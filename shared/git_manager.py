"""Git operations for Hatchery agents — clone, commit, push, PR."""
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class GitManager:
    """Manages git operations for a single agent session."""

    def __init__(self, github_token: str,
                 author_name: str = "Hatchery Agent",
                 author_email: str = "agent@hatchery.local"):
        self.github_token = github_token
        self.author_name = author_name
        self.author_email = author_email
        self._repo_dir: Optional[Path] = None
        self._setup_git_creds()

    def _setup_git_creds(self):
        """Store GitHub token in git credential helper."""
        # Write token to git's credential store so clones/pushes auth automatically
        creds = f"https://{self.github_token}@github.com\n"
        subprocess.run(
            ["git", "config", "--global", "credential.helper", "store"],
            check=False
        )
        try:
            with open(Path.home() / ".git-credentials", "w") as f:
                f.write(creds)
        except Exception as e:
            logger.warning(f"Could not write .git-credentials: {e}")

        # Set author identity
        subprocess.run(["git", "config", "--global", "user.name", self.author_name], check=False)
        subprocess.run(["git", "config", "--global", "user.email", self.author_email], check=False)

    def clone_or_pull(self, repo_url: str, target_dir: Optional[Path] = None) -> Path:
        """
        Clone a repo if not present, otherwise pull latest main.
        Returns the Path to the repo root.
        """
        if target_dir is None:
            # Derive local path from repo URL (e.g. github.com/wannanaplabs/toxic-clouds → ~/repos/toxic-clouds)
            parts = repo_url.rstrip("/").split("/")
            slug = parts[-1].replace(".git", "")
            target_dir = Path.home() / "hatchery-repos" / slug

        if target_dir.exists():
            # Pull latest main
            logger.info(f"Pulling {target_dir}")
            subprocess.run(["git", "fetch", "origin"], cwd=target_dir, check=False)
            subprocess.run(["git", "checkout", "main"], cwd=target_dir, check=False)
            subprocess.run(["git", "pull", "origin", "main"],
                           cwd=target_dir, check=False)
        else:
            # Clone
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cloning {repo_url} → {target_dir}")
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
                check=True
            )
        self._repo_dir = target_dir
        return target_dir

    def new_branch(self, branch_name: str) -> subprocess.CompletedProcess:
        """Create and switch to a new branch."""
        if not self._repo_dir:
            raise RuntimeError("Must call clone_or_pull first")
        r = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=self._repo_dir, capture_output=True, text=True
        )
        logger.info(f"Branch {branch_name}: {r.returncode}")
        return r

    def add_commit(self, message: str) -> subprocess.CompletedProcess:
        """Stage all changes and commit."""
        if not self._repo_dir:
            raise RuntimeError("Must call clone_or_pull first")
        subprocess.run(["git", "add", "."], cwd=self._repo_dir, check=True)
        r = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self._repo_dir, capture_output=True, text=True
        )
        if r.returncode != 0:
            logger.warning(f"Nothing to commit: {r.stderr.decode()[:100]}")
        return r

    def push(self, remote: str = "origin", set_upstream: bool = True) -> subprocess.CompletedProcess:
        """Push current branch to remote."""
        if not self._repo_dir:
            raise RuntimeError("Must call clone_or_pull first")
        cmd = ["git", "push", remote]
        if set_upstream:
            cmd.extend(["-u", remote])
        r = subprocess.run(cmd, cwd=self._repo_dir, capture_output=True, text=True)
        if r.returncode != 0:
            logger.error(f"Push failed: {r.stderr.decode()[:200]}")
        return r

    def open_pr(self, title: str, body: str,
               head_branch: str, base: str = "main") -> dict:
        """Open a GitHub PR using gh CLI. Returns parsed gh output."""
        if not self._repo_dir:
            raise RuntimeError("Must call clone_or_pull first")
        r = subprocess.run(
            ["gh", "pr", "create",
             "--title", title, "--body", body,
             "--head", head_branch, "--base", base,
             "--repo", self._get_repo_slug()],
            cwd=self._repo_dir, capture_output=True, text=True
        )
        if r.returncode != 0:
            logger.error(f"PR create failed: {r.stderr.decode()[:200]}")
            return {"error": r.stderr.decode()}
        # gh outputs PR URL on success
        return {"url": r.stdout.decode().strip()}

    def _get_repo_slug(self) -> str:
        """Extract 'owner/repo' from current repo remote URL."""
        if not self._repo_dir:
            raise RuntimeError("Must call clone_or_pull first")
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self._repo_dir, capture_output=True, text=True
        )
        url = r.stdout.decode().strip()
        # https://github.com/wannanaplabs/repo.git → wannanaplabs/repo
        parts = url.rstrip("/").replace(".git", "").split("/")
        return f"{parts[-2]}/{parts[-1]}"

    def run(self, cmd: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run an arbitrary shell command in the repo (or cwd)."""
        return subprocess.run(cmd, cwd=cwd or self._repo_dir,
                              capture_output=True, text=True)
