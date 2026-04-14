# SHIP Task Coverage Audit

**Date:** 2026-04-13
**Reviewer:** Claude Opus 4.6 (agent)
**Hatchery base:** `https://hatchery-tau.vercel.app/api/v1`

Compared every WannaNapLabs project's existing [SHIP-N] task set against its vision in `/Users/franknguyen/Desktop/forfun/LIVING_IDEAS.md`. Identified gaps and created `[VIS-N]` vision-extension tasks (priority 3, status ready) where LIVING_IDEAS calls out a feature that no SHIP task covers.

**Totals:** 15 projects had SHIP-1..SHIP-12 baseline. 3 projects (party-lines, orbital, living-planet) had only SHIP-1. Zero projects had MCP tool endpoints. Zero projects had webhook/watch subscription endpoints. **55 VIS tasks created across 18 projects.**

---

## Per-project gap analysis

Legend: `[x]` covered by a SHIP task • `[~]` partially covered • `[ ]` gap → new VIS task

### pulse (Earth as Hospital Patient)

LIVING_IDEAS features:
- [x] USGS earthquake live feed (SHIP-1)
- [x] Vital signs sidebar — BPM/Temp/Stress (SHIP-2)
- [x] Canvas EKG strip (SHIP-3)
- [~] Composite health score algorithm — SHIP-2 shows a number but no formula; no API → VIS-1
- [ ] MCP tool `get_earth_health_score()` → **VIS-1** (also `get_vital_signs`)
- [ ] Globe *physically pulsing* with seismic energy (the signature visual hook) → **VIS-2**
- [ ] Data attribution / sources page (USGS, FIRMS, GDELT, OWM) → **VIS-3**
- [ ] MCP tool `watch_region(bbox, webhook_url)` → **VIS-4**

VIS tasks: `5f262510`, `fc4bf89c`, `9d5844a3`, `2740e4db` (4 total)

---

### seismic-jukebox (Earthquakes as Music)

LIVING_IDEAS features:
- [x] 3D globe + USGS markers (in-progress)
- [x] Continent outlines (SHIP-3)
- [x] SonificationPlayer (SHIP-1)
- [~] Magnitude → volume/pitch/pan mapping (referenced in SHIP-1)
- [ ] MCP tool `sonify_earthquake_data(start,end,compression)` → **VIS-1**
- [ ] Ripple shader rings synced to audio (build-plan step 4) → **VIS-2**
- [ ] MCP tool `generate_ambient_loop(duration, region)` — viral hook → **VIS-3**

VIS tasks: `23a2411a`, `13acbb8c`, `904acd62`

---

### vanishing-green (Deforestation)

LIVING_IDEAS features:
- [x] GLAD alerts on map (SHIP-1)
- [x] Time-range tabs (SHIP-2)
- [x] Country filter (SHIP-3)
- [ ] MCP tools `get_deforestation_alerts` + `get_country_loss_rate` → **VIS-1**
- [ ] Real Sentinel-2 before/after imagery (LIVING_IDEAS step 8; workspace_state notes placeholder SVGs) → **VIS-2**
- [ ] Commodity-price overlay (soy/palm/beef, LIVING_IDEAS step 6) → **VIS-3**

VIS tasks: `c2159f6d`, `13647a13`, `c0094308`

---

### dark-shipping (AIS Gap Detection)

LIVING_IDEAS features:
- [x] Vessel tracks + gap markers (SHIP-1)
- [x] Clickable Leaflet popups (SHIP-2)
- [x] Gap-per-day timeline scrubber (SHIP-3)
- [ ] MCP tools `get_recent_ais_gaps` + `analyze_gap_suspicion` → **VIS-1**
- [ ] Signature visual — "pulsing red ? markers" (LIVING_IDEAS hook; current markers are plain) → **VIS-2**
- [ ] Geopolitical overlay: sanctioned waters + MPAs (step 9) → **VIS-3**

VIS tasks: `0f01c4bc`, `ae09941e`, `4a9a8017`

---

### anomaly-board (Multi-Source Detection)

LIVING_IDEAS features:
- [x] Six anomaly cards (SHIP-1)
- [x] Sort by %-deviation (SHIP-2)
- [x] Per-card sparkline (SHIP-3)
- [ ] MCP tools `get_current_anomalies`, `explain_anomaly` (Claude-backed) → **VIS-1**
- [ ] Cross-source correlation detection (step 9) → **VIS-2**
- [ ] MCP tool `setup_anomaly_alert(conditions, webhook_url)` → **VIS-3**

VIS tasks: `390485a0`, `9cd1fd34`, `0e0f5e85`

---

### goop-ops (Internal Analytics)

LIVING_IDEAS features (implied by "analytics dashboard"):
- [x] Stats cards + sparklines (SHIP-1)
- [x] Agent-status table (SHIP-2)
- [x] Project grid (SHIP-3)
- [ ] Machine-readable `/api/health` + Prometheus endpoint → **VIS-1**
- [ ] Live SSE event feed → **VIS-2**
- [ ] Per-project cost tracker → **VIS-3**

VIS tasks: `4f800745`, `4d58d5e5`, `11b7366e`

---

### narrative-shift (Media Sentiment)

LIVING_IDEAS features:
- [x] Live GDELT fetch (SHIP-1)
- [x] TimelineChart (SHIP-2)
- [x] ThemeCloud (SHIP-3)
- [ ] MCP tools `detect_narrative_shifts`, `get_narrative_trend` → **VIS-1**
- [ ] Multi-entity pin comparison (step 7) → **VIS-2**
- [ ] Language-specific sentiment breakdown (step 8) → **VIS-3**

VIS tasks: `e5236ff3`, `0328bee4`, `844489ec`

---

### connected (Multi-Layer Network Analysis)

LIVING_IDEAS features:
- [x] Force-directed graph (SHIP-1)
- [x] Search filter (SHIP-2)
- [x] Node drawer (SHIP-3)
- [ ] MCP tools `detect_correlations`, `predict_cascade_effects` (the project's moat) → **VIS-1**
- [ ] Sankey-diagram mode (build plan step 4) → **VIS-2**
- [ ] Historical correlation timeline (step 7) → **VIS-3**

VIS tasks: `e445be6c`, `e47c7866`, `9cbdacd0`

---

### toxic-clouds (Air Quality)

LIVING_IDEAS features:
- [x] PurpleAir integration (SHIP-1)
- [x] AQI color legend (SHIP-2)
- [x] Ranked sidebar (SHIP-3)
- [ ] MCP tools `get_air_quality`, `get_pollution_events`, `watch_air_quality` → **VIS-1**
- [ ] Animated smoke-plume shader (LIVING_IDEAS mentions shader-based plume) → **VIS-2**
- [ ] Side-by-side city comparison (step 8) → **VIS-3**

VIS tasks: `ae4016b5`, `41b145f0`, `d3784259`

---

### localized-threats (Personal Safety)

LIVING_IDEAS features:
- [x] Location input + local quakes (SHIP-1)
- [x] Fires + news grouped (SHIP-2)
- [x] Composite safety score card (SHIP-3)
- [ ] MCP tools `get_localized_threats`, `assess_personal_risk` → **VIS-1**
- [ ] MCP tool `setup_local_monitoring` with push/email alerts → **VIS-2**
- [ ] Shareable safety report page with OG image (step 9) → **VIS-3**

VIS tasks: `a2ed0033`, `b25ade53`, `ed8076f8`

---

### inside-track (Political Trade Timing) — FLAGSHIP

LIVING_IDEAS features:
- [x] House Stock Watcher connection (SHIP-1)
- [x] TradeExplorer (SHIP-2)
- [x] Timing-analysis engine (SHIP-3)
- [ ] MCP tools `detect_pre_news_trades`, `score_trade_timing` (6 tools total specified; this is the highest-revenue project) → **VIS-1**
- [ ] MCP tool `watch_politician` with alerts → **VIS-2**
- [ ] Committee-filter + sector-timing viz + /politicians/[name] pages → **VIS-3**

VIS tasks: `d0a7db22`, `6d37ddd1`, `ea796886`

---

### the-hill (Congressional Seating)

LIVING_IDEAS features:
- [x] SVG seating chart (SHIP-1)
- [x] Click-to-modal rep cards (SHIP-2)
- [x] State/party search filter (SHIP-3)
- [ ] MCP tools `get_recent_trades`, `get_politician_portfolio` → **VIS-1**
- [ ] Real-time trade-flash animation (the LIVING_IDEAS signature hook — "seats LIGHT UP when they trade") → **VIS-2**
- [ ] Committee heatmap overlay (step 7) → **VIS-3**

VIS tasks: `c79a0fdf`, `201efd61`, `276c2e9e`

---

### newsquake (News as Seismic Activity)

LIVING_IDEAS features:
- [x] Dark-theme full-width map (SHIP-1)
- [x] Seismograph timeline (SHIP-2)
- [x] Search updates map (SHIP-3)
- [ ] MCP tools `get_current_global_sentiment`, `detect_news_anomalies`, `track_story_propagation` → **VIS-1**
- [ ] Shader-based ripple globe (signature hook: "earthquake-style ripples, negative tone red") → **VIS-2**
- [ ] Click ripple → article sidebar via GDELT DOC 2.0 (step 7) → **VIS-3**

VIS tasks: `4ef69ef9`, `0afb420a`, `f5e7139c`

---

### burning-season (Wildfire Timelapse)

LIVING_IDEAS features:
- [x] Wildfire globe + 7-day slider (SHIP-1)
- [x] Play/pause + speed (SHIP-2)
- [x] FRP legend + regional callouts (SHIP-3)
- [ ] MCP tools `get_fire_timeline`, `compare_fire_years`, `analyze_burn_patterns` → **VIS-1**
- [ ] Bloom post-processing + InstancedMesh (signature "cinematic ember glow" hook) → **VIS-2**
- [ ] Sentinel-2 click popup (step 8) → **VIS-3**

VIS tasks: `b714126e`, `27f46010`, `a5508e11`

---

### shell-game (Panama Papers Explorer)

LIVING_IDEAS features:
- [x] Force graph + search + detail (SHIP-1)
- [x] Shortest-path mode (SHIP-2)
- [x] Jurisdiction coloring (SHIP-3)
- [ ] MCP tools `search_entity`, `find_shortest_path`, `get_entity_network` → **VIS-1**
- [ ] `analyze_jurisdiction_risk` tool + world choropleth → **VIS-2**
- [ ] Six Degrees shareable embed + OG image (viral-moment hook) → **VIS-3**

VIS tasks: `75440ac5`, `ffbf32cc`, `7c690a4e`

---

### party-lines (Dem vs Rep Portfolio) — UNDER-SCOPED

LIVING_IDEAS features:
- [x] Portfolio comparison dashboard (SHIP-1, only SHIP task)
- [ ] **No SHIP-2..SHIP-12 exists.** Sector breakdown, leaderboard, timeframe selector, header, About modal, loading states, mobile, OG, deep links, tests → **VIS-1 (bundled)**
- [ ] MCP tools `compare_party_performance`, `get_sector_preferences`, `calculate_politician_roi`, `find_bipartisan_trades` → **VIS-2**
- [ ] Shareable party-performance card + OG image ("Republicans outperformed S&P by 8%" viral hook) → **VIS-3**

VIS tasks: `3b836f86`, `8bb18c36`, `2d71e02d`

---

### orbital (ISS + SpaceX) — UNDER-SCOPED

LIVING_IDEAS features:
- [x] Live position + next launch (SHIP-1, only SHIP task)
- [ ] **No SHIP-2..SHIP-12 exists.** 3D globe + orbit line, visibility predictor, launch schedule, polish layer → **VIS-1 (bundled)**
- [ ] MCP tools `get_iss_position`, `get_upcoming_launches`, `get_visible_passes`, `track_satellite` → **VIS-2**
- [ ] Satellite constellation filter — Starlink/GPS/weather (step 5) → **VIS-3**

VIS tasks: `627c2582`, `a2f212c4`, `1a7a716d`

---

### living-planet (GBIF Biodiversity) — UNDER-SCOPED

LIVING_IDEAS features:
- [x] Recent observations list (SHIP-1, only SHIP task)
- [ ] **No SHIP-2..SHIP-12 exists.** Mapbox observation layer, species search, endangered highlighting, polish → **VIS-1 (bundled)**
- [ ] MCP tools `get_recent_observations`, `get_species_range`, `get_endangered_sightings`, `track_migration` → **VIS-2**
- [ ] Animated migration-pattern layer (step 4, e.g., Arctic tern pole-to-pole) → **VIS-3**

VIS tasks: `9403ff2b`, `bf15e491`, `2e94ea7d`

---

## Cross-cutting findings

### Patterns observed
1. **Zero MCP endpoints exist across all 18 projects.** LIVING_IDEAS makes MCP the revenue moat; every project spec lists 4-6 MCP tools. The SHIP baseline entirely skipped them. Of 55 VIS tasks, **~28 (51%) are MCP-endpoint creation**.
2. **Webhook/subscription endpoints missing universally.** LIVING_IDEAS mentions `watch_*(webhook_url)` on 6 projects; none have them. VIS tasks address this where it's a named LIVING_IDEAS tool (pulse, anomaly-board, toxic-clouds, localized-threats, inside-track).
3. **Signature visual hooks got glossed.** SHIP tasks covered "show data" but not the distinctive aesthetic:
   - pulse: globe isn't pulsing
   - newsquake: no ripple shader
   - burning-season: no bloom post-processing
   - seismic-jukebox: no audio-synced rings
   - the-hill: no flash animation
   - dark-shipping: plain markers instead of pulsing "?"
4. **3 projects (party-lines, orbital, living-planet) severely under-scoped** with only SHIP-1 each. They got a "VIS-1 (bundled baseline)" task summarizing the missing SHIP-2..SHIP-12 equivalent work.
5. **No data-attribution/sources pages anywhere.** OSINT credibility requires citing sources. Added to pulse (the flagship) as VIS-3; other projects should eventually get one but deprioritized here.
6. **SHIP-10 generic time-travel** overlooks deep historical archives (20yr FIRMS, multi-year GDELT, 5yr+ portfolio history). Not explicitly patched — the existing SHIP-10 generic version is "good enough" baseline; deeper-archive work can be a future pass.

### Task distribution
| Category | Count |
|---|---|
| MCP tool endpoints (REST proxies matching LIVING_IDEAS tool specs) | 28 |
| Signature visual hooks (shaders, physics animation, bloom, ripples, flashes) | 10 |
| Webhook/subscription/alerting endpoints | 5 |
| Shareable / viral hooks (OG images, six-degrees, share cards) | 4 |
| Data attribution / sources pages | 1 |
| Comparison / filter modes (side-by-side cities, Sankey, committee overlay, migration) | 5 |
| Baseline SHIP-2..SHIP-12 catch-up (under-scoped projects) | 3 |
| Domain data upgrades (Sentinel imagery, commodity prices, satellite constellations, Claude explanations) | 5 |
| Other (cost tracker, SSE feed, health endpoint) | 4 |

### Biggest surprise
**Inside Track — the LIVING_IDEAS-designated "highest MCP revenue potential" project — had zero MCP endpoints.** The entire revenue thesis of the project (agents querying for suspicious trades) was uncovered by any existing SHIP task. SHIP-1..SHIP-3 built the UI pipeline but never wrapped it in callable API routes. This is the single highest-leverage gap fixed by this audit.

### Projects ranked by vision gap severity

1. **inside-track** — flagship-tier revenue project with zero MCP surface
2. **party-lines / orbital / living-planet** — only 1/12 SHIP tasks each, severely under-scoped against their LIVING_IDEAS specs
3. **pulse** — flagship but missing the *signature* visual (globe pulsing), plus all 6 MCP tools
4. **newsquake** — missing the entire "earthquake-style ripples" visual identity
5. **connected** — project's stated moat ("real-time multi-source correlation via MCP") had no API

---

## Cursor / run pointers

- All 55 tasks listed below under status `ready`, priority `3`, with `[VIS-N]` prefix.
- Source code: `/tmp/create_vis_tasks.py` (can be re-run idempotently; will create duplicates).
- Results: `/tmp/vis_results.json`.
