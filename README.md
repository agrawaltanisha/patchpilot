# Agentic GitHub Issue Resolver (V1)

An AI agent that takes a **GitHub issue** and autonomously tries to
understand it, find the relevant code, reproduce the bug via the
existing test suite, generate a candidate fix, and verify the fix by
re-running the tests — producing a diff and a human-readable report at
the end.

This is *agentic* rather than "an LLM behind a chat box": the agent
plans a multi-step workflow, calls tools (git, the filesystem, pytest,
the GitHub API), keeps state across steps, and only hands control back
to a human once it has evidence the fix actually works.

```
Issue
  │
  ▼
Understand (classify: bug / component)
  │
  ▼
Clone / inspect repo
  │
  ▼
Search files (keyword ranking) ──► Read relevant code + related tests
  │
  ▼
Run existing tests  ──────────────► baseline: PASS / FAIL
  │
  ▼
Generate candidate fix (LLM, unified diff)
  │
  ▼
Apply patch (git apply)
  │
  ▼
Run tests again ──────────────────► after fix: PASS / FAIL
  │
  ▼
Explain the change  →  output/patch.diff + output/report.md
```

## V1 scope (by design)

To keep this shippable and reliable rather than a half-working "Devin
clone", V1 deliberately only supports:

- **Python repositories that use pytest.**
- A **single fix attempt** (no retry loop yet).
- **No auto-merge** — the agent writes a diff + report for a human to
  review; it never pushes or opens a PR itself yet.

What V1 *does* do, fully working end-to-end:

1. Clone a repository
2. Read a GitHub issue (via the GitHub REST API)
3. Search files (keyword-ranked scan of the repo)
4. Read the relevant code + likely test files
5. Run the existing tests (baseline)
6. Generate a patch (via Claude, as a unified diff)
7. Apply the patch and run the tests again
8. Explain what changed, in a Markdown report

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Option A — run the offline demo (recommended first run)

No API keys, no network access needed. This exercises the **entire**
pipeline against a bundled toy repo (`demo_repo/`) that has a real bug
matching the example from the spec ("CSV upload fails when a row
contains an empty date"), using a deterministic offline mock in place
of the LLM:

```bash
python3 cli.py --demo
```

You'll see the agent's full trace printed live, and two files written to
`output/`:

- `output/patch.diff` — the generated fix, as a real unified diff
- `output/report.md` — issue, classification, test results before/after,
  the diff, the reasoning, and the full step-by-step trace

### Option B — run against a real GitHub repo

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY (and optionally GITHUB_TOKEN)

python3 cli.py --repo owner/repo --issue 27
```

Requirements for the target repo: it must be a **public Python
repository that uses pytest**, and pytest/its dependencies should be
installable in your environment (V1 does not sandbox-install a repo's
own requirements.txt yet — see Limitations below).

Useful flags:

```bash
python3 cli.py --repo owner/repo --issue 27 --no-llm       # force the offline mock LLM
python3 cli.py --repo owner/repo --issue 27 --keep-workdir  # don't delete the clone afterwards
```

## Project structure

```
github_issue_resolver/
├── cli.py                  # entrypoint: argument parsing, report writing
├── config.py                # all settings / env vars in one place
├── agent/
│   ├── github_client.py     # Step 1: fetch issue via GitHub REST API
│   ├── repo_manager.py      # Step 2: git clone / isolated workdir management
│   ├── code_search.py       # Steps 3-4: keyword extraction + file ranking
│   ├── test_runner.py       # Steps 6 & 8: run pytest, parse pass/fail
│   ├── llm_client.py        # Steps 2, 7, 9: classify / patch / explain
│   │                         #   - ClaudeLLMClient: real Anthropic API calls
│   │                         #   - MockLLMClient: offline, used by --demo
│   ├── patch_generator.py   # Step 7: apply the diff via `git apply`
│   └── orchestrator.py       # wires all steps into the agent's control loop
├── demo_repo/                # toy Python project with a real, reproducible bug
│   ├── csv_parser.py
│   ├── tests/test_csv_parser.py
│   └── ISSUE.md
├── requirements.txt
└── .env.example
```

## Design notes / why it's built this way

- **`LLMClient` is an abstract interface** (`ClaudeLLMClient` /
  `MockLLMClient`), not a hardcoded API call scattered through the
  codebase. This is what makes `--demo` possible, makes the pipeline
  unit-testable without burning API credits, and would make swapping
  in a different model provider a one-file change.
- **The repo is never touched in place.** Every run clones (or copies,
  in demo mode) into its own timestamped folder under `workdir/`, and
  `git apply`/tests operate only on that isolated copy.
- **Keyword search over embeddings, on purpose.** A vector DB would be
  overkill and non-deterministic for V1's scope; a transparent,
  debuggable ranking (word counts) is easier to reason about and to
  explain in an interview.
- **`git apply` over hand-rolled patching.** Real PR tooling relies on
  the same mechanism; it also gives us a free correctness check (a
  patch either applies cleanly or the agent reports failure honestly,
  rather than silently corrupting a file).
- **State is inspectable, not hidden.** `RunReport` records every
  step's output, which is what turns this from "an LLM call" into
  something you can genuinely call an *agent trace*.

## Limitations (intentional, for V1)

- Only Python + pytest projects.
- No retry loop if the generated patch fails to fix the bug.
- No human-approval gate or PR creation yet.
- No sandboxed dependency installation — if the target repo needs
  packages beyond the stdlib, install them into your environment
  first (`pip install -r <target-repo>/requirements.txt`).
- Keyword search is intentionally simple (no ASTs/embeddings) — a
  deliberate scope decision, not an oversight.

## Roadmap (V2)

- **Automatic reproduction test**: have the LLM write a new failing
  test from the issue text *before* looking at the fix, to prove the
  bug is understood (not just that existing tests already covered it).
- **Retry when tests fail**: feed the failing test output back into
  `generate_patch` for a second attempt.
- **Diff viewer**: a small web UI (or terminal UI) to review the patch
  interactively instead of reading a `.diff` file.
- **Human-in-the-loop approval gate**: agent pauses and waits for an
  explicit "approve" before doing anything further.
- **PR description generation + opening a real draft PR** via the
  GitHub API once approved.

## CV / interview talking points

This project intentionally touches: LLM/agent engineering & tool use,
planning a multi-step workflow, Git/GitHub automation, sandboxed code
execution, automated testing, state management across an agent run,
and human-in-the-loop design — a much more concrete interview story
than "built a chatbot with an LLM API".
