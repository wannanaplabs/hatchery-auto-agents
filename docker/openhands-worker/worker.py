#!/usr/bin/env python3
"""
WannaNapLabs OpenHands Worker — Hatchery poller that delegates the coding loop to
the OpenHands headless CLI (docs.openhands.dev).

Why a separate worker vs Hermes?
  - Hermes (NousResearch) scores ~10-20% on SWE-bench Verified.
  - OpenHands's edit->build->test->retry loop scores ~53% on SWE-bench Verified.
  - This worker shares the same Hatchery queue, same Goop API key, same PR flow —
    whoever claims a task first wins. Measure which framework ships better work.

Invocation model:
  1. Poll /api/v1/agent/tasks/available
  2. If repo has an open auto/* PR: skip (let prior PR land first)
  3. Claim task, clone repo to /repos/<slug>
  4. Invoke `openhands --headless -t "<prompt>" --config-file /tmp/oh-config.toml`
     inside the repo dir. OpenHands handles: file edits, npm install, npm run build,
     retry on failure.
  5. After OpenHands exits: soft-reset to origin/main (undoes any commits OpenHands
     made), create feature branch auto/<task_id[:8]>, commit+push, open PR via gh.
  6. PATCH task {status: review, pr_url: ...}. Hatchery webhook auto-closes on merge.
  7. On any exception: PATCH task {status: ready, assignee_agent_id: null}.

Environment variables:
  WORKER_NAME      — e.g. openhands-claude, openhands-minimax
  LLM_MODEL        — e.g. anthropic/claude-sonnet-4-5-20250929, openai/MiniMax-M2.7
  LLM_API_KEY      — key for the above provider
  LLM_BASE_URL     — base URL (for MiniMax: https://api.minimax.io/v1)
  HATCHERY_API_KEY — Goop fleet key
  HATCHERY_BASE_URL— default https://hatchery.run
  GITHUB_TOKEN     — GH push + PR creation
  GITHUB_ORG       — default wannanaplabs
  POLL_INTERVAL    — default 30
  OPENHANDS_TIMEOUT — default 600 (10 min cap per task)
"""

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)

WORKER_NAME = os.environ.get("WORKER_NAME", "openhands-worker")
logger = logging.getLogger(WORKER_NAME)

HATCHERY_BASE = os.environ.get("HATCHERY_BASE_URL", "https://hatchery.run")
HATCHERY_KEY = os.environ.get("HATCHERY_API_KEY", "")
GITHUB_ORG = os.environ.get("GITHUB_ORG", "wannanaplabs")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
OPENHANDS_TIMEOUT = int(os.environ.get("OPENHANDS_TIMEOUT", "600"))

LLM_MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")


# =====================================================================
# Hatchery API helpers (lifted verbatim from hermes-worker for parity)
# =====================================================================

def hatchery_api(method, path, data=None, return_status=False):
    url = f"{HATCHERY_BASE}/api/v1/{path.lstrip('/')}"
    body = json.dumps(data).encode() if data else None
    headers = {"Authorization": f"Bearer {HATCHERY_KEY}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read() or b"{}")
            if return_status:
                return payload, r.status
            return payload
    except urllib.error.HTTPError as e:
        if return_status:
            return {}, e.code
        return {}
    except Exception:
        if return_status:
            return {}, 0
        return {}


def fetch_project_context(project_id):
    if not project_id:
        return ""
    chunks = []
    digest = hatchery_api("GET", f"agent/projects/{project_id}/digest")
    if isinstance(digest, dict) and digest:
        summary = digest.get("summary") or digest.get("digest") or digest.get("content") or ""
        if summary:
            chunks.append(f"DIGEST:\n{str(summary)[:1500]}")
    spec = hatchery_api("GET", f"agent/projects/{project_id}/spec")
    if isinstance(spec, dict) and spec:
        spec_txt = spec.get("spec") or spec.get("content") or spec.get("text") or ""
        if spec_txt:
            chunks.append(f"SPEC:\n{str(spec_txt)[:1500]}")
    return "\n\n".join(chunks)


def release_task(task_id, reason):
    """POST /release — bare PATCH returns 401 after Hatchery auth tightening."""
    resp, status = hatchery_api(
        "POST", f"agent/tasks/{task_id}/release",
        {"comment": f"[{WORKER_NAME}] {reason[:200]}"}, return_status=True,
    )
    if status in (200, 201, 204):
        logger.info(f"Released task {task_id}: {reason[:80]}")
    else:
        logger.warning(f"Release returned HTTP {status} for {task_id}")


def submit_for_qa(task_id, note):
    resp, status = hatchery_api(
        "POST", f"agent/tasks/{task_id}/submit-for-qa",
        {"note": note}, return_status=True,
    )
    if status in (200, 201, 202, 204):
        logger.info(f"Submitted task {task_id} for QA (HTTP {status})")
        return True
    if status in (404, 405):
        hatchery_api("PATCH", f"agent/tasks/{task_id}", {"status": "done"})
        return True
    hatchery_api("PATCH", f"agent/tasks/{task_id}", {"status": "done"})
    return False


def stale_claimed_reaper():
    try:
        resp = hatchery_api("GET", f"agent/tasks/search?status=claimed&agent_id={WORKER_NAME}")
        tasks = resp.get("tasks", []) if isinstance(resp, dict) else []
        if not tasks:
            alt = hatchery_api("GET", "agent/tasks/claimed")
            tasks = alt.get("tasks", []) if isinstance(alt, dict) else []
        cutoff = time.time() - 15 * 60
        released = 0
        from datetime import datetime
        for t in tasks:
            ts = t.get("updated_at") or t.get("claimed_at") or ""
            try:
                iso = ts.replace("Z", "+00:00") if isinstance(ts, str) else ""
                dt = datetime.fromisoformat(iso).timestamp() if iso else 0
            except Exception:
                dt = 0
            if dt and dt < cutoff:
                release_task(t.get("id"), "startup: stale claim >15min")
                released += 1
        logger.info(f"Stale-claimed reaper: released {released} task(s)")
    except Exception as e:
        logger.warning(f"stale_claimed_reaper error: {e}")


# =====================================================================
# Git / PR helpers
# =====================================================================

def extract_slug(repo_url):
    if not repo_url:
        return ""
    s = repo_url.rstrip("/").split("/")[-1]
    if s.endswith(".git"):
        s = s[:-4]
    return s


def has_open_pr_from_self(slug):
    if not slug:
        return False
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--repo", f"{GITHUB_ORG}/{slug}",
             "--state", "open", "--json", "headRefName,number"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return False
        prs = json.loads(result.stdout or "[]")
        return any(pr.get("headRefName", "").startswith("auto/") for pr in prs)
    except Exception as e:
        logger.warning(f"has_open_pr_from_self({slug}) failed: {e}")
        return False


def create_pr(slug, branch, title, body):
    if not slug:
        return ""
    try:
        result = subprocess.run(
            ["gh", "pr", "create",
             "--repo", f"{GITHUB_ORG}/{slug}",
             "--base", "main",
             "--head", branch,
             "--title", title[:120],
             "--body", body[:4000]],
            capture_output=True, text=True, timeout=30,
        )
        url = (result.stdout or "").strip()
        if result.returncode != 0 or not url.startswith("http"):
            logger.warning(f"gh pr create failed ({result.returncode}): "
                           f"stdout={url[:200]!r} stderr={(result.stderr or '')[:200]!r}")
            return ""
        return url
    except Exception as e:
        logger.warning(f"gh pr create exception: {e}")
        return ""


# =====================================================================
# Project self-heal (match Hermes conventions so PRs actually build on Vercel)
# =====================================================================

def _pin_next_version(workdir):
    pj = f"{workdir}/package.json"
    if not os.path.exists(pj):
        return
    try:
        with open(pj) as f:
            d = json.load(f)
        changed = False
        if isinstance(d.get("dependencies"), dict) and "next" in d["dependencies"]:
            if d["dependencies"]["next"] != "15.5.15":
                d["dependencies"]["next"] = "15.5.15"
                changed = True
        if changed:
            with open(pj, "w") as f:
                json.dump(d, f, indent=2)
            logger.info(f"_pin_next_version: pinned next@15.5.15 in {pj}")
    except Exception as e:
        logger.warning(f"pin_next failed: {e}")


def _ensure_npmrc_legacy_peer(workdir):
    p = f"{workdir}/.npmrc"
    line = "legacy-peer-deps=true\n"
    try:
        if os.path.exists(p):
            with open(p) as f:
                existing = f.read()
            if "legacy-peer-deps" not in existing:
                with open(p, "a") as f:
                    f.write(line if existing.endswith("\n") or existing == "" else "\n" + line)
        else:
            with open(p, "w") as f:
                f.write(line)
    except Exception as e:
        logger.warning(f"npmrc fix failed: {e}")


def _fix_use_client(workdir):
    p = f"{workdir}/src/app/page.tsx"
    if not os.path.exists(p):
        return
    try:
        with open(p) as f:
            content = f.read()
        needs_client = any(h in content for h in (
            "useState", "useEffect", "useRouter", "useCallback", "onClick=",
        ))
        stripped = content.lstrip()
        if needs_client and not (stripped.startswith('"use client"') or stripped.startswith("'use client'")):
            with open(p, "w") as f:
                f.write('"use client";\n\n' + content)
            logger.info(f"_fix_use_client: prepended directive to {p}")
    except Exception as e:
        logger.warning(f"use_client fix failed: {e}")


def _scan_for_stubs(workdir):
    patterns = [
        r"return\s*<div\s*/?>\s*</div>",
        r"return\s*<div\s*/>",
        r"//\s*TODO(?!.*task)",
        r"//\s*In production,?\s+this\s+would",
    ]
    root_dir = f"{workdir}/src"
    if not os.path.isdir(root_dir):
        return None
    try:
        for root, _dirs, files in os.walk(root_dir):
            for fname in files:
                if not fname.endswith((".tsx", ".ts", ".jsx", ".js")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, errors="ignore") as fh:
                        content = fh.read()
                except Exception:
                    continue
                for pat in patterns:
                    if re.search(pat, content):
                        return f"{fname}: {pat}"
    except Exception as e:
        logger.warning(f"_scan_for_stubs error: {e}")
    return None


def kill_dev_servers():
    os.system("pkill -f 'next dev' 2>/dev/null; pkill -f 'npm run dev' 2>/dev/null; "
              "pkill -f 'npm start' 2>/dev/null")


# =====================================================================
# OpenHands invocation — the one thing that's actually different from Hermes
# =====================================================================

def run_openhands(task_prompt, workdir):
    """
    Invoke OpenHands SDK v1.x CLI headless on `workdir` with `task_prompt`.

    Flags (per `openhands --help` at SDK 1.16.1):
      --headless              auto-approve all actions, no TUI
      --override-with-envs    pull LLM_MODEL/LLM_API_KEY/LLM_BASE_URL from env
                              (default behaviour IGNORES env; settings.json wins)
      -t TASK                 initial task prompt
      --exit-without-confirmation

    OpenHands takes cwd as its workspace — no --config-file flag in 1.x.
    Returns (returncode, stdout_tail, stderr_tail).
    """
    cmd = [
        "openhands",
        "--headless",
        "--override-with-envs",
        "--exit-without-confirmation",
        "-t", task_prompt,
    ]
    logger.info(f"Invoking OpenHands: cwd={workdir} model={LLM_MODEL} timeout={OPENHANDS_TIMEOUT}s")
    env = os.environ.copy()
    env["LLM_MODEL"] = LLM_MODEL
    env["LLM_API_KEY"] = LLM_API_KEY
    if LLM_BASE_URL:
        env["LLM_BASE_URL"] = LLM_BASE_URL
    env["OPENHANDS_SUPPRESS_BANNER"] = "1"
    # ANTHROPIC_API_KEY / OPENAI_API_KEY mirror for litellm's native paths
    if LLM_MODEL.startswith("anthropic/"):
        env.setdefault("ANTHROPIC_API_KEY", LLM_API_KEY)
    elif LLM_MODEL.startswith("openai/") or LLM_BASE_URL:
        env.setdefault("OPENAI_API_KEY", LLM_API_KEY)

    try:
        result = subprocess.run(
            cmd,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=OPENHANDS_TIMEOUT,
        )
        stdout_tail = (result.stdout or "")[-2000:]
        stderr_tail = (result.stderr or "")[-2000:]
        logger.info(f"OpenHands exit={result.returncode}")
        if stdout_tail:
            logger.info(f"OpenHands stdout tail:\n{stdout_tail}")
        if stderr_tail and result.returncode != 0:
            logger.warning(f"OpenHands stderr tail:\n{stderr_tail}")
        return result.returncode, stdout_tail, stderr_tail
    except subprocess.TimeoutExpired:
        logger.warning(f"OpenHands timed out after {OPENHANDS_TIMEOUT}s")
        kill_dev_servers()
        return -1, "", "timeout"
    except FileNotFoundError:
        logger.error("openhands CLI not on PATH — Dockerfile install may have failed")
        return -2, "", "openhands not found"
    except Exception as e:
        logger.error(f"OpenHands invocation raised: {type(e).__name__}: {e}")
        return -3, "", str(e)


# =====================================================================
# Task execution
# =====================================================================

def execute_task(task):
    task_id = task.get("id")
    title = task.get("title", "")
    desc = task.get("description", "")
    project = task.get("hatchery_projects", {}) or {}
    project_id = project.get("id") or task.get("project_id")
    repo_url = project.get("repo_url", "")
    slug = extract_slug(repo_url) or "unknown"
    workdir = f"/repos/{slug}"

    logger.info(f"Executing: {title!r} on {slug} via OpenHands [model={LLM_MODEL}]")

    try:
        # Force HTTPS clone URL so the credential helper works (matches Hermes behavior)
        https_url = repo_url
        if repo_url.startswith("git@github.com:"):
            https_url = "https://github.com/" + repo_url.split(":", 1)[1]

        if not os.path.exists(workdir):
            rc = os.system(f"git clone --depth 1 {https_url} {workdir}")
            if rc != 0:
                release_task(task_id, f"git clone failed for {https_url}")
                return
        else:
            os.system(f"cd {workdir} && git fetch origin main >/dev/null 2>&1 && "
                      f"git reset --hard origin/main >/dev/null 2>&1")

        if not LLM_API_KEY:
            release_task(task_id, "missing LLM_API_KEY env var")
            return

        if not title and not desc:
            hatchery_api("POST", f"agent/tasks/{task_id}/request-human",
                         {"comment": "empty title+description; need clarification"})
            return

        project_context = fetch_project_context(project_id)
        if project_context:
            logger.info(f"Fetched project context ({len(project_context)} chars) for project {project_id}")

        # The OpenHands prompt — let its internal loop handle edit/build/test.
        # We still inject Next.js conventions so PRs build on Vercel first try.
        prompt = f"""TASK: {title}

DESCRIPTION:
{desc}

{project_context}

WORKING DIRECTORY: {workdir} (already cloned, on main)

This is a Next.js 15 App Router + Tailwind v4 + React 19 project.
Follow these conventions BEFORE finishing:
- Add `"use client"` to any .tsx using useState/useEffect/onClick/useRouter.
- Pin `"next": "15.5.15"` in package.json (Vercel blocks older for CVE-2025-66478).
- Add `legacy-peer-deps=true` to .npmrc if using react-leaflet or similar.
- Dark theme: bg-[#0a0a0a], cards bg-[#141414], text text-white/90.
- NEVER submit placeholder stubs like `return <div></div>` or `// TODO`.

LOOP:
1. Read the existing code (src/app/page.tsx, package.json, etc).
2. Implement the task.
3. Run `npm install --legacy-peer-deps && npm run build`. If it fails, fix.
4. Repeat until build passes AND the VERIFY block at the end of DESCRIPTION is satisfied.

IMPORTANT: Do NOT run `npm run dev`, `npm start`, or any long-running command —
it will hang forever inside this container. Only use `npm run build` for verification.

Do NOT commit or push — the worker layer handles git. Just leave your changes staged
or unstaged in the working tree and exit when done.
"""

        rc, _stdout, _stderr = run_openhands(prompt, workdir)
        kill_dev_servers()

        # Self-heal the deltas OpenHands may have missed
        _pin_next_version(workdir)
        _ensure_npmrc_legacy_peer(workdir)
        _fix_use_client(workdir)

        # Detect whether OpenHands actually changed anything
        diff_check = subprocess.run(
            ["git", "-C", workdir, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if not (diff_check.stdout or "").strip():
            # Also check for staged commits on top of origin/main (OpenHands may have
            # committed locally — we'll undo those below but need to detect them now)
            log_check = subprocess.run(
                ["git", "-C", workdir, "log", "--oneline", "origin/main..HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if not (log_check.stdout or "").strip():
                logger.warning(f"OpenHands made no changes for {task_id}; releasing task")
                release_task(task_id, f"OpenHands exit={rc} produced no diff")
                return

        stub_flag = _scan_for_stubs(workdir)
        if stub_flag:
            logger.warning(f"Stub detected in {workdir}: {stub_flag}; releasing task")
            release_task(task_id, f"stub detected: {stub_flag}")
            return

        # PR flow: soft-reset to origin/main (preserves changes as staged), create
        # feature branch, commit, push, open PR. Mirrors Hermes worker exactly.
        branch = f"auto/{(task_id or 'notask')[:8]}"
        os.system(
            f"cd {workdir} && "
            f"git fetch origin main >/dev/null 2>&1 && "
            f"git reset --soft origin/main >/dev/null 2>&1 && "
            f"git checkout -B {branch} && "
            f"git add -A && "
            f"git -c user.email=frank.quy.nguyen@gmail.com -c user.name='Frank Nguyen' "
            f"commit -m 'feat: {title[:60]}' >/dev/null 2>&1; "
            f"git push -u origin {branch} --force-with-lease >/dev/null 2>&1"
        )

        commit_sha = ""
        try:
            commit_sha = subprocess.check_output(
                ["git", "-C", workdir, "rev-parse", "--short", "HEAD"], timeout=10
            ).decode().strip()
        except Exception:
            pass

        deployed_url = project.get("vercel_url") or project.get("url") or ""
        note = (
            f"[{WORKER_NAME}] built via OpenHands ({LLM_MODEL}) | "
            f"commit={commit_sha or 'n/a'} | url={deployed_url or 'n/a'} | "
            f"task={title[:80]}"
        )
        pr_title = f"[Hatchery/OpenHands] {title[:60]}"
        pr_body = (
            f"Automated PR from worker **{WORKER_NAME}** (framework: OpenHands, model: `{LLM_MODEL}`).\n\n"
            f"Task: `{task_id}`\n"
            f"Commit: `{commit_sha or 'n/a'}`\n"
            f"Deployed URL: {deployed_url or 'n/a'}\n\n"
            f"---\n\n{desc[:500]}"
        )
        pr_url = create_pr(slug, branch, pr_title, pr_body)

        if pr_url:
            resp, status = hatchery_api(
                "PATCH", f"agent/tasks/{task_id}",
                {"status": "review", "pr_url": pr_url,
                 "comment": f"PR opened: {pr_url} — awaiting auto-close on merge. {note}"},
                return_status=True,
            )
            if status in (200, 201, 204):
                logger.info(f"Task {task_id} marked review with pr_url={pr_url}")
            else:
                submit_for_qa(task_id, f"{note} | pr_url={pr_url}")
            hatchery_api("POST", "agent/messages", {
                "to_type": "broadcast", "message_type": "status_update",
                "content": f"[{WORKER_NAME}] PR opened: {title} on {project.get('name', '?')} "
                           f"({commit_sha}) → {pr_url}",
            })
            logger.info(f"PR opened for task: {title} → {pr_url}")
        else:
            logger.warning(f"PR creation failed for task {task_id}; submit_for_qa fallback")
            submit_for_qa(task_id, note)

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:150]}"
        logger.error(f"execute_task failed for {task_id}: {err}")
        if task_id:
            release_task(task_id, f"transient error: {err}")


# =====================================================================
# Capability advertisement + main loop
# =====================================================================

def advertise_capabilities():
    full = ["complex-ui", "simple-component", "recharts-chart", "api-route",
            "bugfix", "typescript", "debugging", "debug", "leaflet-map",
            "force-graph", "r3f-globe", "data-fetching", "data-viz",
            "frontend-nextjs", "frontend-dev"]
    try:
        hatchery_api("PATCH", "agent/capabilities", {"capabilities": full})
        logger.info(f"Capabilities advertised ({len(full)}): {full}")
    except Exception as e:
        logger.warning(f"Capability advertise failed: {e}")


def main():
    logger.info(f"Worker: {WORKER_NAME}")
    logger.info(f"Framework: OpenHands (headless)")
    logger.info(f"LLM: {LLM_MODEL}  base_url={LLM_BASE_URL or '<default>'}")
    logger.info(f"Hatchery: {HATCHERY_BASE}")

    # Sanity-check openhands CLI
    try:
        ver = subprocess.run(["openhands", "--version"], capture_output=True, text=True, timeout=10)
        logger.info(f"openhands --version: {(ver.stdout or ver.stderr).strip()[:200]}")
    except Exception as e:
        logger.warning(f"openhands CLI probe failed: {e}")

    advertise_capabilities()
    stale_claimed_reaper()

    running = True
    def shutdown(*_a):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while running:
        try:
            tasks = hatchery_api("GET", "agent/tasks/available").get("tasks", [])
            if tasks:
                task = tasks[0]
                project = task.get("hatchery_projects", {}) or {}
                slug = extract_slug(project.get("repo_url", ""))
                if slug and has_open_pr_from_self(slug):
                    logger.info(
                        f"Skipping {task.get('title','')[:50]!r}: "
                        f"{GITHUB_ORG}/{slug} has an open auto/* PR"
                    )
                else:
                    logger.info(f"Picked up: {task.get('title', '?')}")
                    hatchery_api("POST", f"agent/tasks/{task['id']}/claim")
                    execute_task(task)
        except Exception as e:
            logger.error(f"Poll error: {e}")
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
