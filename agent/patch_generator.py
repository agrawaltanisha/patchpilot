"""
Step 7: Apply the LLM-generated unified diff to the repo working copy.

Uses `git apply` (the repo copy is always a real git repo -- see
RepoManager) since it's far more robust than hand-rolling a patch
parser, and it's what real PR tooling relies on too.
"""
import os
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass
class PatchResult:
    applied: bool
    message: str = ""


def apply_patch(repo_path: str, diff_text: str) -> PatchResult:
    if not diff_text or not diff_text.strip():
        return PatchResult(applied=False, message="Empty diff -- nothing to apply.")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False
    ) as f:
        f.write(diff_text)
        if not diff_text.endswith("\n"):
            f.write("\n")
        patch_file = f.name

    try:
        # --whitespace=fix tolerates minor trailing-whitespace diffs the LLM
        # might introduce; -p1 matches the a/ b/ prefixes we ask the LLM for.
        result = subprocess.run(
            ["git", "apply", "--whitespace=fix", "-p1", patch_file],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return PatchResult(applied=True, message="Patch applied cleanly.")

        # Retry with --3way in case of minor context drift (still safe: it
        # only succeeds if the merge is unambiguous).
        result3 = subprocess.run(
            ["git", "apply", "--3way", "--whitespace=fix", "-p1", patch_file],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result3.returncode == 0:
            return PatchResult(applied=True, message="Patch applied via 3-way merge.")

        return PatchResult(
            applied=False,
            message=f"git apply failed:\n{result.stderr.strip()}\n{result3.stderr.strip()}",
        )
    finally:
        os.unlink(patch_file)
