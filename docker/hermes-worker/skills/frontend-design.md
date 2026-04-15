# Frontend Design Skill for WannaNapLabs Fleet

When building or redoing a hero view for a WannaNapLabs OSINT project, default to THIS stack and these aesthetic principles. Override only with explicit reason.

---

## Canonical 2026 Package Stack

### 3D / globe
- **`cobe`** — tiny dot-globe, ~2KB, best for background hero (orbital, pulse)
- **`@react-three/fiber` + `@react-three/drei` + `@react-three/postprocessing`** — full 3D scene with `<Bloom>` for ember/neon glow (burning-season, seismic-jukebox)
- **`r3f-globe`** (vasturiano) — opinionated geo layers, use when you want built-in rings/arcs/points on an R3F globe

### Maps
- **`react-map-gl` + `maplibre-gl`** (free base) + **`deck.gl`** overlays — the 2026 standard for interactive geo. Use `HeatmapLayer` for density, `ScatterplotLayer` for points, `IconLayer` for species/vessels, `ArcLayer` for connections.
- Never use raw Leaflet for new hero views — it's outdated vs deck.gl for data-heavy.

### Charts
- **`@tremor/react`** — polished KPI dashboards, Tailwind+Radix, Vercel-owned. Default for `goop-ops`, `party-lines`, `inside-track`.
- **`@visx/visx`** — D3 primitives in React. Use when you need custom shapes beyond tremor's presets (seismograph curves, sentiment stacked areas).

### Network / graph
- **`@cosmograph/react`** (v2) — GPU-accelerated WebGL. Default for `shell-game`, `connected`. Blows sigma.js + react-force-graph out of the water on >1k nodes.

### Animation
- **`motion`** (formerly framer-motion, now `motion/react`) — React 19 ready. Default for all transitions, page entrances, draggable UI, list reveal.
- **`gsap + lenis`** — add ONLY for granular timeline control or buttery scroll-jack. Default pages don't need it.

### Components
- **`shadcn/ui`** base (Radix + Tailwind, owned code via `npx shadcn@latest add`)
- **`@tremor/react`** layered on top for data-dense surfaces

### Audio
- **`tone.js` Analyser → `three.js` AudioAnalyser → R3F mesh** for audio-reactive 3D. Default for `seismic-jukebox`.

---

## Aesthetic Conventions

- **Dark background:** `bg-[#0a0a0a]`
- **Cards:** `bg-[#141414]` with `border border-white/10`
- **Text hierarchy:** primary `text-white`, secondary `text-white/70`, tertiary `text-white/40`
- **Accent colors per project type:**
  - Earth/planet: emerald `#34d399` or cyan `#22d3ee`
  - Fire/alert: amber-to-red `#fbbf24 → #ef4444`
  - Finance: green `#10b981` / red `#ef4444` (gain/loss intuitive)
  - News/sentiment: violet `#a78bfa`
- **Typography:** default Geist (Vercel), mono Geist Mono for data-heavy
- **Branding header:** top-left `wannanaplabs / <slug>` — `<span className="text-white/40">wannanap</span><span className="text-emerald-400">labs</span>` `<span className="text-white/30 mx-2">/</span>` `<span>{slug}</span>`
- **Feedback widget:** `<script async src="https://goop-feedback.vercel.app/widget.js" data-slug="<slug>" />` in `layout.tsx`

---

## Signature Moves

1. **Ripple / pulse on event** — the fleet's visual vocabulary. seismic-jukebox's earthquake ripples, the-hill's seat flashes, pulse's heartbeat, burning-season's ember emit. If a new event happens, ring it.
2. **Time-scrubber at bottom** — every data-over-time project gets a `motion` draggable scrubber with "Live" snap.
3. **Cards with staggered reveal** — `motion` `initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}`.
4. **Composite metric top-right** — a single giant number summarizing project state ("AQI: 42", "Safety: 87", "Fires: 12,847"). Use `<TextShimmer>` from shadcn or Tremor's `<DeltaBar>`.
5. **Hover-to-reveal** — on map/graph nodes, minimize always-on labels; use hover for detail, click for drawer.

---

## Always Use

- **`context7` MCP** (`@upstash/context7-mcp`) for current docs on any package. Don't trust training-data API signatures — look them up.
- **Pin `next@15.5.15`** exactly (CVE). `.npmrc` `legacy-peer-deps=true`.
- **`"use client"`** in ANY `.tsx` importing React hooks.
- **`dynamic(() => import(...), { ssr: false })`** for 3D/canvas components that can't SSR.

## Never Use

- **Leaflet** for new hero views (deck.gl instead)
- **Chart.js** (tremor or visx instead)
- **sigma.js / vanilla d3-force** for network (cosmograph instead)
- **`npm run dev` for verification** — use `npm run build` + `next start` headless + curl

---

## Quick Bootstrap Snippet

```bash
npm install --legacy-peer-deps next@15.5.15 react@19.0.0 react-dom@19.0.0 \
  motion cobe @react-three/fiber @react-three/drei @react-three/postprocessing \
  react-map-gl maplibre-gl deck.gl @tremor/react @visx/visx @cosmograph/react
```

Only install what the project actually uses. Tree-shake aggressively.
