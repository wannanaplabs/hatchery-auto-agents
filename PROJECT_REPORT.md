# Project State Report — 2026-04-15

## Summary
- REAL: 6 / 18
- PARTIAL: 7 / 18
- STUB: 3 / 18
- BROKEN: 2 / 18

| Slug | Verdict | Vercel (prod latest) | Size | Tasks done | Open PRs |
|---|---|---|---|---|---|
| pulse | **BROKEN** | ERROR (ready_seen=0) | 0.1KB | 29/32 | 0 |
| vanishing-green | **REAL** | READY (ready_seen=4) | 12.0KB | 27/28 | 0 |
| dark-shipping | **PARTIAL** | ERROR (ready_seen=1) | 10.0KB | 25/28 | 0 |
| connected | **PARTIAL** | READY (ready_seen=5) | 5.6KB | 27/28 | 0 |
| anomaly-board | **PARTIAL** | ERROR (ready_seen=9) | 6.8KB | 25/29 | 1 |
| goop-ops | **REAL** | READY (ready_seen=7) | 11.7KB | 26/27 | 0 |
| burning-season | **STUB** | READY (ready_seen=1) | 4.6KB | 27/29 | 0 |
| localized-threats | **STUB** | READY (ready_seen=1) | 0.6KB | 26/27 | 0 |
| shell-game | **BROKEN** | ERROR (ready_seen=0) | 0.1KB | 26/30 | 0 |
| the-hill | **PARTIAL** | ERROR (ready_seen=1) | 8.4KB | 27/29 | 0 |
| newsquake | **PARTIAL** | READY (ready_seen=1) | 7.3KB | 28/28 | 0 |
| toxic-clouds | **STUB** | ERROR (ready_seen=4) | 5.4KB | 28/29 | 0 |
| inside-track | **PARTIAL** | READY (ready_seen=6) | 9.1KB | 29/32 | 0 |
| narrative-shift | **PARTIAL** | READY (ready_seen=8) | 5.6KB | 27/27 | 0 |
| seismic-jukebox | **REAL** | READY (ready_seen=2) | 199.0KB | 28/30 | 1 |
| party-lines | **REAL** | READY (ready_seen=3) | 11.2KB | 3/6 | 0 |
| orbital | **REAL** | READY (ready_seen=6) | 8.4KB | 5/5 | 0 |
| living-planet | **REAL** | READY (ready_seen=4) | 25.7KB | 5/5 | 0 |

## Per-Project Detail

### pulse — [BROKEN]
- **One-liner:** Earth-as-hospital — earthquakes/fires/events
- **Vercel (prod):** latest=ERROR · ready_seen=0/10 · recent=['ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://pulse-wannanaplabs.vercel.app (0.1KB)
  - title: `(empty)`
  - visible body preview: `The deployment could not be found on Vercel. DEPLOYMENT_NOT_FOUND yul1::24wz9-1776262445087-672a20472d97`
  - flags: keywords=no, title_is_stub=True, loading_only=False, deployment_missing=True
- **Last commit:** 82cbd1c "fix: resolve all build errors + real content [reviewed by claude-main]" (1d ago)
- **Open PRs:** 0
- **Hatchery tasks:** 29 done · 0 ready · 1 claimed · 0 in_progress · 0 review (90% complete)
- **Verdict:** BROKEN — DEPLOYMENT_NOT_FOUND on production alias — every recorded production deploy is ERROR and no alias resolves.
- **Gaps:**
  - NO successful production deployment ever — fix build errors
  - title is still 'Create Next App' / empty — update `app/layout.tsx` metadata

### vanishing-green — [REAL]
- **One-liner:** GLAD forest loss alerts
- **Vercel (prod):** latest=READY · ready_seen=4/10 · recent=['READY', 'READY', 'READY', 'READY', 'ERROR']
- **Live URL:** https://vanishing-green-wannanaplabs.vercel.app (12.0KB)
  - title: `Vanishing Green`
  - visible body preview: `Vanishing Green Vanishing Green Tracking global deforestation with satellite imagery and forest data Loading deforestation alerts from Global Forest Watch... Amazon Rainforest - Deforestation Hotspot 2025 - Deforested 20`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 8c8347e "[Hatchery] [SHIP-9] Download GLAD alerts CSV of visible markers (#4)" (18h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 27 done · 0 ready · 1 claimed · 0 in_progress · 0 review (96% complete)
- **Verdict:** REAL — Vercel production READY; live URL renders domain-specific data (941 chars of visible content with keywords).

### dark-shipping — [PARTIAL]
- **One-liner:** AIS vessel gap detection
- **Vercel (prod):** latest=ERROR · ready_seen=1/10 · recent=['ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://dark-shipping-wannanaplabs.vercel.app (10.0KB)
  - title: `Dark Shipping`
  - visible body preview: `Dark Shipping WannanaPlabs AIS Ship Tracking Platform Welcome to the Dark Shipping logistics platform Track Shipment Enter your tracking number to get real-time updates on your shipment. Shipping Calculator Calculate shi`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 32482e7 "[Hatchery] [VIS-1] Add MCP endpoints `/get_recent_ais_gaps` and `/analyze_gap_suspicion` (#4)" (18h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 25 done · 0 ready · 3 claimed · 0 in_progress · 0 review (89% complete)
- **Verdict:** PARTIAL — Live page renders a generic logistics UI ('Track Shipment', 'Shipping Calculator') — not AIS vessel gap detection; off-brief
- **Gaps:**
  - latest production build is ERROR — live site is served by a stale alias

### connected — [PARTIAL]
- **One-liner:** Multi-source correlation network
- **Vercel (prod):** latest=READY · ready_seen=5/10 · recent=['READY', 'READY', 'READY', 'READY', 'READY', 'ERROR']
- **Live URL:** https://connected-wannanaplabs.vercel.app (5.6KB)
  - title: `Connected`
  - visible body preview: `Connected Loading...`
  - flags: keywords=yes, title_is_stub=False, loading_only=True, deployment_missing=False
- **Last commit:** c1ca755 "fix: pin next to 15.5.15 to avoid CVE-2025-66478" (1d ago)
- **Open PRs:** 0
- **Hatchery tasks:** 27 done · 0 ready · 1 claimed · 0 in_progress · 0 review (96% complete)
- **Verdict:** PARTIAL — Shows title + 'Loading...' — correlation network never renders
- **Gaps:**
  - UI stuck on 'Loading...' / error state — upstream data fetch not wired or failing

### anomaly-board — [PARTIAL]
- **One-liner:** Multi-source anomaly cards
- **Vercel (prod):** latest=ERROR · ready_seen=9/10 · recent=['ERROR', 'READY', 'READY', 'READY', 'READY', 'READY']
- **Live URL:** https://anomaly-board-wannanaplabs.vercel.app (6.8KB)
  - title: `Anomaly Board — Cross-Source Detection`
  - visible body preview: `Anomaly Board — Cross-Source Detection Loading anomalies...`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 53801be "feat(127833b9): [SHIP-11] Vercel Analytics + Speed Insights + perf budget [Hatchery task]" (15h ago)
- **Open PRs:** 1 — #7 [Hatchery] [SHIP-11] Vercel Analytics + Speed Insights + per
- **Hatchery tasks:** 25 done · 0 ready · 1 claimed · 0 in_progress · 1 review (86% complete)
- **Verdict:** PARTIAL — Shows title + 'Loading anomalies...' — API call not resolving / no cards visible
- **Gaps:**
  - latest production build is ERROR — live site is served by a stale alias
  - 1 open PR(s) unmerged

### goop-ops — [REAL]
- **One-liner:** Internal analytics dashboard
- **Vercel (prod):** latest=READY · ready_seen=7/10 · recent=['READY', 'READY', 'READY', 'READY', 'READY', 'READY']
- **Live URL:** https://goop-ops-wannanaplabs.vercel.app (11.7KB)
  - title: `Goop Ops`
  - visible body preview: `Goop Ops Goop Ops Agents Costs Deployments Hatchery Agents Agent Status Context agent-1 running Processing batch job #4523 agent-2 stopped Awaiting new tasks agent-3 running Analyzing deployment metrics agent-4 idle Idle`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 2ae5d59 "[Hatchery] [VIS-3] Add per-project cost tracker (Vercel API + LLM spend) (#6)" (18h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 26 done · 0 ready · 0 claimed · 0 in_progress · 1 review (96% complete)
- **Verdict:** REAL — Vercel production READY; live URL renders domain-specific data (290 chars of visible content with keywords).

### burning-season — [STUB]
- **One-liner:** NASA FIRMS wildfire timelapse
- **Vercel (prod):** latest=READY · ready_seen=1/10 · recent=['READY', 'ERROR', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://burning-season-wannanaplabs.vercel.app (4.6KB)
  - title: `Burning Season · WannaNapLabs`
  - visible body preview: `Burning Season · WannaNapLabs Burning Season`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 1751e05 "fix: add missing root layout.tsx" (1d ago)
- **Open PRs:** 0
- **Hatchery tasks:** 27 done · 0 ready · 0 claimed · 0 in_progress · 0 review (93% complete)
- **Verdict:** STUB — Live page shows only the title — no FIRMS wildfire data, no timelapse

### localized-threats — [STUB]
- **One-liner:** ZIP-local safety score
- **Vercel (prod):** latest=READY · ready_seen=1/10 · recent=['READY', 'ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://localized-threats-wannanaplabs.vercel.app (0.6KB)
  - title: `Localized Threats`
  - visible body preview: `Localized Threats`
  - flags: keywords=yes, title_is_stub=False, loading_only=True, deployment_missing=False
- **Last commit:** 9ad995d "trigger: redeploy with vite framework" (1d ago)
- **Open PRs:** 0
- **Hatchery tasks:** 26 done · 0 ready · 0 claimed · 0 in_progress · 0 review (96% complete)
- **Verdict:** STUB — Live page shows only the title — no ZIP-based scoring UI rendered
- **Gaps:**
  - UI stuck on 'Loading...' / error state — upstream data fetch not wired or failing

### shell-game — [BROKEN]
- **One-liner:** ICIJ Panama Papers force graph
- **Vercel (prod):** latest=ERROR · ready_seen=0/10 · recent=['ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://shell-game-wannanaplabs.vercel.app (0.1KB)
  - title: `(empty)`
  - visible body preview: `The deployment could not be found on Vercel. DEPLOYMENT_NOT_FOUND yul1::cnw67-1776262446464-4086d9c96eda`
  - flags: keywords=no, title_is_stub=True, loading_only=False, deployment_missing=True
- **Last commit:** 107abeb "[Hatchery] [VIS-1] Add MCP endpoints `/search_entity`, `/find_shortest_path`, `/get_entity_network` (#5)" (18h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 26 done · 0 ready · 1 claimed · 1 in_progress · 1 review (86% complete)
- **Verdict:** BROKEN — DEPLOYMENT_NOT_FOUND on production alias — every recorded production deploy is ERROR and no alias resolves.
- **Gaps:**
  - NO successful production deployment ever — fix build errors
  - title is still 'Create Next App' / empty — update `app/layout.tsx` metadata
  - 0 ready + 1 in_progress tasks still open

### the-hill — [PARTIAL]
- **One-liner:** Congressional seating chart
- **Vercel (prod):** latest=ERROR · ready_seen=1/10 · recent=['ERROR', 'READY', 'ERROR']
- **Live URL:** https://the-hill-wannanaplabs.vercel.app (8.4KB)
  - title: `The Hill - Congressional Stock Trading Tracker`
  - visible body preview: `The Hill - Congressional Stock Trading Tracker Loading... The Hill Congressional Stock Trading Tracker Error Loading Data Unable to fetch trading data. Please try again later. fetch failed`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 1e60d56 "fix: bump next to 15.5.15 (CVE-2025-66478)" (9h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 27 done · 0 ready · 1 claimed · 0 in_progress · 0 review (93% complete)
- **Verdict:** PARTIAL — Shows 'Error Loading Data — Unable to fetch trading data. fetch failed' — upstream data call broken
- **Gaps:**
  - latest production build is ERROR — live site is served by a stale alias
  - UI stuck on 'Loading...' / error state — upstream data fetch not wired or failing

### newsquake — [PARTIAL]
- **One-liner:** GDELT news-as-seismograph
- **Vercel (prod):** latest=READY · ready_seen=1/10 · recent=['READY', 'ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://newsquake-wannanaplabs.vercel.app (7.3KB)
  - title: `NewsQuake`
  - visible body preview: `NewsQuake Newsquake News Events as Seismic Activity Recent Events Loading... Event Location Tone Impact Date Loading events... Built by WannaNapLabs`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 0641486 "fix: bump next to 15.5.15 (patch CVE-2025-66478)" (1d ago)
- **Open PRs:** 0
- **Hatchery tasks:** 28 done · 0 ready · 0 claimed · 0 in_progress · 0 review (100% complete)
- **Verdict:** PARTIAL — Table scaffolding renders but rows show 'Loading events...' — GDELT feed never populates

### toxic-clouds — [STUB]
- **One-liner:** PurpleAir AQI map
- **Vercel (prod):** latest=ERROR · ready_seen=4/10 · recent=['ERROR', 'ERROR', 'READY', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://toxic-clouds-wannanaplabs.vercel.app (5.4KB)
  - title: `toxic-clouds`
  - visible body preview: `toxic-clouds`
  - flags: keywords=no, title_is_stub=False, loading_only=True, deployment_missing=False
- **Last commit:** 5bee1be "fix: add "use client" to 4 component(s) using hooks" (17h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 28 done · 0 ready · 1 claimed · 0 in_progress · 0 review (96% complete)
- **Verdict:** STUB — Live page shows only the slug 'toxic-clouds' — no AQI map, no PurpleAir data
- **Gaps:**
  - latest production build is ERROR — live site is served by a stale alias
  - UI stuck on 'Loading...' / error state — upstream data fetch not wired or failing
  - no domain-specific keywords in live HTML — content is off-brief

### inside-track — [PARTIAL]
- **One-liner:** Politician trade detection
- **Vercel (prod):** latest=READY · ready_seen=6/10 · recent=['READY', 'READY', 'READY', 'READY', 'READY', 'READY']
- **Live URL:** https://inside-track-wannanaplabs.vercel.app (9.1KB)
  - title: `Create Next App`
  - visible body preview: `Create Next App Inside Track Congressional Stock Trade Monitor Total Trades 0 Most Active Trader N/A Top Ticker N/A Loading trades... © 2026 Inside Track. Built with Next.js 15. WannaNapLabs`
  - flags: keywords=yes, title_is_stub=True, loading_only=False, deployment_missing=False
- **Last commit:** 1cbcd5f "trigger: redeploy with legacy-peer-deps" (1d ago)
- **Open PRs:** 0
- **Hatchery tasks:** 29 done · 0 ready · 2 claimed · 0 in_progress · 0 review (90% complete)
- **Verdict:** PARTIAL — Title still 'Create Next App'; 'Total Trades 0', 'Most Active Trader N/A', 'Loading trades...' — data empty
- **Gaps:**
  - title is still 'Create Next App' / empty — update `app/layout.tsx` metadata

### narrative-shift — [PARTIAL]
- **One-liner:** GDELT media sentiment
- **Vercel (prod):** latest=READY · ready_seen=8/10 · recent=['READY', 'READY', 'READY', 'READY', 'READY', 'READY']
- **Live URL:** https://narrative-shift-wannanaplabs.vercel.app (5.6KB)
  - title: `Narrative Shift`
  - visible body preview: `Narrative Shift Loading narrative data...`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 4cd5a02 "fix: add "use client" to 3 component(s) using hooks" (17h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 27 done · 0 ready · 0 claimed · 0 in_progress · 0 review (100% complete)
- **Verdict:** PARTIAL — Shows title + 'Loading narrative data...' — GDELT data not loading

### seismic-jukebox — [REAL]
- **One-liner:** USGS earthquakes sonified
- **Vercel (prod):** latest=READY · ready_seen=2/10 · recent=['READY', 'ERROR', 'ERROR', 'ERROR', 'ERROR', 'ERROR']
- **Live URL:** https://seismic-jukebox-wannanaplabs.vercel.app (199.0KB)
  - title: `Seismic Jukebox - Hear the Earth Move`
  - visible body preview: `Seismic Jukebox - Hear the Earth Move 🌍 Seismic Jukebox Listen to the Earth shake EVENTS: 100 LARGEST: M 5.7 DEEPEST: 554 km Recent Earthquakes 0.9 15 km N of Warner Springs, CA 10m ago DEPTH: 4.1 km LAT: 33.42 ° LON: -1`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** aab2572 "fix: bump next to 15.5.15 (patch CVE-2025-66478)" (1d ago)
- **Open PRs:** 1 — #12 [Hatchery] [FIX-DEPLOY] seismic-jukebox: npm install fails —
- **Hatchery tasks:** 28 done · 0 ready · 1 claimed · 0 in_progress · 0 review (93% complete)
- **Verdict:** REAL — Vercel production READY; live URL renders domain-specific data (8515 chars of visible content with keywords).
- **Gaps:**
  - 1 open PR(s) unmerged

### party-lines — [REAL]
- **One-liner:** Dem vs Rep portfolios
- **Vercel (prod):** latest=READY · ready_seen=3/10 · recent=['READY', 'ERROR', 'ERROR', 'READY', 'READY']
- **Live URL:** https://party-lines-wannanaplabs.vercel.app (11.2KB)
  - title: `party-lines`
  - visible body preview: `party-lines party-lines Side-by-side portfolio performance: Dems vs Republicans over time. Democratic YTD: 14.2 % YTD 1Y: 21.8 % 365d Trades: 1243 NVDA 8.1 % MSFT 7.4 % AAPL 6.3 % Republican YTD: 11.7 % YTD 1Y: 18.3 % 36`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 0b3b47a "feat(11858dfb): [SHIP-1] Portfolio comparison dashboard with party averages [Hatchery task]" (14h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 3 done · 0 ready · 1 claimed · 1 in_progress · 0 review (50% complete)
- **Verdict:** REAL — Vercel production READY; live URL renders domain-specific data (265 chars of visible content with keywords).
- **Gaps:**
  - 0 ready + 1 in_progress tasks still open

### orbital — [REAL]
- **One-liner:** ISS + SpaceX
- **Vercel (prod):** latest=READY · ready_seen=6/10 · recent=['READY', 'READY', 'READY', 'READY', 'READY', 'READY']
- **Live URL:** https://orbital-wannanaplabs.vercel.app (8.4KB)
  - title: `orbital · WannaNapLabs`
  - visible body preview: `orbital · WannaNapLabs orbital Real-time ISS tracker with upcoming SpaceX launches. ISS — Live Position Latitude: -21.078 ° Longitude: 31.071 ° Updated: Wed, 15 Apr 2026 14:11:21 GMT Next SpaceX Launch USSF-44 Launch: Tu`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** 9beb70f "feat(7256e90c): [SHIP-1] ISS live position card + next SpaceX launch card [Hatchery task]" (18h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 5 done · 0 ready · 0 claimed · 0 in_progress · 0 review (100% complete)
- **Verdict:** REAL — Vercel production READY; live URL renders domain-specific data (269 chars of visible content with keywords).

### living-planet — [REAL]
- **One-liner:** GBIF biodiversity
- **Vercel (prod):** latest=READY · ready_seen=4/10 · recent=['READY', 'READY', 'READY', 'READY']
- **Live URL:** https://living-planet-wannanaplabs.vercel.app (25.7KB)
  - title: `living-planet · WannaNapLabs`
  - visible body preview: `living-planet · WannaNapLabs living-planet Real-time animal species observations around the world. 3,613,176,142 observations in GBIF Frangula dodonei Frangula dodonei subsp. dodonei Magnoliopsida France 1/20/2026 Agriop`
  - flags: keywords=yes, title_is_stub=False, loading_only=False, deployment_missing=False
- **Last commit:** e3ed44c "feat(7025b8cc): [SHIP-1] GBIF recent species observations list [Hatchery task]" (15h ago)
- **Open PRs:** 0
- **Hatchery tasks:** 5 done · 0 ready · 0 claimed · 0 in_progress · 0 review (100% complete)
- **Verdict:** REAL — Vercel production READY; live URL renders domain-specific data (1354 chars of visible content with keywords).

## Top 5 Most Critical Gaps

Ranked by blast radius — what fixing next unlocks the most user-visible quality.

1. **pulse & shell-game have no successful production deployment ever.** Both live URLs return `DEPLOYMENT_NOT_FOUND`. Every production deploy is ERROR (ready_seen=0). These are the flagship 'Earth-as-hospital' and 'Panama Papers force graph' projects — they are 100% invisible to users. Priority: make them build (likely TypeScript/ESLint errors or missing env vars at build time). `pulse` has 32 Hatchery tasks with 29 done — work is being merged but never shipping.

2. **Six PARTIAL projects are stuck on `Loading...` — upstream data fetches are broken in production.** anomaly-board, narrative-shift, connected, newsquake, the-hill, localized-threats all render the shell but their data loaders never resolve (the-hill explicitly shows 'fetch failed'). Most likely: (a) client-side fetch to an API route that fails due to missing env vars on Vercel, (b) CORS/SSR mismatch, or (c) external rate limits (GDELT, GLAD, USGS). A single audit of env vars + data loader error handling across these six would flip most to REAL.

3. **Three STUB projects never progressed past a title bar** despite near-complete task queues: toxic-clouds (28/29 done), burning-season (27/29 done), localized-threats (26/27 done). Tasks are being marked done but the actual feature work isn't reaching the page component. This points to a systemic agent-quality problem — tasks are being 'completed' without rendering anything visible. Recommend spot-auditing the PRs that closed these tasks; the main page `app/page.tsx` is likely empty/unchanged while nested feature components were added but never imported.

4. **'Latest production deploy is ERROR while an older READY is aliased'** pattern hits dark-shipping, the-hill, anomaly-board, toxic-clouds. Users see stale content and there's no alert — deployments are silently regressing. Add a CI check that fails if the latest production build is ERROR, or enable Vercel deployment-status webhooks to Hatchery.

5. **inside-track still has `<title>Create Next App</title>`** after 29/32 tasks done. This is the tell-tale sign that the base Next.js template `app/layout.tsx` metadata was never updated. Almost certainly the same root cause affects any project where the agent scaffolded from `create-next-app` and never touched `metadata`. Grep every repo for `'Create Next App'` in `layout.tsx` — cheap global fix.
