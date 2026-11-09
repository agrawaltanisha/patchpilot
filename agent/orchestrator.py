"""
The agent's control loop (V1 scope):

    Issue -> Understand -> Inspect repo -> Find files -> Read code
          -> Run tests (baseline) -> Generate patch -> Apply patch
          -> Run tests (again) -> Explain what changed

Each step's result is recorded on the returned RunReport so the CLI
(or any future UI/API) can render a full trace, not just the final
answer -- this is what makes it "agentic" rather than a single LLM
call: the state persists and is inspectable at every step.
"""
import os
from dataclasses import dataclass, field

import config
from agent import code_search, patch_generator, test_runner
from agent.github_client import GitHubClient, Issue
from agent.llm_client import LLMClient
from agent.repo_manager import RepoManager


@dataclass
class RunReport:
    issue: Issue = None
    classification: dict = field(default_factory=dict)
    keywords: list = field(default_factory=list)
    file_matches: list = field(default_factory=list)
    inspected_files: list = field(default_factory=list)
    test_files_run: list = field(default_factory=list)
    baseline_tests: test_runner.TestResult = None
    diff: str = ""
    patch_reasoning: str = ""
    patch_applied: bool = False
    patch_message: str = ""
    post_patch_tests: test_runner.TestResult = None
    explanation: str = ""
    repo_path: str = ""
    status: str = "incomplete"  # incomplete | fixed | patch_failed | no_repro | error
    log: list = field(default_factory=list)

    def step(self, msg: str):
        self.log.append(msg)
        print(f"[agent] {msg}")


class IssueResolverAgent:
    def __init__(self, llm_client: LLMClient, github_client: GitHubClient = None,
                 repo_manager: RepoManager = None):
        self.llm = llm_client
        self.github = github_client or GitHubClient()
        self.repo_manager = repo_manager or RepoManager()

    def run(self, repo_slug: str = None, issue_number: int = None,
            demo: bool = False) -> RunReport:
        report = RunReport()

        # ---- Step 1: Issue ----------------------------------------------
        if demo:
            demo_repo_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_repo"
            )
            report.step("Loading bundled demo issue (no GitHub API call needed)...")
            report.issue = GitHubClient.load_demo_issue(demo_repo_path)
        else:
            report.step(f"Fetching issue #{issue_number} from {repo_slug}...")
            report.issue = self.github.fetch_issue(repo_slug, issue_number)
        report.step(f"Issue: \"{report.issue.title}\"")

        # ---- Step 2: Understand (classify) ------------------------------
        report.step("Classifying issue (category / component)...")
        report.classification = self.llm.classify_issue(report.issue.full_text)
        report.step(f"Classified as: {report.classification}")

        # ---- Step 3: Inspect repo ----------------------------------------
        if demo:
            report.step("Copying demo repo into an isolated workdir...")
            report.repo_path = self.repo_manager.copy_demo_repo(demo_repo_path)
        else:
            report.step(f"Cloning {repo_slug} (shallow) into an isolated workdir...")
            report.repo_path = self.repo_manager.clone(repo_slug)

        # ---- Step 4: Find files ------------------------------------------
        report.step("Extracting keywords from the issue...")
        report.keywords = code_search.extract_keywords(report.issue.title, report.issue.body)
        report.step(f"Keywords: {report.keywords}")

        report.step("Searching repository for relevant files...")
        report.file_matches = code_search.search_repository(report.repo_path, report.keywords)
        top = [f"{m.path} (score={m.score})" for m in report.file_matches[:5]]
        report.step(f"Top matches: {top or 'none found'}")

        if not report.file_matches:
            report.status = "no_repro"
            report.step("No relevant files found -- stopping (V1 cannot proceed blind).")
            return report

        # ---- Step 5: Read relevant code -----------------------------------
        code_context = code_search.read_relevant_files(report.repo_path, report.file_matches)
        report.inspected_files = list(code_context.keys())
        report.step(f"Read {len(report.inspected_files)} file(s): {report.inspected_files}")

        related_tests = code_search.find_related_test_files(
            report.repo_path, report.inspected_files
        )
        report.test_files_run = related_tests
        report.step(f"Related test files: {related_tests or 'none found -- running full suite'}")

        # ---- Step 6: Run tests (baseline) ---------------------------------
        report.step("Running baseline tests (before fix)...")
        report.baseline_tests = test_runner.run_tests(report.repo_path, related_tests or None)
        report.step(f"Baseline result: {report.baseline_tests.summary}")

        # ---- Step 7: Generate candidate fix --------------------------------
        report.step("Generating candidate patch via LLM...")
        patch_result = self.llm.generate_patch(
            report.issue.full_text, code_context, report.baseline_tests.raw_output
        )
        report.diff = patch_result.get("diff", "")
        report.patch_reasoning = patch_result.get("reasoning", "")
        report.step(f"Patch reasoning: {report.patch_reasoning}")

        if not report.diff.strip():
            report.status = "patch_failed"
            report.step("LLM did not produce a usable diff -- stopping.")
            return report

        # Apply the patch to the working copy.
        apply_result = patch_generator.apply_patch(report.repo_path, report.diff)
        report.patch_applied = apply_result.applied
        report.patch_message = apply_result.message
        report.step(f"Patch application: {apply_result.message}")

        if not report.patch_applied:
            report.status = "patch_failed"
            return report

        # ---- Step 8: Run tests again ----------------------------------------
        report.step("Re-running tests (after fix)...")
        report.post_patch_tests = test_runner.run_tests(report.repo_path, related_tests or None)
        report.step(f"Post-patch result: {report.post_patch_tests.summary}")

        # ---- Step 9: Explain ------------------------------------------------
        report.step("Generating plain-English explanation of the change...")
        report.explanation = self.llm.explain_patch(report.diff, report.issue.full_text)

        report.status = "fixed" if report.post_patch_tests.all_passed else "patch_failed"
        report.step(f"Final status: {report.status}")

        return report

    def cleanup(self):
        self.repo_manager.cleanup()
