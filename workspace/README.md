# Breakthrough Engine — Development Workspace

Internal development workspace for testing and iterating on Breakthrough Engine product surfaces.

**This is not the final production UI.** It is a lightweight internal tool that:
- mirrors future Project Zero product surfaces
- separates human-facing results from internal diagnostics
- makes background jobs visible and easy to inspect
- safely integrates AI assistance grounded in engine outputs

## Quick Start

```bash
cd workspace
npm install
npm run dev
```

Open http://localhost:3000

## Pages

| Route | Purpose |
|-------|---------|
| `/` | **Home / Control Room** — active jobs, recent results, quick actions |
| `/validate` | **Validate** — run battery or PV benchmark evaluations |
| `/research` | **Research** — explore new solution directions |
| `/diligence` | **Due Diligence** — assess companies and technologies |
| `/results` | **Results** — inspect decision briefs, artifacts, raw JSON |

## Architecture

```
workspace/
├── src/app/           # Next.js App Router (pages + API routes)
│   ├── api/jobs/      # Job creation and status
│   ├── api/briefs/    # Decision brief listing
│   ├── api/artifacts/ # Artifact browsing
│   └── api/assistant/ # AI assistant (DeepSeek v3.2)
├── src/components/    # Reusable UI components
│   ├── layout/        # Sidebar, AssistantShell
│   ├── jobs/          # Job status cards
│   ├── results/       # Decision brief rendering, JSON viewer
│   └── assistant/     # AI assistant drawer
├── src/hooks/         # React hooks (useJobs, useBriefs)
└── src/lib/           # Backend integration, TypeScript types
```

### Backend Integration

The workspace reads from the parent directory's `runtime/` for all data:
- Decision briefs: `runtime/battery_briefs/`
- Exports: `runtime/battery_exports/`
- Evaluation artifacts: `runtime/battery_eval/`
- Job state: `runtime/workspace_jobs/`

Job execution spawns Python CLI processes (e.g., `python -m breakthrough_engine battery benchmark`).

**The Python backend is the source of truth.** The workspace only reads, submits, and renders — it does not contain engine logic.

## Output Separation

Every result has two views:

1. **Human-facing** (default): headline, recommendation, tradeoffs, confidence, caveats, next step
2. **Technical/diagnostic** (toggle): score components, parameters, raw JSON, sidecar details

Decision Briefs use this pattern. The Results page Artifacts tab exposes raw JSON with copy support.

## AI Assistant

Right-side drawer accessible from any page via the floating "AI" button.

- Task-oriented, not freeform chat
- Grounded in latest decision briefs and engine outputs
- Will not invent facts — guides users to run workflows when data is missing
- Requires `DEEPSEEK_API_KEY` in `.env.local` (copy from `.env.local.example`)
- Degrades gracefully without API key

Supported tasks:
- Compare candidates
- Summarize validation runs
- Explain promotions/rejections
- Generate founder/investor summaries
- Suggest what to test next

## Migration Path

This workspace is designed to migrate into Project Zero later:
- Route names match future product surfaces
- Components are modular
- Backend integration is thin (read artifacts, spawn CLI)
- No engine logic in the frontend
- TypeScript types mirror backend Pydantic models

## What This Is Not

- Not a polished production app
- Not a general-purpose chatbot
- Not an Omniverse integration
- Not a replacement for the CLI
- Not a place for engine logic

## Development

```bash
npm run dev      # Start dev server (with Turbopack)
npm run build    # Production build
npm run start    # Serve production build
```
