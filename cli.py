#!/usr/bin/env python3
"""
Agentic GitHub Issue Resolver -- CLI entrypoint.

Usage:
    # Full offline demo (no API key / network needed):
    python3 cli.py --demo

    # Real usage against a Python + pytest GitHub repo:
    python3 cli.py --repo owner/repo --issue 27

    # Force the offline mock LLM even on a real repo (useful for testing
    # the pipeline mechanics without burning API credits):
    python3 cli.py --repo owner/repo --issue 27 --no-llm
"""
import argparse
import os
import sys
from datetime import datetime

import config
from agent.llm_client import get_llm_client
from agent.orchestrator import IssueResolverAgent


def build_report_markdown(report) -> str:
    lines = []
    lines.append(f"# Issue Resolution Report\n")
    lines.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}\n")
    lines.append(f"**Status:** `{report.status}`\n")

    lines.append("## Issue\n")
    lines.append(f"- **Title:** {report.issue.title}")
    lines.append(f"- **URL:** {report.issue.url}\n")
    lines.append(f"```\n{report.issue.body.strip()}\n```\n")

    lines.append("## Classification\n")
    for k, v in report.classification.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")

    lines.append("## Files Inspected\n")
    for f in report.inspected_files:
        lines.append(f"- `{f}`")
    lines.append("")

    lines.append("## Test Results\n")
    lines.append(f"- **Baseline (before fix):** {report.baseline_tests.summary if report.baseline_tests else 'n/a'}")
    if report.post_patch_tests:
        lines.append(f"- **After fix:** {report.post_patch_tests.summary}")
    lines.append("")

    lines.append("## Proposed Patch\n")
    lines.append(f"```diff\n{report.diff.strip()}\n```\n")
    lines.append(f"**Why:** {report.patch_reasoning}\n")

    if report.explanation:
        lines.append("## Explanation (for the PR description)\n")
        lines.append(report.explanation.strip() + "\n")

    lines.append("## Full Agent Trace\n")
    for entry in report.log:
        lines.append(f"- {entry}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Agentic GitHub Issue Resolver (V1)")
    parser.add_argument("--repo", help="GitHub repo, e.g. owner/repo or full URL")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--demo", action="store_true",
                         help="Run the bundled offline demo (no API keys/network needed)")
    parser.add_argument("--no-llm", action="store_true",
                         help="Force the offline mock LLM instead of the real Claude API")
    parser.add_argument("--keep-workdir", action="store_true",
                         help="Don't delete the cloned/copied repo after the run "
                              "(useful for inspecting the patched code yourself)")
    args = parser.parse_args()

    if not args.demo and (not args.repo or not args.issue):
        parser.error("Provide --repo and --issue, or pass --demo to run the offline demo.")

    llm = get_llm_client(force_mock=args.no_llm or args.demo)
    print(f"[cli] Using LLM backend: {type(llm).__name__}")

    agent = IssueResolverAgent(llm_client=llm)

    try:
        report = agent.run(repo_slug=args.repo, issue_number=args.issue, demo=args.demo)
    except Exception as e:
        print(f"\n[cli] ERROR: {e}", file=sys.stderr)
        agent.cleanup()
        sys.exit(1)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if report.diff.strip():
        diff_path = os.path.join(config.OUTPUT_DIR, "patch.diff")
        with open(diff_path, "w") as f:
            f.write(report.diff)
        print(f"\n[cli] Diff written to {diff_path}")

    report_path = os.path.join(config.OUTPUT_DIR, "report.md")
    with open(report_path, "w") as f:
        f.write(build_report_markdown(report))
    print(f"[cli] Full report written to {report_path}")

    print("\n" + "=" * 70)
    print(f"FINAL STATUS: {report.status.upper()}")
    print("=" * 70)
    if report.status == "fixed":
        print("Tests pass after the patch. Review output/patch.diff and")
        print("output/report.md, then approve it to open as a real PR (V2).")
    elif report.status == "patch_failed":
        print("The candidate patch did not make tests pass (or failed to apply).")
        print("See output/report.md for the full trace. (Automatic retry is a V2 feature.)")
    elif report.status == "no_repro":
        print("The agent could not find any relevant files for this issue in V1's")
        print("simple keyword search -- see output/report.md.")

    if not args.keep_workdir:
        agent.cleanup()
    else:
        print(f"\n[cli] Workdir kept at: {report.repo_path}")


if __name__ == "__main__":
    main()
