"""
Step 1: Issue ingestion.

Fetches a GitHub issue's title/body via the REST API, or loads the
bundled demo issue when running without network access / a real repo.
"""
from dataclasses import dataclass

import requests

import config


@dataclass
class Issue:
    number: int
    title: str
    body: str
    url: str = ""

    @property
    def full_text(self) -> str:
        return f"{self.title}\n\n{self.body}"


class GitHubClient:
    def __init__(self, token: str = None):
        self.token = token or config.GITHUB_TOKEN
        self.session = requests.Session()
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    @staticmethod
    def parse_repo_slug(repo_url_or_slug: str) -> str:
        """Accepts 'owner/repo' or a full github URL and returns 'owner/repo'."""
        s = repo_url_or_slug.strip()
        s = s.removeprefix("https://github.com/").removeprefix("http://github.com/")
        s = s.removesuffix(".git").removesuffix("/")
        return s

    def fetch_issue(self, repo_slug: str, issue_number: int) -> Issue:
        repo_slug = self.parse_repo_slug(repo_slug)
        url = f"{config.GITHUB_API_URL}/repos/{repo_slug}/issues/{issue_number}"
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404:
            raise ValueError(f"Issue #{issue_number} not found in {repo_slug}")
        if resp.status_code == 403:
            raise RuntimeError(
                "GitHub API rate-limited or forbidden. Set GITHUB_TOKEN in .env."
            )
        resp.raise_for_status()
        data = resp.json()
        return Issue(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            url=data.get("html_url", ""),
        )

    @staticmethod
    def load_demo_issue(demo_repo_path: str) -> Issue:
        """Parses the bundled demo_repo/ISSUE.md into an Issue object."""
        import os

        with open(os.path.join(demo_repo_path, "ISSUE.md")) as f:
            content = f.read()
        title_line = next(l for l in content.splitlines() if l.startswith("Title:"))
        title = title_line.replace("Title:", "").strip()
        body = content.split("Body:", 1)[1].strip() if "Body:" in content else content
        return Issue(number=0, title=title, body=body, url="(demo mode - no URL)")
