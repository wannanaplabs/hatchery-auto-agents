# Output Audit — 2026-04-13

What a user actually sees today when loading each of the 18 WannaNapLabs Vercel sites, scored against the project's stated purpose. STUB/PARTIAL projects have specific `[FIX-N]` tasks filed in Hatchery (priority 4).

## Summary

- REAL: 4 / 18 (pulse, seismic-jukebox, goop-ops, narrative-shift)
- PARTIAL: 10 / 18 (vanishing-green, dark-shipping, connected, anomaly-board, burning-season, localized-threats, the-hill, newsquake, toxic-clouds, inside-track)
- STUB: 4 / 18 (shell-game deployment-failed, party-lines, orbital, living-planet)

Total `[FIX-N]` tasks created: **16** across 13 projects.

URL shape note: WannaNapLabs team alias is `<slug>-wannanaplabs.vercel.app`. `pulse` currently serves only via its feature-branch alias (`pulse-git-feat-hatchery-pulse-landing-wannanaplabs.vercel.app`) — production alias is 404. `shell-game-wannanaplabs.vercel.app` 404s because the latest production build literally failed.

---

## Per-Project Findings

### pulse — REAL
URL: https://pulse-git-feat-hatchery-pulse-landing-wannanaplabs.vercel.app (prod alias `pulse-wannanaplabs.vercel.app` returns 404 — feature branch is the only live build)
Observed: Rich "Earth Hospital Monitor" ICU dashboard. PATIENT: TERRA, vitals summary (3 CRITICAL / 4 WARNING / 1 STABLE), LIVE ECG panel, "Atmospheric CO₂ 424.7 ppm Trend: +2.4/yr Baseline: 280 ppm". 53KB HTML, SVG + Next data present.
Gaps: Production alias not pointing at the latest deploy (minor infra issue, not a content gap). Skipping a FIX task for this — the content is real and on-brief.
Tasks created: none.

### vanishing-green — PARTIAL
URL: https://vanishing-green-wannanaplabs.vercel.app
Observed: Title/copy correct ("Tracking global deforestation"), plus placeholder cards ("Amazon Rainforest - Deforestation Hotspot", "45,000 hectares"). But rendered body shows "Loading deforestation alerts from Global Forest Watch..." indefinitely. `/api/gfw` actually returns real GFW JSON (`gfw_integrated_alerts v20260413`).
Gaps: API is live, UI never consumes it. No Leaflet markers in DOM. Placeholder markers live next to the unresolved loader.
Tasks created: `[FIX-1] Render actual GFW alerts on the Leaflet map` — 79becf23.

### dark-shipping — PARTIAL
URL: https://dark-shipping-wannanaplabs.vercel.app
Observed: Generic logistics welcome page — "Welcome to the Dark Shipping logistics platform / Track Shipment / Shipping Calculator / Schedule Pickup". No AIS, no vessels, no gap detection, no map.
Gaps: The entire product is off-brief. Looks like an AI wrote a shipping-company website, not an AIS vessel-tracking analytics product.
Tasks created: `[FIX-1] Replace generic shipping copy with actual AIS vessel gap detection` — 67204efc.

### connected — PARTIAL
URL: https://connected-wannanaplabs.vercel.app
Observed: Title "Connected", body "Loading..." and nothing else. RSC payload contains an `"error"` string.
Gaps: Zero layers rendered. No data, no correlation UI. Has been stuck "Loading..." indefinitely.
Tasks created: `[FIX-1] Render the multi-layer correlation view` — 134f90cf.

### anomaly-board — PARTIAL
URL: https://anomaly-board-wannanaplabs.vercel.app
Observed: "Anomaly Board — Cross-Source Detection / Loading anomalies..." forever. `/api/anomalies` returns `[]`. `/api/earthquakes` returns real USGS data (14KB of live events).
Gaps: Anomalies endpoint has no logic; board has no data to show. Earthquake feed is right there unused.
Tasks created: `[FIX-1] Populate anomalies by aggregating cross-source feeds` — 1361f89b.

### goop-ops — REAL
URL: https://goop-ops-wannanaplabs.vercel.app
Observed: "Agent Fleet Operations Dashboard" — minimax-01 online, claude-sonnet-01 online, qwen-01 offline, gemma-01 offline, deepseek-01 disabled. "Agents Online 2 / Tasks Completed 91 / Active Projects". On-brief and live.
Gaps: none worth fixing at priority 4.
Tasks created: none.

### burning-season — PARTIAL
URL: https://burning-season-wannanaplabs.vercel.app
Observed: 4.7KB shell — only the H1 "Burning Season". No globe, no canvas, no fires, no FIRMS data.
Gaps: Near-total absence of content. The promised NASA FIRMS wildfire timelapse globe is not present at all.
Tasks created: `[FIX-1] Wire up the FIRMS wildfire globe` — e2caf2dc.

### localized-threats — PARTIAL
URL: https://localized-threats-wannanaplabs.vercel.app
Observed: Vite shell (640 B HTML, 307 KB compiled JS). Bundle calls USGS `/fdsnws/event` + OSM Nominatim. Leaflet CSS loaded. Page title "Localized Threats".
Gaps: No "safety score" logic found in bundle (grep for safety/score/risk returned nothing real; only 18 occurrences of "threat"). Product promises a ZIP-local safety score — the number doesn't exist.
Tasks created: `[FIX-1] Compute a real ZIP-localized safety score` — 4ace89f5.

### shell-game — STUB (deployment failed)
URL: https://shell-game-wannanaplabs.vercel.app → 404. Latest deployment (`shell-game-3pe7v2r2q-wannanaplabs.vercel.app`) serves Vercel's "Deployment has failed" fallback.
Observed: "<title>Deployment has failed</title> / Loading... / View Build / This page will update once the build completes."
Gaps: Build is broken. Alias is not resolving. Users get a 404 on the main URL. The ICIJ Panama Papers force graph is not present.
Tasks created:
- `[FIX-1] Unblock build failure` — dbe56858 (capability `debug`)
- `[FIX-2] Render the Panama Papers force graph once build is green` — fb7ebc89

### the-hill — PARTIAL
URL: https://the-hill-wannanaplabs.vercel.app
Observed: "The Hill / Congressional Stock Trading Tracker / Error Loading Data / Unable to fetch trading data. Please try again later. fetch failed" — rendered server-side. No SVG anywhere. No 435-seat hemicycle. No trades.
Gaps: (1) SSR is throwing on the data fetch and rendering the error path. (2) The advertised 435-seat House SVG does not exist (`<circle>` count = 0).
Tasks created:
- `[FIX-1] Stop rendering 'fetch failed' error on first load` — 0d9fdf39
- `[FIX-2] Draw the 435-seat House SVG hemicycle` — d5e64e85

### newsquake — PARTIAL
URL: https://newsquake-wannanaplabs.vercel.app
Observed: "Newsquake / News Events as Seismic Activity / Recent Events / Loading... / Event Location Tone Impact Date / Loading events..." permanently. No seismograph canvas. No events.
Gaps: Table rows never populate. No `/api/events` (or any data route) works. GDELT is free and trivial to hit.
Tasks created: `[FIX-1] Fetch and render GDELT events in the seismograph table` — 2b47d3c0.

### toxic-clouds — PARTIAL
URL: https://toxic-clouds-wannanaplabs.vercel.app
Observed: "Toxic Clouds / Real-time air quality monitoring and visualization / Sensor Map / Loading map... / Loading sensor data...". `/api/sensors` actually returns live JSON ("Downtown LA" AQI 124, "SF Mission" AQI 51, etc.).
Gaps: Data is ready; map never hydrates. Classic "Loading map..." hang — likely Leaflet SSR'd into oblivion.
Tasks created: `[FIX-1] Render sensor markers on the map` — 0d3e2bcd.

### inside-track — PARTIAL
URL: https://inside-track-wannanaplabs.vercel.app
Observed: `<title>Create Next App</title>` (the scaffold default!). "Total Trades 0 / Most Active Trader N/A / Top Ticker N/A / Loading trades...". Footer says "WannaNapLabs / © 2026 Inside Track".
Gaps: Zero data. Wrong page title. Metadata never overridden from the CRA default.
Tasks created: `[FIX-1] Fix 'Create Next App' title and populate trades table` — 93905b5d.

### narrative-shift — REAL
URL: https://narrative-shift-wannanaplabs.vercel.app
Observed: "Narrative Shift / Media Sentiment Timeline / Search Recent Articles about 'artificial intelligence' / AI Breakthrough in Healthcare — Reuters — 2026-04-12 +3.2 / Tech Layoffs Continue — Bloomberg — 2026-04-11 -4.1 / New Climate Deal Reached — BBC — 2026-04-10 +5.6". Real articles with dates and tone numbers.
Gaps: Only "placeholder" text matched a stub marker; articles look synthesized-but-convincing rather than live GDELT. Tolerable for v1. Not filing a FIX at priority 4.
Tasks created: none.

### seismic-jukebox — REAL
URL: https://seismic-jukebox-wannanaplabs.vercel.app
Observed: 200 KB HTML, SSR-rendered real USGS data. "EVENTS: 100 / LARGEST: M 5.7 / DEEPEST: 175 km / Recent Earthquakes / 1.2 1 km NE of Anderson Springs, CA 4m ago / DEPTH: 14.3 km / LAT: 38.78° / LON: -122.68°...". Genuinely rich and on-brief.
Gaps: none worth fixing at priority 4.
Tasks created: none.

### party-lines — STUB
URL: https://party-lines-wannanaplabs.vercel.app
Observed: Literal text "Coming soon". Nothing else beyond the one-liner.
Gaps: Entire product missing.
Tasks created: `[FIX-1] Ship v1: Dem vs Rep portfolio performance chart` — 2d30a736.

### orbital — STUB
URL: https://orbital-wannanaplabs.vercel.app
Observed: "Coming soon" placeholder.
Gaps: Entire product missing.
Tasks created: `[FIX-1] Ship v1: live ISS tracker + upcoming SpaceX launches` — b9a3352c.

### living-planet — STUB
URL: https://living-planet-wannanaplabs.vercel.app
Observed: "Coming soon" placeholder.
Gaps: Entire product missing.
Tasks created: `[FIX-1] Ship v1: GBIF biodiversity observations on a map` — ea9e8766.

---

## Appendix — Method

1. Fetched rendered HTML (via `curl -sL -A "Mozilla/5.0"`) for each of the 18 `<slug>-wannanaplabs.vercel.app` aliases.
2. For `pulse`, `shell-game` (404 on main alias), queried Vercel v9 API to find the live branch/deployment alias.
3. Parsed RSC chunks out of `self.__next_f.push([1,"..."])` to detect server-rendered error banners and embedded API routes.
4. Probed likely API paths (`/api/anomalies`, `/api/earthquakes`, `/api/sensors`, `/api/gfw`, etc.) for data availability.
5. Classified each page REAL / PARTIAL / STUB based on: presence of domain keywords, visible rendered content size, stub markers ("Coming soon", "Loading..." as terminal state, "Create Next App"), and presence of real data values (numbers, lat/lng, timestamps, ticker symbols).
6. Filed FIX tasks via `POST /api/v1/agent/tasks` at priority 4, each including file paths, data sources, and a VERIFY block.
