#!/usr/bin/env python3
"""Multi-layer QA reviewer for Hatchery tasks.

Drains the review queue by performing deterministic verification:
  1. Vercel deploy state (must be READY + newer than task updated_at)
  2. Live HTML fetch + stub-marker / size / </html> sanity checks
  3. VERIFY-block grep pattern extraction + match against deployed HTML
  4. /api/* routes mentioned in description -> hit, expect 2xx + non-trivial body
  5. Latest commit diff scan for red-flag stubs (TODO / <div></div> / etc)

Stdlib only. Single file. Safe on per-task errors.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HATCHERY_KEY = os.environ.get("HATCHERY_API_KEY", "")
HATCHERY_BASE = os.environ.get(
    "HATCHERY_BASE_URL", "https://hatchery-tau.vercel.app"
) + "/api/v1"
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN", "")
VERCEL_TEAM = os.environ.get("VERCEL_TEAM", "")

if not HATCHERY_KEY or not VERCEL_TOKEN or not VERCEL_TEAM:
    sys.stderr.write(
        "Missing required env vars: HATCHERY_API_KEY, VERCEL_TOKEN, VERCEL_TEAM\n"
    )
    sys.exit(1)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
VERCEL_TEAM_SLUG = os.environ.get("VERCEL_TEAM_SLUG", "wannanaplabs")

VERBOSE = False


def _http(method, url, headers=None, body=None, timeout=20, raw=False):
    data = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload.decode("utf-8", "replace")
            text = payload.decode("utf-8")
            return r.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        raw_body = e.read().decode("utf-8", "replace")
        if raw:
            return e.code, raw_body
        try:
            return e.code, json.loads(raw_body)
        except Exception:
            return e.code, {"error": raw_body[:300]}
    except Exception as e:
        return 0, ("" if raw else {"error": str(e)})


def hatchery(method, path, body=None):
    return _http(
        method,
        f"{HATCHERY_BASE}{path}",
        headers={"Authorization": f"Bearer {HATCHERY_KEY}"},
        body=body,
    )


def vercel(path):
    sep = "&" if "?" in path else "?"
    url = f"https://api.vercel.com{path}{sep}teamId={VERCEL_TEAM}"
    return _http("GET", url, headers={"Authorization": f"Bearer {VERCEL_TOKEN}"})


def slug_from_repo(repo_url):
    if not repo_url:
        return None
    m = re.search(r"github\.com[:/][^/]+/([^/.]+)", repo_url)
    return m.group(1) if m else None


def iso_to_ms(s):
    if not s:
        return 0
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0


def latest_deploy_for_slug(slug):
    code, proj = vercel(f"/v9/projects/{slug}?")
    if code != 200 or not isinstance(proj, dict) or "id" not in proj:
        return None, f"project_not_found({code})"
    pid = proj["id"]
    code, deps = vercel(f"/v6/deployments?projectId={pid}&limit=3")
    if code != 200:
        return None, f"deploy_list_failed({code})"
    items = deps.get("deployments") or []
    if not items:
        return None, "no_deployments"
    d = items[0]
    url = d.get("url") or d.get("alias", [None])[0]
    if isinstance(d.get("alias"), list) and d["alias"]:
        url = d["alias"][0]
    return {
        "state": (d.get("readyState") or d.get("state") or "UNKNOWN"),
        "createdAt": d.get("createdAt") or d.get("created") or 0,
        "uid": d.get("uid"),
        "url": url,
    }, None


# ---------- verification layers ----------

VERIFY_PATTERNS = [
    re.compile(r"grep\s+-[EFi]*\s*['\"]([^'\"]+)['\"]", re.I),
    re.compile(r"grep\s+['\"]([^'\"]+)['\"]", re.I),
    re.compile(r"curl[^|]*\|\s*grep\s+[^'\"]*['\"]([^'\"]+)['\"]", re.I),
    re.compile(r"must\s+(?:show|match|contain|include)\s+['\"]([^'\"\.]+)['\"]", re.I),
]
API_ROUTE_RE = re.compile(r"/api/[A-Za-z0-9_\-/\[\]]+")


def extract_verify_patterns(description):
    if not description:
        return []
    pats = []
    for line in description.splitlines():
        if "VERIFY" not in line and "verify" not in line:
            continue
        for rx in VERIFY_PATTERNS:
            for m in rx.finditer(line):
                pat = m.group(1).strip()
                if pat and len(pat) < 200 and pat not in pats:
                    pats.append(pat)
    # Also scan the whole description for grep/curl grep lines outside VERIFY
    if not pats:
        for rx in VERIFY_PATTERNS:
            for m in rx.finditer(description):
                pat = m.group(1).strip()
                if pat and len(pat) < 200 and pat not in pats:
                    pats.append(pat)
    return pats[:5]


def extract_api_routes(description):
    if not description:
        return []
    routes = []
    for m in API_ROUTE_RE.finditer(description):
        r = m.group(0).rstrip(".,);:'\"`")
        # strip dynamic segment placeholders
        r = re.sub(r"\[[^\]]+\]", "x", r)
        if r not in routes and len(r) < 120:
            routes.append(r)
    return routes[:5]


def candidate_urls(slug, deploy_url):
    urls = []
    if deploy_url:
        if not deploy_url.startswith("http"):
            deploy_url = "https://" + deploy_url
        urls.append(deploy_url)
    urls.append(f"https://{slug}-{VERCEL_TEAM_SLUG}.vercel.app")
    urls.append(f"https://{slug}.vercel.app")
    # dedupe preserving order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_html(urls):
    headers = {"User-Agent": "Mozilla/5.0 QA-reviewer"}
    last = (None, 0, "")
    for u in urls:
        code, body = _http("GET", u, headers=headers, timeout=15, raw=True)
        b = body if isinstance(body, str) else ""
        last = (u, code, b)
        if code == 200 and len(b) > 200:
            return last
    return last


def html_sanity(html):
    markers = []
    size = len(html or "")
    low = (html or "").lower()
    if size < 3000:
        markers.append(f"small({size}b)")
    if "</html>" not in low:
        markers.append("no_html_close")
    if "Create Next App" in (html or ""):
        markers.append("nextjs_scaffold")
    if "coming soon" in low:
        markers.append("coming_soon")
    if "lorem ipsum" in low:
        markers.append("lorem_ipsum")
    # excessive loading
    loading_ct = low.count("loading...")
    if loading_ct > 5:
        markers.append(f"loading_x{loading_ct}")
    # lots of empty divs in a row
    if re.search(r"(?:<div></div>\s*){3,}", html or ""):
        markers.append("empty_divs")
    return markers, size


def verify_greps(html, patterns):
    hits, misses = [], []
    if not patterns:
        return hits, misses
    for p in patterns:
        try:
            rx = re.compile(p, re.I)
            if rx.search(html or ""):
                hits.append(p)
            else:
                misses.append(p)
        except re.error:
            # literal fallback
            if p.lower() in (html or "").lower():
                hits.append(p)
            else:
                misses.append(p)
    return hits, misses


def hit_api_routes(site_base, routes):
    results = []
    headers = {"User-Agent": "Mozilla/5.0 QA-reviewer"}
    for r in routes:
        url = site_base.rstrip("/") + r
        code, body = _http("GET", url, headers=headers, timeout=12, raw=True)
        ok = code in (200, 201) and body and len(body) > 50 and body.strip() not in ("[]", "{}")
        results.append({"route": r, "status": code, "len": len(body or ""), "ok": bool(ok)})
    return results


DIFF_RED_FLAGS = [
    (re.compile(r"return\s*<div\s*/>\s*;"), "return <div />"),
    (re.compile(r"return\s*\(\s*<div>\s*</div>\s*\)"), "return <div></div>"),
    (re.compile(r"return\s*<div>\s*</div>"), "return <div></div>"),
    (re.compile(r"//\s*TODO\b"), "// TODO"),
    (re.compile(r"//\s*FIXME\b"), "// FIXME"),
    (re.compile(r"//\s*In\s+production,?\s+this\s+would", re.I), "// In production, this would"),
    (re.compile(r"/\*\s*TODO\s*\*/"), "/* TODO */"),
]


def scan_latest_commit(slug, branch="main"):
    repo = f"{VERCEL_TEAM_SLUG}/{slug}"
    patch = ""
    try:
        p = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{branch}",
             "-H", "Accept: application/vnd.github.v3.diff"],
            capture_output=True, text=True, timeout=15,
        )
        if p.returncode == 0 and p.stdout:
            patch = p.stdout
    except Exception:
        pass
    if not patch and GITHUB_TOKEN:
        code, raw = _http(
            "GET", f"https://api.github.com/repos/{repo}/commits/{branch}",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                     "Accept": "application/vnd.github.v3.diff"},
            timeout=15, raw=True,
        )
        if code == 200 and isinstance(raw, str):
            patch = raw
    if not patch:
        return None, []
    added = "\n".join(
        line[1:] for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    flags = [label for rx, label in DIFF_RED_FLAGS if rx.search(added)]
    return True, flags


# ---------- hatchery mutations ----------

def approve(task_id, note):
    code, body = hatchery(
        "PATCH",
        f"/agent/tasks/{task_id}",
        body={"status": "done", "comment": f"auto-QA: {note}"},
    )
    return code in (200, 204), code, body


def reject(task_id, reason):
    code, body = hatchery(
        "PATCH",
        f"/agent/tasks/{task_id}",
        body={"status": "ready", "comment": f"QA rejected: {reason}"},
    )
    return code in (200, 204), code, body


# ---------- orchestrator ----------

def _do_reject(task, title, slug, reason, bucket, tally, reason_counts, proj_rejects):
    ok, c, _ = reject(task["id"], reason)
    if ok:
        print(f"[auto-QA] {title} -> reject ({reason})")
        tally["rejected"] += 1
        reason_counts[bucket] = reason_counts.get(bucket, 0) + 1
        proj_rejects[slug] = proj_rejects.get(slug, 0) + 1
    else:
        print(f"[auto-QA] {title} -> error (reject http {c})")
        tally["errors"] += 1


def review_task(task, projects, tally, reason_counts, proj_rejects):
    title = (task.get("title") or "")[:50]
    proj = projects.get(task.get("project_id"))
    if not proj:
        print(f"[auto-QA] {title} -> skip (project not loaded)")
        tally["skipped"] += 1
        return
    slug = slug_from_repo(proj.get("repo_url"))
    if not slug:
        print(f"[auto-QA] {title} -> skip (no slug in {proj.get('repo_url')})")
        tally["skipped"] += 1
        return

    dep, err = latest_deploy_for_slug(slug)
    if err:
        print(f"[auto-QA] {title} -> skip ({slug}: {err})")
        tally["skipped"] += 1
        return

    task_ms = iso_to_ms(task.get("updated_at"))
    dep_ms = int(dep["createdAt"] or 0)
    state = str(dep["state"]).upper()
    new_deploy = dep_ms > task_ms

    if VERBOSE:
        print(f"[auto-QA] [{title}]")
        print(f"  deploy: {slug} {state} (new:{new_deploy})")

    if not new_deploy:
        print(f"[auto-QA] {title} -> skip ({slug}: no new deploy; dep={state})")
        tally["skipped"] += 1
        return

    if state != "READY":
        _do_reject(task, title, slug, f"Vercel deploy {state}",
                   "deploy_state", tally, reason_counts, proj_rejects)
        return

    description = task.get("description") or ""
    verify_pats = extract_verify_patterns(description)
    api_routes = extract_api_routes(description)

    urls = candidate_urls(slug, dep.get("url"))
    fetched_url, _code, html = fetch_html(urls)
    markers, size = html_sanity(html)
    if VERBOSE:
        print(f"  html: {size/1024.0:.1f}KB, markers={markers}")

    hard = [m for m in markers if m in ("nextjs_scaffold", "coming_soon", "lorem_ipsum")]
    bad_shape = any(m.startswith("small(") or m == "no_html_close" for m in markers)
    if hard or bad_shape:
        _do_reject(task, title, slug, f"Stub page: markers={markers} size={size}",
                   "stub_markers", tally, reason_counts, proj_rejects)
        return

    hits, misses = verify_greps(html, verify_pats)
    if VERBOSE:
        if verify_pats:
            print(f"  verify: {verify_pats} -> {len(hits)}/{len(verify_pats)} match")
        else:
            print("  verify: (no criteria) [no_verify_criteria]")
    if verify_pats and misses:
        _do_reject(task, title, slug, f"VERIFY grep failed: missing {misses[0]!r}",
                   "verify_grep", tally, reason_counts, proj_rejects)
        return

    api_results = []
    if api_routes and fetched_url:
        m = re.match(r"(https?://[^/]+)", fetched_url)
        base = m.group(1) if m else fetched_url
        api_results = hit_api_routes(base, api_routes)
    if VERBOSE:
        if api_results:
            summary = ", ".join(f"{r['route']}={r['status']}" for r in api_results)
            print(f"  apis: {summary}")
        else:
            print("  apis: (none mentioned)")
    failed_api = [r for r in api_results if not r["ok"]]
    if failed_api:
        r0 = failed_api[0]
        _do_reject(task, title, slug,
                   f"API {r0['route']} returns {r0['status']} (len={r0['len']})",
                   "api_failure", tally, reason_counts, proj_rejects)
        return

    available, flags = scan_latest_commit(slug)
    if VERBOSE:
        if available is None:
            print("  diff: unavailable (no gh/GITHUB_TOKEN)")
        elif flags:
            print(f"  diff: red flags={flags}")
        else:
            print("  diff: no red flags")

    if flags:
        _do_reject(task, title, slug, f"Stub code detected: {flags[0]}",
                   "diff_flags", tally, reason_counts, proj_rejects)
        return

    assertions = 1 + (len(hits) if verify_pats else 0) + sum(1 for r in api_results if r["ok"])
    note = f"deploy=READY, verify OK, {assertions} assertions passed"
    ok, c, _ = approve(task["id"], note)
    if ok:
        print(f"[auto-QA] {title} -> approve ({slug} {note})")
        tally["approved"] += 1
    else:
        print(f"[auto-QA] {title} -> error (approve http {c})")
        tally["errors"] += 1


def main_once():
    code, body = hatchery("GET", "/agent/tasks/search?limit=200")
    if code != 200:
        print(f"[auto-QA] task fetch failed: {code} {body}")
        return {"approved": 0, "rejected": 0, "skipped": 0, "errors": 1}
    tasks = [t for t in body.get("tasks", []) if t.get("status") == "review"]
    code, pbody = hatchery("GET", "/agent/projects")
    projects = {p["id"]: p for p in pbody.get("projects", [])} if code == 200 else {}

    tally = {"approved": 0, "rejected": 0, "skipped": 0, "errors": 0}
    reason_counts = {}
    proj_rejects = {}
    for t in tasks:
        title = (t.get("title") or "")[:50]
        try:
            review_task(t, projects, tally, reason_counts, proj_rejects)
        except Exception as e:
            print(f"[auto-QA] {title} -> error ({e})")
            tally["errors"] += 1

    print(f"[auto-QA] tally: {tally}")
    if reason_counts:
        r_summary = ", ".join(f"{k}={v}" for k, v in sorted(reason_counts.items(), key=lambda x: -x[1]))
    else:
        r_summary = "(none)"
    worst = sorted(proj_rejects.items(), key=lambda x: -x[1])[:3]
    w_summary = ", ".join(f"{s}({n})" for s, n in worst) if worst else "(none)"
    print("[auto-QA] pass complete:")
    print(f"  approved: {tally['approved']} | rejected: {tally['rejected']} | skipped: {tally['skipped']}")
    print(f"  rejection reasons: {r_summary}")
    print(f"  worst projects by rejection: {w_summary}")
    return tally


def main():
    global VERBOSE
    args = sys.argv[1:]
    if "--verbose" in args:
        VERBOSE = True
        args.remove("--verbose")
    loop_n = 0
    if "--loop" in args:
        i = args.index("--loop")
        try:
            loop_n = int(args[i + 1])
        except (IndexError, ValueError):
            loop_n = 120
    if loop_n <= 0:
        main_once()
        return
    while True:
        try:
            main_once()
        except Exception as e:
            print(f"[auto-QA] loop error: {e}")
        time.sleep(loop_n)


if __name__ == "__main__":
    main()
