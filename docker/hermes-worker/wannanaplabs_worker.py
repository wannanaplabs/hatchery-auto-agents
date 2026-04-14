#!/usr/bin/env python3
"""
WannaNapLabs Hermes Worker — Configurable brain + coding tool.

Supports multiple permutations:
  - MiniMax brain + Claude Code CLI (most powerful)
  - MiniMax brain + Ollama Qwen (free, local coding)
  - MiniMax brain + Ollama Gemma (free, local coding)
  - Qwen brain + Claude Code CLI (local orchestrator, cloud coder)
  - Gemma brain + Claude Code CLI (local orchestrator, cloud coder)
  - MiniMax brain + self (orchestrator writes code directly)

Environment variables:
  WORKER_NAME        — Name for this worker (default: hermes-worker)
  ORCHESTRATOR_MODEL — Model for the brain (default: MiniMax-M2.7)
  ORCHESTRATOR_URL   — API base URL (default: https://api.minimax.io/anthropic)
  ORCHESTRATOR_KEY   — API key for orchestrator
  CODING_TOOL        — "claude-cli", "ollama-qwen", "ollama-gemma", "ollama-deepseek", "self"
  CODING_MODEL       — Override model name for ollama coding tools
  OLLAMA_HOST        — Ollama host (default: host.docker.internal:11434)
  HATCHERY_API_KEY   — Hatchery API key
  HATCHERY_BASE_URL  — Hatchery base (default: https://hatchery.run)
  GITHUB_TOKEN       — GitHub token for pushing
  GITHUB_ORG         — GitHub org for repos/PRs (default: wannanaplabs)
  POLL_INTERVAL      — Seconds between polls (default: 30)

Flow (post-April 2026):
  1. Poll agent/tasks/available
  2. If repo has an open auto/* PR: skip (let prior PR land first)
  3. Claim task, run coding tool, self-heal, scan for stubs
  4. Push to feature branch auto/<task_id[:8]>
  5. Create PR via gh CLI
  6. PATCH task {status: review, pr_url: ...} — Hatchery auto-closes to 'done' on merge
  7. Fallback: if gh fails, use legacy submit_for_qa
"""

import os, sys, json, time, signal, logging, re, subprocess, urllib.request, urllib.error

sys.path.insert(0, "/opt/hermes")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

WORKER_NAME = os.environ.get("WORKER_NAME", "hermes-worker")
logger = logging.getLogger(WORKER_NAME)

HATCHERY_BASE = os.environ.get("HATCHERY_BASE_URL", "https://hatchery.run")
HATCHERY_KEY = os.environ.get("HATCHERY_API_KEY", "")
CODING_TOOL = os.environ.get("CODING_TOOL", "claude-cli")
CODING_MODEL = os.environ.get("CODING_MODEL", "")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "host.docker.internal:11434")


def _pin_next_version(workdir):
    """Force-pin next@15.5.15 in package.json (Vercel blocks CVE-2025-66478 on older)."""
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
    """Add legacy-peer-deps=true to .npmrc if missing (react-leaflet etc.)."""
    p = f"{workdir}/.npmrc"
    line = "legacy-peer-deps=true\n"
    try:
        if os.path.exists(p):
            with open(p) as f:
                existing = f.read()
            if "legacy-peer-deps" not in existing:
                with open(p, "a") as f:
                    f.write(line if existing.endswith("\n") or existing == "" else "\n" + line)
                logger.info(f"_ensure_npmrc_legacy_peer: appended to {p}")
        else:
            with open(p, "w") as f:
                f.write(line)
            logger.info(f"_ensure_npmrc_legacy_peer: created {p}")
    except Exception as e:
        logger.warning(f"npmrc fix failed: {e}")


def _fix_use_client(workdir):
    """Prepend 'use client' to src/app/page.tsx if it uses client-only hooks."""
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
    """Scan src/ for red-flag stub patterns. Returns a short description or None."""
    patterns = [
        r"return\s*<div\s*/?>\s*</div>",
        r"return\s*<div\s*/>",
        r"//\s*TODO(?!.*task)",
        r"//\s*In production,?\s+this\s+would",
        r"/\*\s*TODO\s*\*/",
    ]
    root_dir = f"{workdir}/src"
    if not os.path.isdir(root_dir):
        return None
    try:
        for root, dirs, files in os.walk(root_dir):
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
    """Fetch project digest + spec and return a short combined context string."""
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


def submit_for_qa(task_id, note):
    """Try submit-for-qa first; fall back to PATCH status=done on 404/405."""
    resp, status = hatchery_api(
        "POST", f"agent/tasks/{task_id}/submit-for-qa",
        {"note": note}, return_status=True,
    )
    if status in (200, 201, 202, 204):
        logger.info(f"Submitted task {task_id} for QA (HTTP {status})")
        return True
    if status in (404, 405):
        logger.info(f"submit-for-qa not available (HTTP {status}); falling back to PATCH done")
        hatchery_api("PATCH", f"agent/tasks/{task_id}", {"status": "done"})
        return True
    # Other errors: still fall back to avoid leaving task claimed
    logger.warning(f"submit-for-qa returned HTTP {status}; falling back to PATCH done")
    hatchery_api("PATCH", f"agent/tasks/{task_id}", {"status": "done"})
    return False


def release_task(task_id, reason):
    """Release a claimed task back to the pool.

    Uses PATCH status=ready instead of POST /release because the latter sets
    last_failed_by=<agent_id>, which makes the task invisible to the SAME
    agent via /tasks/available. Since all workers share the Goop identity,
    /release would create a perma-block. PATCH status=ready has no blame."""
    try:
        hatchery_api("PATCH", f"agent/tasks/{task_id}", {
            "status": "ready",
            "comment": f"released by {WORKER_NAME}: {reason[:200]}",
            "assignee_agent_id": None,
        })
        logger.info(f"Released task {task_id}: {reason[:80]}")
    except Exception as e:
        logger.warning(f"Release failed for {task_id}: {e}")


def request_human(task_id, reason):
    """Escalate an ambiguous task to a human."""
    try:
        hatchery_api("POST", f"agent/tasks/{task_id}/request-human", {"comment": reason[:200]})
        logger.info(f"Requested human review on {task_id}: {reason[:80]}")
    except Exception as e:
        logger.warning(f"request-human failed for {task_id}: {e}")


def stale_claimed_reaper():
    """Release tasks in 'claimed' state owned by this agent with no update >15min ago."""
    try:
        resp = hatchery_api("GET", f"agent/tasks/search?status=claimed&agent_id={WORKER_NAME}")
        tasks = resp.get("tasks", []) if isinstance(resp, dict) else []
        if not tasks:
            # Fallback: some deployments expose claimed tasks via agent/tasks/claimed
            alt = hatchery_api("GET", "agent/tasks/claimed")
            tasks = alt.get("tasks", []) if isinstance(alt, dict) else []
        cutoff = time.time() - 15 * 60
        released = 0
        for t in tasks:
            if t.get("claimed_by") not in (None, WORKER_NAME) and t.get("agent_id") not in (None, WORKER_NAME):
                continue
            ts = t.get("updated_at") or t.get("claimed_at") or ""
            try:
                # ISO 8601 e.g. 2026-04-13T10:00:00Z
                from datetime import datetime
                iso = ts.replace("Z", "+00:00") if isinstance(ts, str) else ""
                dt = datetime.fromisoformat(iso).timestamp() if iso else 0
            except Exception:
                dt = 0
            if dt and dt < cutoff:
                release_task(t.get("id"), "startup: stale claim >15min, releasing for retry")
                released += 1
        if released:
            logger.info(f"Stale-claimed reaper released {released} task(s)")
        else:
            logger.info("Stale-claimed reaper: nothing to release")
    except Exception as e:
        logger.warning(f"stale_claimed_reaper error: {e}")


GITHUB_ORG = os.environ.get("GITHUB_ORG", "wannanaplabs")


def extract_slug(repo_url):
    """Return the repo slug (last path segment, .git stripped) or empty string."""
    if not repo_url:
        return ""
    s = repo_url.rstrip("/").split("/")[-1]
    if s.endswith(".git"):
        s = s[:-4]
    return s


def has_open_pr_from_self(slug):
    """Return True if <org>/<slug> has an open PR on a branch named auto/*."""
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
    """Create a PR via gh CLI. Returns the PR URL (str) or empty string on failure."""
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


def kill_dev_servers():
    """Kill any stray dev-server processes the coding tool may have left running."""
    os.system("pkill -f 'next dev' 2>/dev/null; pkill -f 'npm run dev' 2>/dev/null")


def build_coding_command(task_prompt, workdir):
    """Build the terminal command for the coding tool."""
    escaped = task_prompt.replace("'", "'\\''")

    if CODING_TOOL == "claude-cli":
        return (
            f"cd {workdir} && claude -p --dangerously-skip-permissions "
            f"'{escaped}' --model claude-sonnet-4-5"
        )

    elif CODING_TOOL.startswith("ollama-"):
        model = CODING_MODEL
        if not model:
            variant = CODING_TOOL.replace("ollama-", "")
            model = {"qwen": "qwen2.5:7b", "gemma": "gemma4:latest", "deepseek": "deepseek-r1:8b"}.get(variant, variant)

        system_msg = (
            "You are a coding agent. Output ONLY a JSON manifest: "
            '{"files": [{"path": "...", "content": "..."}]}. No explanations.'
        )
        escaped_system = system_msg.replace('"', '\\"')
        escaped_user = task_prompt.replace('"', '\\"').replace("'", "'\\''")

        # Call Ollama, parse response, write files
        return (
            f"cd {workdir} && python3 -c \""
            f"import urllib.request, json, os; "
            f"r = urllib.request.urlopen(urllib.request.Request("
            f"'http://{OLLAMA_HOST}/api/chat', "
            f"data=json.dumps({{"
            f"'model':'{model}',"
            f"'messages':["
            f"{{'role':'system','content':'{escaped_system}'}},"
            f"{{'role':'user','content':'{escaped_user}'}}"
            f"],'stream':False}}).encode(), "
            f"headers={{'Content-Type':'application/json'}}), timeout=300); "
            f"data=json.loads(r.read()); "
            f"content=data.get('message',{{}}).get('content',''); "
            f"print(content[:200]); "
            # Parse and write files from JSON manifest
            f"import re; "
            f"m=re.search(r'\\{{.*\\\"files\\\".*\\}}', content, re.DOTALL); "
            f"files=json.loads(m.group()).get('files',[]) if m else []; "
            f"[os.makedirs(os.path.dirname(os.path.join('{workdir}',f['path'])),exist_ok=True) or "
            f"open(os.path.join('{workdir}',f['path']),'w').write(f['content']) for f in files]; "
            f"print(f'Wrote {{len(files)}} files')"
            f"\""
        )

    elif CODING_TOOL == "self":
        return None

    else:
        logger.warning(f"Unknown CODING_TOOL: {CODING_TOOL}")
        return None


def execute_task(task):
    """Execute a Hatchery task using the Hermes agent loop."""
    task_id = task.get("id")
    try:
        from run_agent import AIAgent
    except ImportError:
        logger.error("Cannot import Hermes AIAgent")
        if task_id:
            release_task(task_id, "worker import error: Hermes AIAgent unavailable")
        return

    title = task.get("title", "")
    desc = task.get("description", "")
    project = task.get("hatchery_projects", {}) or {}
    project_id = project.get("id") or task.get("project_id")
    repo_url = project.get("repo_url", "")
    slug = repo_url.rstrip("/").split("/")[-1] if repo_url else "unknown"
    workdir = f"/repos/{slug}"

    logger.info(f"Executing: {title} on {slug} [coding: {CODING_TOOL}]")

    try:
        if not os.path.exists(workdir):
            os.system(f"git clone --depth 1 {repo_url} {workdir}")
        else:
            os.system(f"cd {workdir} && git pull origin main 2>/dev/null")

        # NEW: fetch project-level context (digest + spec) and prepend to prompt
        project_context = fetch_project_context(project_id)
        if project_context:
            logger.info(f"Fetched project context ({len(project_context)} chars) for project {project_id}")

        full_coding_prompt = (
            f"{title}\n\n{desc}\n\n"
            f"{project_context}\n\n"
            "CRITICAL: This is a Next.js 15 App Router + Tailwind v4 + React 19 project. "
            "Add 'use client' to any page using useState/useEffect/onClick/useRouter. "
            "Pin next@15.5.15 in package.json. Install with --legacy-peer-deps. "
            "NEVER produce stubs or placeholder returns. The deployed site MUST satisfy the VERIFY block at the end of the DESCRIPTION."
        )
        coding_cmd = build_coding_command(full_coding_prompt, workdir)

        orch_url = os.environ.get("ORCHESTRATOR_URL", "https://api.minimax.io/anthropic")
        orch_key = os.environ.get("ORCHESTRATOR_KEY", os.environ.get("MINIMAX_API_KEY", ""))
        orch_model = os.environ.get("ORCHESTRATOR_MODEL", "MiniMax-M2.7")

        # Guard: missing orchestrator key → release with cooldown note
        if not orch_key:
            release_task(task_id, "missing ORCHESTRATOR_KEY/MINIMAX_API_KEY env var")
            return

        # Guard: ambiguous spec → escalate to human
        if not title and not desc:
            request_human(task_id, "empty title and description; need clarification")
            return

        agent = AIAgent(
            base_url=orch_url,
            api_key=orch_key,
            model=orch_model,
            max_iterations=25,
            enabled_toolsets=["terminal", "file"],
            quiet_mode=True,
            tool_delay=0.5,
        )

        if coding_cmd:
            fix_cmd = build_coding_command("Fix all build errors in this Next.js project", workdir) or ""
            steps = f"""STEPS:
1. terminal(command="cd {workdir} && npm install 2>/dev/null", timeout=60)
2. terminal(command="{coding_cmd}", timeout=300)
3. terminal(command="cd {workdir} && npm run build", timeout=120)
4. If build fails: terminal(command="{fix_cmd}", timeout=300)
5. terminal(command="cd {workdir} && git add -A && git commit --author='Frank Nguyen <frank.quy.nguyen@gmail.com>' -m 'feat: {title[:50]}' && git push origin main", timeout=60)"""
        else:
            steps = f"""STEPS (you write the code yourself using file tools):
1. read_file(path="{workdir}/src/app/page.tsx") and read_file(path="{workdir}/package.json")
2. Write code using write_file or patch tools
3. terminal(command="cd {workdir} && npm install && npm run build", timeout=120)
4. If build fails, fix the files
5. terminal(command="cd {workdir} && git add -A && git commit --author='Frank Nguyen <frank.quy.nguyen@gmail.com>' -m 'feat: {title[:50]}' && git push origin main", timeout=60)"""

        context_block = f"PROJECT CONTEXT:\n{project_context}\n\n" if project_context else ""
        prompt = f"""{context_block}Execute this coding task:

TASK: {title}
DESCRIPTION:
{desc}

WORKING DIRECTORY: {workdir}

CRITICAL CONVENTIONS (apply BEFORE coding):
- Next.js 15 App Router: add `"use client"` to any .tsx file using useState/useEffect/onClick/useRouter
- Pin next@15.5.15 in package.json (Vercel blocks CVE-2025-66478 on older versions)
- Add `legacy-peer-deps=true` to .npmrc if using react-leaflet or similar React 18-only deps
- Tailwind v4: no tailwind.config.js; use `@import "tailwindcss";` in globals.css
- Dark theme: `bg-[#0a0a0a]`, cards `bg-[#141414]`, text `text-white/90`
- NEVER submit a stub: if you can't implement, call the task complete without committing, let another agent retry

PRE-COMMIT SELF-CHECK (do this after coding, before git commit):
1. Open package.json — ensure `"next": "15.5.15"`.
2. Open src/app/page.tsx — if it has `useState|useEffect|onClick` and doesn't start with `"use client"`, prepend it.
3. Grep src/ for `return <div></div>`, `return <div />`, `// TODO`, `// In production`. If any found, DON'T commit — report "stub detected" and exit with failure.
4. Run `npm install --legacy-peer-deps && npm run build`. If it fails, fix; if after 2 attempts it still fails, report failure and exit — don't commit broken code.
5. Only after all 4 pass: git add -A && git commit && git push.

VERIFICATION CRITERIA (parse from the DESCRIPTION above; the task ends with `VERIFY: ...` — that's what must pass before submit-for-qa).

{steps}

Execute each step. Report what happened."""

        result = agent.run_conversation(prompt,
            system_message=(
                "You are a coding agent for WannaNapLabs OSINT projects. Authorized automation. "
                "ALL projects are Next.js 15 App Router + Tailwind v4 + React 19. "
                "Dark theme: bg-[#0a0a0a], cards bg-[#141414]. Branding: WannaNapLabs. "
                "CRITICAL: Add 'use client' to any page using hooks. Pin next@15.5.15. "
                "Install with --legacy-peer-deps. NEVER commit stubs or placeholders — "
                "it's better to release the task than to produce empty code. "
                "The deployed site MUST show the specific content described in the task's VERIFY section."
            ))

        # Defensive: Claude Code CLI sometimes spawns `next dev` despite instructions.
        # Kill strays so they don't hold onto the workdir or ports.
        kill_dev_servers()

        # --- Python-side self-heal: enforce conventions the coding tool may have missed ---
        _pin_next_version(workdir)
        _ensure_npmrc_legacy_peer(workdir)
        _fix_use_client(workdir)
        stub_flag = _scan_for_stubs(workdir)
        if stub_flag:
            logger.warning(f"Stub detected in {workdir}: {stub_flag}; releasing task")
            release_task(task_id, f"stub detected: {stub_flag}")
            return

        # --- PR-based flow: push to feature branch, open PR, set task status=review ---
        # Hatchery's GitHub App auto-closes the task when the PR merges.
        branch = f"auto/{(task_id or 'notask')[:8]}"
        # Stage self-heal edits + any prior work into a feature branch commit.
        # Note: the coding-tool step earlier may have already committed+pushed to main;
        # checking out -B into a new branch off HEAD keeps those commits on the branch too.
        os.system(
            f"cd {workdir} && git checkout -B {branch} && "
            f"git add -A && "
            f"git -c user.email=frank.quy.nguyen@gmail.com -c user.name='Frank Nguyen' "
            f"commit --allow-empty -m 'self-heal: pin next/use-client/npmrc' >/dev/null 2>&1; "
            f"git push -u origin {branch} --force-with-lease >/dev/null 2>&1"
        )

        # Capture commit SHA and deployed URL best-effort
        commit_sha = ""
        try:
            commit_sha = subprocess.check_output(
                ["git", "-C", workdir, "rev-parse", "--short", "HEAD"], timeout=10
            ).decode().strip()
        except Exception:
            pass
        deployed_url = project.get("vercel_url") or project.get("url") or ""
        note = (
            f"[{WORKER_NAME}] built via {CODING_TOOL} | "
            f"commit={commit_sha or 'n/a'} | url={deployed_url or 'n/a'} | "
            f"task={title[:80]}"
        )

        pr_title = f"[Hatchery] {title[:60]}"
        pr_body = (
            f"Automated PR from worker **{WORKER_NAME}** (coding tool: `{CODING_TOOL}`).\n\n"
            f"Task: `{task_id}`\n"
            f"Commit: `{commit_sha or 'n/a'}`\n"
            f"Deployed URL: {deployed_url or 'n/a'}\n\n"
            f"---\n\n{desc[:500]}"
        )
        pr_url = create_pr(slug, branch, pr_title, pr_body)

        if pr_url:
            # Happy path: let Hatchery's auto-close-on-merge drive the task to done.
            resp, status = hatchery_api(
                "PATCH", f"agent/tasks/{task_id}",
                {
                    "status": "review",
                    "pr_url": pr_url,
                    "comment": f"PR opened: {pr_url} — awaiting auto-close on merge. {note}",
                },
                return_status=True,
            )
            if status in (200, 201, 204):
                logger.info(f"Task {task_id} marked review with pr_url={pr_url}")
            else:
                logger.warning(f"PATCH status=review returned HTTP {status}; falling back to submit_for_qa")
                submit_for_qa(task_id, f"{note} | pr_url={pr_url}")

            hatchery_api("POST", "agent/messages", {
                "to_type": "broadcast", "message_type": "status_update",
                "content": f"[{WORKER_NAME}] PR opened: {title} on {project.get('name', '?')} "
                           f"({commit_sha}) → {pr_url}",
            })
            logger.info(f"PR opened for task: {title} → {pr_url}")
        else:
            # Fallback: couldn't create a PR (e.g. one already exists on this branch, or gh CLI missing).
            # Use legacy submit-for-qa so the task doesn't stay claimed forever.
            logger.warning(f"PR creation failed for task {task_id}; using legacy submit_for_qa fallback")
            submit_for_qa(task_id, note)
            hatchery_api("POST", "agent/messages", {
                "to_type": "broadcast", "message_type": "status_update",
                "content": f"[{WORKER_NAME}] Submitted for QA (PR fallback): {title} on "
                           f"{project.get('name', '?')} ({commit_sha})",
            })
            logger.info(f"Task submitted for QA (PR fallback): {title}")

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:150]}"
        logger.error(f"execute_task failed for {task_id}: {err}")
        if task_id:
            release_task(task_id, f"transient error: {err}")


def advertise_capabilities():
    """Advertise the full cap set. All workers share one agent identity (Goop key),
    so per-worker tiers would conflict — last writer wins and shrinks visibility.
    Workers that can't actually handle complex-ui will fail fast and release the task."""
    full = ["complex-ui", "simple-component", "recharts-chart", "api-route",
            "bugfix", "typescript", "debugging", "debug", "leaflet-map",
            "force-graph", "r3f-globe", "data-fetching", "data-viz",
            "frontend-nextjs", "frontend-dev"]
    try:
        hatchery_api("PATCH", "agent/capabilities", {"capabilities": full})
        logger.info(f"Capabilities advertised ({len(full)}): {full}")
    except Exception as e:
        logger.warning(f"Capability advertise failed: {e}")
        return {}


def main():
    logger.info(f"Worker: {WORKER_NAME}")
    logger.info(f"Orchestrator: {os.environ.get('ORCHESTRATOR_MODEL', 'MiniMax-M2.7')}")
    logger.info(f"Coding tool: {CODING_TOOL}")
    logger.info(f"Hatchery: {HATCHERY_BASE}")
    advertise_capabilities()
    stale_claimed_reaper()

    running = True
    def shutdown(*a):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))

    while running:
        try:
            tasks = hatchery_api("GET", "agent/tasks/available").get("tasks", [])
            if tasks:
                task = tasks[0]
                project = task.get("hatchery_projects", {}) or {}
                slug = extract_slug(project.get("repo_url", ""))
                # PR-freshness guard: if the repo already has an open auto/* PR, skip so
                # we don't race with a pending review and overwrite the branch.
                if slug and has_open_pr_from_self(slug):
                    logger.info(
                        f"Skipping task {task.get('title','')[:50]!r}: "
                        f"{GITHUB_ORG}/{slug} has an open auto/* PR; waiting for it to land"
                    )
                else:
                    logger.info(f"Picked up: {task.get('title', '?')}")
                    hatchery_api("POST", f"agent/tasks/{task['id']}/claim")
                    execute_task(task)
        except Exception as e:
            logger.error(f"Error: {e}")
        for _ in range(poll_interval):
            if not running: break
            time.sleep(1)

if __name__ == "__main__":
    main()
