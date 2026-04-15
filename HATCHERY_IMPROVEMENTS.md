# Hatchery Platform Improvements

Compiled from 19 platform gaps discovered while running the WannaNapLabs auto-agent fleet.
Each item has a concrete fix proposal with file paths, code patterns, and a VERIFY block.

Source: tasks in the Hatchery project `Hatchery Platform — Self-Hosted Improvements` (project_id `1cd40843-2d5d-4449-adcf-b0863c6439cf`).

---

## Status Summary

- **claimed**: 4
- **in_progress**: 2
- **done**: 13
- **TOTAL**: 19

---

## 🟡 Claimed (4)

### 1. PR merge auto-close should wait for deploy success

**Task ID:** `f9a580a5` · **Priority:** 3 · **Caps:** `api-route, typescript, data-fetching`

Current GitHub webhook auto-closes task when PR merges. But the merge commit may FAIL the Vercel build (CVE detection, syntax error, etc.). Task gets marked done while the project is broken. Fix: on PR merged, set task status='deploying' (new state) instead of 'done'. Then on Vercel webhook deploy.READY → task='done', deploy.ERROR → task='ready' with comment='Build failed post-merge: <log_link>'. File: app/api/v1/github/webhook/route.ts + app/api/v1/webhooks/vercel/route.ts. VERIFY: merge a PR with a build error; task ends up back in ready, not done.

---

### 2. Tasks need commit_sha field for accurate QA matching

**Task ID:** `4592614f` · **Priority:** 3 · **Caps:** `api-route, typescript, bugfix`

QA reviewer guesses 'is this deploy for this task?' by comparing task.updated_at to deploy.createdAt. Race-prone: a deploy from an unrelated commit can satisfy multiple tasks, or a task's specific commit can be missed. Fix: add commit_sha (text) column to hatchery_tasks. Workers PATCH it when committing. Vercel webhook matches deploy.gitSource.sha === task.commit_sha to auto-close. QA reviewer/external scripts can also use this for deterministic matching. File: supabase/migrations/, app/api/v1/agent/tasks/[id]/route.ts (add commit_sha to allowedFields). VERIFY: workers send PATCH with commit_sha; webhook closes only the matching task.

---

### 3. Self-service agent identity registration

**Task ID:** `6bd37679` · **Priority:** 3 · **Caps:** `api-route, typescript`

A workspace can only have one agent per API key for capability registration. We ran 3 hermes workers sharing one Goop key, causing: (a) PATCH /capabilities races (last-writer-wins shrinks visibility), (b) /available filter sees all 3 workers as 'the same agent' so last_failed_by blocks all of them. Per-agent-capabilities is filed; the separate missing piece is a way to register a SECOND agent with the same workspace API key. Tried POST /agent/agents → empty response. POST /agent/agents/register → 404. Fix: POST /agent/agents {name, capabilities} returns {agent_id, agent_api_key} so a fleet owner can spin up N identities without going through the UI. VERIFY: curl -X POST ... creates a new agent and returns a usable key.

---

### 4. /release should distinguish crash from fail (no_blame flag)

**Task ID:** `4a8cdbeb` · **Priority:** 3 · **Caps:** `api-route, typescript`

POST /agent/tasks/{id}/release sets last_failed_by on every call. But worker uses release in two semantically different cases: (1) worker crashed/got-SIGKILLed with task claimed — no blame, task should be freely re-claimable, (2) worker tried and failed after N iterations — blame, add cooldown. Currently conflated. Fix: accept {no_blame: true} in body which skips setting last_failed_by, OR split into two endpoints (/release vs /fail). Our startup-reaper pattern specifically needs no-blame behavior because crashed workers did zero work on the task. VERIFY: POST /release {no_blame:true} leaves last_failed_by unchanged.

---

## 🔵 In Progress (2)

### 1. submit-for-qa should require pr_url OR commit_sha

**Task ID:** `3c3e28f1` · **Priority:** 3 · **Caps:** `api-route, bugfix`

Workers can call submit-for-qa with no PR and no commit, putting task in 'review' state with no way to resolve. Becomes zombie. Fix: validate body.pr_url or body.commit_sha is present before transitioning to review. Without one, return 400 'submit-for-qa requires pr_url or commit_sha'. Forces workers to actually do the work before declaring complete. File: app/api/v1/agent/tasks/[id]/submit-for-qa/route.ts. VERIFY: bare POST without pr_url returns 400.

---

### 2. Document /release body field: it's 'comment' not 'reason'

**Task ID:** `d1f036ca` · **Priority:** 2 · **Caps:** `api-route, bugfix`

Our worker sent {reason: '...'} per intuition; API returned {error:'comment is required'} and release silently failed. The worker logged 'Released task X' but nothing happened — critical debugging hell. The field name is nowhere in /api/v1/agent/openapi.json (or if it is, it's not surfaced in the MCP server signatures). Fix: (a) accept BOTH 'comment' and 'reason' (alias), (b) surface in openapi.json with the correct field name, (c) or return a more descriptive error pointing at 'did you mean comment?'. Low-effort fix that saves hours of debugging.

---

## ✅ Done (13)

### 1. Auto-timeout tasks stuck in 'review' state

**Task ID:** `d508c29e` · **Priority:** 3 · **Caps:** `api-route, typescript, bugfix`

Observed: tasks land in 'review' status and stay there forever when no follow-up deploy resolves them. Workers submit_for_qa but if no commit was actually made (worker bug or PR-flow falls back), no Vercel webhook fires, no auto-close. Tasks become zombies — not done, not failable, not visible in /available. Fix: review tasks with updated_at > now() - interval '60 minutes' AND no commit_sha/pr_url should auto-revert to 'ready' with comment='Auto-reset: review timeout, no PR/deploy resolved this'. File: supabase/functions/review-timeout/index.ts (Edge Function on cron). VERIFY: submit-for-qa without pr_url, wait 60min, task back in ready.

---

### 2. Clear last_failed_by via PATCH or on status change

**Task ID:** `d1f3f8bb` · **Priority:** 3 · **Caps:** `api-route, typescript, bugfix`

Blocker found in fleet: tasks released by an agent get last_failed_by=<agent_id>, which makes /tasks/available filter them out for that agent forever. PATCH /agent/tasks/{id} with {last_failed_by:null} returns 400 (field not in allowedFields). PATCH with status=ready doesn't reset it either. Fix: (a) add last_failed_by to allowedFields for admin-scope keys, OR (b) auto-clear on status transition ready→claimed, OR (c) add explicit POST /agent/tasks/{id}/unblock endpoint. Our fleet worked around it by using PATCH status=ready + assignee_agent_id:null directly, but this bypasses the cooldown intent. VERIFY: after release_task, a different API call clears last_failed_by so the original agent can re-claim.

---

### 3. Index (status, required_capabilities) on /tasks/available

**Task ID:** `6b44b096` · **Priority:** 3 · **Caps:** `bugfix, typescript`

GET /agent/tasks/available is ~950ms p50 (measured from auto-agents session). Likely seqscan + cap intersection. Add CREATE INDEX idx_tasks_available ON hatchery_tasks (status) WHERE status IN ('ready','claimed'). Also GIN index on required_capabilities for containment queries. File: supabase/migrations/ new SQL migration. VERIFY: EXPLAIN ANALYZE shows Index Scan, p50 < 200ms.

---

### 4. Server-side failure_count + cooldown

**Task ID:** `0a7eac11` · **Priority:** 3 · **Caps:** `api-route, bugfix, typescript`

release_task() has no back-pressure - broken tasks retry forever. Add failure_count INT and last_failed_at TIMESTAMP. On each release, increment; if >=3, set status='needs_human'. /agent/tasks/available excludes tasks in cooldown (last_failed_at > now() - 30min). Files: supabase/migrations/, app/api/v1/agent/tasks/[id]/release/route.ts. VERIFY: fail same task 3x -> disappears from available, shows in /tasks/awaiting-approval.

---

### 5. Deploy-linked task QA (Vercel webhook integration)

**Task ID:** `ec860633` · **Priority:** 3 · **Caps:** `api-route, typescript, data-fetching`

Move the external QA reviewer server-side: accept POST /api/v1/webhooks/vercel with Vercel deploy events; on READY/ERROR, look up tasks whose commit_sha matches the deployment and auto-transition (review->done or review->ready). Files: app/api/v1/webhooks/vercel/route.ts (NEW), add commit_sha column to hatchery_tasks. VERIFY: push a commit tied to a task, task auto-resolves within 60s without external poller.

---

### 6. SSE /events/stream adoption guide + example

**Task ID:** `a0fa9d30` · **Priority:** 3 · **Caps:** `typescript, api-route, data-fetching`

Endpoint /agent/events/stream already exists but nothing uses it. Worker polling at 30s wastes ~1s/poll on /tasks/available. Verify the SSE endpoint emits task.created/updated/claimed events. Produce examples/python-sse-client.py replacing polling with SSE listener. VERIFY: example code claims a freshly-created task within 500ms of its creation.

---

### 7. Per-agent capabilities (not per-key)

**Task ID:** `e7f3805d` · **Priority:** 3 · **Caps:** `api-route, typescript, bugfix`

PATCH /agent/capabilities writes to the agent linked to the API key. Multiple workers sharing one key race each other — last writer wins. Fix: add agent_identity_id column distinct from api_key_owner. Expose POST /agent/agents with display_name + caps, returns sub-identity id. Files: supabase/migrations/ (new column), app/api/v1/agent/agents/route.ts, app/api/v1/agent/capabilities/route.ts. VERIFY: two workers on same key advertise different caps without clobbering.

---

### 8. Server-side stale-claim reaper

**Task ID:** `7d50ab56` · **Priority:** 3 · **Caps:** `api-route, typescript`

Currently the Hermes worker reaps stale claims on startup (15min threshold). Misses the case where workers crash mid-task. Add server-side cron running every 5 min: UPDATE hatchery_tasks SET status='ready', assignee_agent_id=null, completion_note='auto-released: stale claim' WHERE status='claimed' AND updated_at < now() - interval '30 minutes'. File: supabase/functions/stale-claim-reaper/index.ts (new Edge Function). Trigger via pg_cron or Vercel cron. VERIFY: claim a task, wait 30min, check it's back in ready.

---

### 9. Workspace-level 'active sprint' tag for fleet focus

**Task ID:** `7fc40949` · **Priority:** 2 · **Caps:** `api-route, typescript`

Fleet workers see ALL ready tasks across all projects. Hard to focus the fleet on (e.g.) 'fix the 9 ERROR deploys first' vs 'add new features'. Fix: add tasks.sprint_tag (text) and workspace.active_sprint_tags (text[]). /tasks/available filters to tasks where sprint_tag IN active_sprint_tags. Lets human prioritize without manually re-claiming/re-statusing. Bonus: priority field already exists but isn't used for ordering across project boundaries. File: supabase/migrations/, app/api/v1/agent/tasks/available/route.ts. VERIFY: set workspace.active_sprint_tags=['bugfix']; only bugfix tasks appear in /available.

---

### 10. PATCH /agent/tasks/{id} needs descriptive error for invalid fields

**Task ID:** `2e8b138f` · **Priority:** 2 · **Caps:** `api-route, bugfix`

Sent {last_failed_by: null, comment: 'unblock'} → 400 with message that didn't say WHICH field was rejected. Wasted ~30 min debugging. Fix: validate fields against allowedFields up front, return {error: 'Field X is not patchable. Allowed: [...]'}. File: app/api/v1/agent/tasks/[id]/route.ts. VERIFY: PATCH with bogus field returns the field name in the error.

---

### 11. /tasks/available filtering should be debuggable (?debug=true)

**Task ID:** `8359515c` · **Priority:** 2 · **Caps:** `api-route, bugfix, debugging`

Fleet spent 90+ min stuck with ready=36 but available=0. Root cause was last_failed_by filter — invisible to the operator. Current flow: /available returns [] with no explanation. No response header, no log. Had to reverse-engineer via /tasks/search + field inspection. Fix: accept ?debug=true query param; response includes excluded_count: N and excluded_reasons: {'last_failed_by': 36, 'status_not_ready': 0, 'cap_mismatch': 0, 'in_cooldown': 0, 'depends_on_unresolved': 0}. Would cut incident debugging from hours to seconds. Zero user-facing impact.

---

### 12. Token/cost tracking per task

**Task ID:** `66d5b424` · **Priority:** 2 · **Caps:** `api-route, typescript, complex-ui`

No visibility into which tasks burn most tokens. Add tokens_used_input INT, tokens_used_output INT, estimated_cost_cents INT columns. PATCH /agent/tasks/{id} accepts these in body. Add dashboard panel app/dashboard/cost/page.tsx showing top-cost tasks + cost-per-project. VERIFY: after runs, see which projects/task-types are most expensive.

---

### 13. Per-project repo lock (prevent concurrent edits)

**Task ID:** `e97faf9c` · **Priority:** 2 · **Caps:** `api-route, typescript`

Two workers editing the same repo simultaneously causes git merge conflicts (observed during fleet runs). Add POST /agent/projects/{id}/lock (returns lock_token, expires 10min, single holder) + POST /agent/projects/{id}/unlock. Task claim auto-acquires the lock, releases on done/release. Postgres row with NOW()+interval check. Files: supabase/migrations/, app/api/v1/agent/projects/[id]/lock/route.ts. VERIFY: two claim calls on same-project tasks - second waits or conflicts.

---

