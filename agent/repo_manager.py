"""
Step 2: Repository acquisition.

Clones a real GitHub repo into an isolated working directory (never
touching the user's actual filesystem outside workdir/), or copies the
bundled demo repo when running in --demo mode. All git operations shell
out to the `git` binary so no extra dependency (e.g. GitPython) is
required.
"""
import os
import shutil
import subprocess
import time
import uuid

import config


class RepoManager:
    def __init__(self, workdir_root: str = None):
        self.workdir_root = workdir_root or config.WORKDIR_ROOT
        os.makedirs(self.workdir_root, exist_ok=True)
        self.repo_path = None

    def _new_session_dir(self) -> str:
        session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        path = os.path.join(self.workdir_root, session_id)
        os.makedirs(path, exist_ok=True)
        return path

    def clone(self, repo_url_or_slug: str) -> str:
        """Shallow-clones a real GitHub repository. Returns the local path."""
        session_dir = self._new_session_dir()
        repo_path = os.path.join(session_dir, "repo")

        slug = repo_url_or_slug
        if not slug.startswith(("http://", "https://", "git@")):
            slug = f"https://github.com/{slug}"
        if not slug.endswith(".git"):
            slug += ".git"

        result = subprocess.run(
            ["git", "clone", "--depth", "1", slug, repo_path],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

        self._ensure_git_identity(repo_path)
        self.repo_path = repo_path
        return repo_path

    def copy_demo_repo(self, demo_repo_path: str) -> str:
        """Copies the bundled demo repo into an isolated workdir and git-inits it,
        so patch application (git apply / git diff) works exactly like on a real
        clone."""
        session_dir = self._new_session_dir()
        repo_path = os.path.join(session_dir, "repo")
        shutil.copytree(
            demo_repo_path, repo_path,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

        subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
        self._ensure_git_identity(repo_path)
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "initial commit (demo repo baseline)"],
            cwd=repo_path, check=True,
        )
        self.repo_path = repo_path
        return repo_path

    @staticmethod
    def _ensure_git_identity(repo_path: str):
        """Sets a local commit identity so `git commit`/`git apply` never fail
        in a fresh environment that has no global git config."""
        subprocess.run(["git", "config", "user.email", "agent@issue-resolver.local"],
                        cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Issue Resolver Agent"],
                        cwd=repo_path, check=True)

    def cleanup(self):
        if self.repo_path and os.path.exists(self.repo_path):
            shutil.rmtree(os.path.dirname(self.repo_path), ignore_errors=True)
