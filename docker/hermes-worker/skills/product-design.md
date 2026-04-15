# Product Design — Don't Ship Flat

The fleet's #1 wasted-resource pattern: building working code that renders nothing meaningful. A page that returns 200 with `<div></div>` is worse than a 500 — it lies about being done.

---

## The 5-Second Rule

When a user lands on the page, in the first 5 seconds they should:
1. **See** something visually distinct (not a blank dark theme)
2. **Understand** what the project does (one sentence in the layout)
3. **Want** to interact (something hover-able, click-able, or animated)

If your page fails any of those, it's not done — even if `npm run build` exits 0.

---

## Hero-First Architecture

Every project has ONE hero — the moment that makes the user say "oh wow." Build that first, polish second.

| Project | Hero |
|---|---|
| seismic-jukebox | Earth with audio-synced earthquake ripples |
| pulse | Globe pulsing with EKG waveform overlay |
| the-hill | 535 Capitol seats flashing on trade events |
| burning-season | Fire emitter particles on rotating Earth |
| orbital | ISS arc traced over rotating planet |

If your `app/page.tsx` doesn't render the hero, you're working on the wrong thing.

---

## Required States — Never Show A Blank Screen

Every data-fetching component MUST handle:

```tsx
{loading && <Skeleton />}                      // not just spinner
{error && <ErrorState onRetry={refetch} />}    // never silent
{!data?.length && <EmptyState message="Specific to this project's domain" />}
{data?.length > 0 && <RealView data={data} />}
```

Empty states are domain-specific. NOT "No data" — instead "No earthquakes detected in the last hour. The Earth is quiet right now." It's a chance to teach + delight.

---

## Interactive > Static (Always)

Default to interactive. If you wrote a static list, ask: could this be sortable? filterable? clickable to drill in? hoverable for detail?

| Boring | Engaging |
|---|---|
| `<table>` of trades | Sortable Tremor data table → expand row to timeline |
| List of species | Map with clustered markers → hover for popup |
| Chart of values over time | Brushable scrubber + crosshair + tooltip |
| Dot per earthquake | Pulsing ripple + audio sonification |

If your page has zero `onClick` / `onHover` / `onChange` handlers, it's not done.

---

## Design Conventions (don't reinvent)

| Need | Use |
|---|---|
| Dashboards / KPI cards | `@tremor/react` |
| Custom viz / shapes | `@visx/visx` |
| Maps + overlays | `react-map-gl` + `maplibre-gl` + `deck.gl` |
| 3D / globe | `@react-three/fiber` + `@react-three/drei` + `@react-three/postprocessing` (or `cobe` for tiny dot-globes) |
| Network / graph | `@cosmograph/react` |
| Animation | `motion` (formerly framer-motion) |
| Components | `shadcn/ui` (Radix + Tailwind) |
| Audio viz | `tone.js` + Three.js AudioAnalyser |

See `frontend-design.md` for full canonical stack.

---

## Branding Lock

Every page in the WannaNapLabs fleet MUST have:

```tsx
<header className="sticky top-0 z-50 border-b border-white/10 bg-[#0a0a0a]/80 backdrop-blur">
  <div className="container mx-auto flex h-14 items-center justify-between px-4">
    <Link href="/" className="font-mono text-sm">
      <span className="text-white/40">wannanap</span>
      <span className="text-emerald-400">labs</span>
      <span className="text-white/30 mx-2">/</span>
      <span>{slug}</span>
    </Link>
    <nav className="flex items-center gap-3 text-xs text-white/60">
      <button onClick={openAbout} className="hover:text-white">About</button>
      <a href={`https://github.com/wannanaplabs/${slug}`} className="hover:text-white">GitHub</a>
    </nav>
  </div>
</header>
```

And the feedback widget (one line):

```tsx
<script async src="https://goop-feedback.vercel.app/widget.js" data-slug={slug} />
```

---

## Verification — Don't Lie About Done

Before submitting:

1. `npm run build` exits 0
2. `npm run start` then `curl -s localhost:3000` — read the HTML
3. Verify the HTML contains the project's domain keywords (earthquake, AQI, deforestation, whatever)
4. Verify the HTML size > 5KB (a blank Next.js shell is ~3KB)
5. Verify no `<title>Create Next App</title>`, no "Coming soon", no "lorem ipsum"

If the page fails any of those — even though build passed — DON'T submit. Either fix it or `request_human`. A blank page marked "done" is a lie that costs the next agent another 10 minutes.

---

## Anti-Pattern Hall of Fame

❌ `return <div>{slug}</div>` — not a page, just a label
❌ `<Loading />` forever because no `useEffect` fired
❌ Map with no data points
❌ Chart with mock data committed to main
❌ Three sections that all show the same thing
❌ "Coming soon" anywhere
❌ Component named `<Foo />` that returns `null`

If you see yourself writing any of these — STOP. The task isn't ready. `request_human` for clarification.
