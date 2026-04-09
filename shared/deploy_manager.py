"""Vercel deploy manager for Hatchery agents."""
import os
import logging
import urllib.request
import urllib.error
import json
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class DeployManager:
    """Handle Vercel deployments."""

    def __init__(self, vercel_token: str, github_token: str):
        self.vercel_token = vercel_token
        self.github_token = github_token

    def deploy(self, project_dir: Path, vercel_project_id: Optional[str] = None) -> dict:
        """
        Deploy a project to Vercel using the Vercel API.
        Returns dict with deployment URL and id.
        """
        if not vercel_project_id:
            logger.warning("No vercel_project_id provided, skipping deploy")
            return {"skipped": True}

        # Vercel API: create new deployment
        url = f"https://api.vercel.com/v13/deployments"
        payload = {
            "gitSource": {
                "type": "github",
                "repo": self._get_repo_name(project_dir),
                "ref": "main",
            },
            "project": vercel_project_id,
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Authorization": f"Bearer {self.vercel_token}",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return {
                    "url": data.get("url", ""),
                    "id": data.get("id", ""),
                    "status": data.get("status", ""),
                }
        except urllib.error.HTTPError as e:
            body_err = e.read().decode() if e.fp else ""
            logger.error(f"Vercel deploy error {e.code}: {body_err[:300]}")
            return {"error": body_err}

    def smoke_test(self, url: str) -> bool:
        """Run a quick smoke test (HTTP GET) on the deployed URL."""
        if not url:
            return False
        try:
            req = urllib.request.Request(url.rstrip("/") + "/")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Smoke test failed for {url}: {e}")
            return False

    def _get_repo_name(self, project_dir: Path) -> str:
        """Get owner/repo from git remote."""
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_dir, capture_output=True, text=True
        )
        url = r.stdout.decode().strip()
        # https://github.com/wannanaplabs/repo.git → wannanaplabs/repo
        parts = url.rstrip("/").replace(".git", "").split("/")
        return f"{parts[-2]}/{parts[-1]}"
