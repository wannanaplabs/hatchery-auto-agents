# Codebase Awareness — Read Before You Write

The #1 cause of broken PRs is agents hallucinating things that don't exist: imaginary table names, wrong import paths, fictional packages, the wrong auth pattern. ALWAYS verify against the real codebase before writing code.

---

## Hard Rules

### Before touching ANY file:
1. **`grep -r <symbol>` the codebase** to see how it's used elsewhere
2. **Read 1+ existing similar file** to learn conventions (auth, imports, error handling, naming)
3. **Check `package.json`** — never import a package that isn't installed
4. **Check `tsconfig.json` paths** — `@/lib/x` resolves differently per project

### Before adding a database call:
1. `grep -r "from(\"" supabase/migrations/` to see actual table names
2. NEVER guess table names — verify in `lib/types.ts` or migrations
3. NEVER guess auth flow — read 1 existing `app/api/v1/agent/*/route.ts`

### Before adding an import:
1. `grep -r "from \"<package>\"" src/` to see how teammates import it
2. If 0 hits → confirm install with `npm ls <package>` first
3. If installed but unused elsewhere → that's a smell, double-check the package is what you think

### Before extending an endpoint:
1. Read the SIBLING route (e.g., editing `/release/route.ts` → read `/claim/route.ts`)
2. Mirror its auth pattern, error shape, table names
3. If your code looks WILDLY different, you're probably wrong

---

## Anti-patterns That Destroyed Real PRs

| Mistake | What broke |
|---|---|
| Used `tasks` table | Codebase uses `hatchery_tasks`. Production endpoint instantly broken. |
| Used `supabase.auth.getUser()` | That's HUMAN auth via cookie. Agents use Bearer API keys via `authenticateAgent()`. Returns 401. |
| Imported `createClient` for service code | Should be `createServiceClient`. Browser client has no service role. |
| Referenced `agent_sessions`, `workspace_members`, `api_keys` tables | Don't exist. Pure hallucination. |
| Used `@/lib/foo` | Some projects don't have that alias. `tsconfig.json` paths differ. |

Every one of these would have been caught by ONE grep. Don't skip the grep.

---

## Reading Order for an Unfamiliar Project

1. `README.md` — what does this project DO
2. `package.json` — what's the stack
3. `app/layout.tsx` (or `src/app/layout.tsx`) — global wiring, providers
4. `app/page.tsx` — the home view (this is what users see)
5. `lib/` or `src/lib/` — shared utilities, auth, db clients
6. ONE file in `app/api/` or `src/components/` similar to what you're building

If you can't name 3 conventions used by THIS project (auth pattern, file naming, import alias), you have not read enough.

---

## Use `context7` MCP for current docs

Your training data lies about package APIs. Before writing code that uses any package, call:

```
mcp__context7__resolve-library-id(libraryName="next")
mcp__context7__get-library-docs(library="/vercel/next.js", topic="app-router api routes")
```

Specifically for Next.js 15 App Router, React 19, Tailwind v4, Supabase JS v2 — your training data is from before these versions shipped breaking changes.

## Use `hatchery` MCP to coordinate

Don't blindly write — call `hatchery_get_project_spec(<id>)` first to get the project's vision and conventions. Call `hatchery_get_workspace_state(<id>)` for active decisions and conventions other agents have established.

---

## When in Doubt

**Ask, don't guess.** Use `request_human` on the task with a specific question. A 30s pause for clarification beats 10min producing broken code.
