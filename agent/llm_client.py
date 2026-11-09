"""
The "brain" of the agent: issue classification, patch generation, and
plain-English explanation. Defined as an ABC so the orchestrator never
cares whether it's talking to the real Claude API or the offline mock
used by `--demo` (this is what makes the pipeline testable without an
API key, and swappable for a different provider later).
"""
import json
import re
from abc import ABC, abstractmethod

import config


class LLMClient(ABC):
    @abstractmethod
    def classify_issue(self, issue_text: str) -> dict:
        """Returns {'category': str, 'component': str, 'summary': str}"""

    @abstractmethod
    def generate_patch(self, issue_text: str, code_context: dict, test_output: str) -> dict:
        """Returns {'diff': str, 'reasoning': str} where diff is a unified
        diff (git apply -compatible) against the given code_context files."""

    @abstractmethod
    def explain_patch(self, diff: str, issue_text: str) -> str:
        """Returns a short, human-readable explanation of what the patch does."""


class ClaudeLLMClient(LLMClient):
    """Real implementation backed by the Anthropic Messages API."""

    def __init__(self, api_key: str = None, model: str = None):
        import anthropic  # imported lazily so --demo never requires the package

        self.client = anthropic.Anthropic(api_key=api_key or config.ANTHROPIC_API_KEY)
        self.model = model or config.ANTHROPIC_MODEL

    def _ask(self, system: str, user: str, max_tokens: int = 2000) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def classify_issue(self, issue_text: str) -> dict:
        system = (
            "You are a senior software engineer triaging a GitHub issue. "
            "Respond with ONLY a JSON object, no prose, no markdown fences, "
            "with keys: category (bug/feature/docs/question), "
            "component (short guess, e.g. 'backend/parsing'), "
            "summary (one sentence)."
        )
        raw = self._ask(system, issue_text, max_tokens=300)
        return _safe_json(raw, fallback={
            "category": "bug", "component": "unknown", "summary": issue_text[:120],
        })

    def generate_patch(self, issue_text: str, code_context: dict, test_output: str) -> dict:
        files_block = "\n\n".join(
            f"--- FILE: {path} ---\n{content}" for path, content in code_context.items()
        )
        system = (
            "You are an expert Python engineer fixing a bug. You will be given "
            "a GitHub issue, the contents of relevant files, and the current "
            "failing test output. Produce a minimal fix as a unified diff "
            "(the format `git apply` accepts: '--- a/path', '+++ b/path', "
            "'@@' hunks with correct line context). "
            "Respond with ONLY a JSON object, no markdown fences, with keys: "
            "'diff' (the unified diff as a string, using the SAME relative "
            "file paths shown in FILE headers, prefixed with a/ and b/) and "
            "'reasoning' (2-3 sentences on why this fixes it)."
        )
        user = (
            f"ISSUE:\n{issue_text}\n\n"
            f"RELEVANT FILES:\n{files_block}\n\n"
            f"CURRENT TEST OUTPUT (baseline, before fix):\n{test_output}\n"
        )
        raw = self._ask(system, user, max_tokens=3000)
        return _safe_json(raw, fallback={"diff": "", "reasoning": "LLM did not return valid JSON."})

    def explain_patch(self, diff: str, issue_text: str) -> str:
        system = (
            "Explain the following unified diff in plain English for a PR "
            "description. 3-5 sentences, no markdown fences."
        )
        return self._ask(system, f"ISSUE:\n{issue_text}\n\nDIFF:\n{diff}", max_tokens=400)


class MockLLMClient(LLMClient):
    """Offline, deterministic 'LLM' used for `--demo` mode so the full
    pipeline can be demonstrated/graded without any API key or network
    access. It recognizes the specific bundled demo bug (empty-date CSV
    parsing) and produces a real, working unified diff for it -- every
    other pipeline step (search, test running, patch application) is
    exercised exactly as it would be with a real LLM."""

    def classify_issue(self, issue_text: str) -> dict:
        return {
            "category": "bug",
            "component": "backend/parsing",
            "summary": "CSV rows with an empty date field crash the parser instead "
                       "of being handled gracefully.",
        }

    def generate_patch(self, issue_text: str, code_context: dict, test_output: str) -> dict:
        target = "csv_parser.py"
        if target not in code_context:
            return {"diff": "", "reasoning": "Mock LLM only knows how to patch csv_parser.py."}

        original = code_context[target]
        old_block = (
            '    # BUG: this blows up with ValueError when row["date"] == ""\n'
            '    date_str = row.get("date", "")\n'
            '    date = datetime.strptime(date_str, "%Y-%m-%d")\n'
        )
        new_block = (
            '    date_str = row.get("date", "").strip()\n'
            '    date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else None\n'
        )
        if old_block not in original:
            return {"diff": "", "reasoning": "Mock LLM could not locate the expected buggy block."}

        patched = original.replace(old_block, new_block)
        diff = _make_unified_diff(target, original, patched)
        reasoning = (
            "The parser called datetime.strptime on an empty string, which always "
            "raises ValueError. The fix short-circuits: if the date field is empty "
            "after stripping whitespace, the row's date is set to None instead of "
            "attempting to parse it."
        )
        return {"diff": diff, "reasoning": reasoning}

    def explain_patch(self, diff: str, issue_text: str) -> str:
        return (
            "This patch fixes the crash reported in the issue: uploading a CSV where "
            "a row's date column is blank used to raise `ValueError: time data '' does "
            "not match format '%Y-%m-%d'`. The fix checks whether the date string is "
            "empty (after trimming whitespace) before calling strptime, and sets the "
            "row's date to None in that case instead of crashing. All other rows are "
            "parsed exactly as before."
        )


def _safe_json(raw: str, fallback: dict) -> dict:
    """LLMs occasionally wrap JSON in markdown fences or add stray text;
    this defensively extracts the JSON object."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return fallback
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback


def _make_unified_diff(rel_path: str, original: str, patched: str) -> str:
    import difflib

    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
    )
    return "".join(diff_lines)


def get_llm_client(force_mock: bool = False) -> LLMClient:
    """Factory: returns the real Claude client if an API key is configured
    (and not force_mock), otherwise falls back to the offline mock."""
    if not force_mock and config.ANTHROPIC_API_KEY:
        return ClaudeLLMClient()
    return MockLLMClient()
