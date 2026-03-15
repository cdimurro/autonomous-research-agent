# Breakthrough Engine — Development Workspace

Internal development workspace for testing and iterating on Breakthrough Engine product surfaces.

**This is not the final production UI.** It is a lightweight internal tool that:
- mirrors future Project Zero product surfaces
- separates human-facing results from internal diagnostics
- makes background jobs visible and easy to inspect
- safely integrates AI assistance grounded in engine outputs
- supports 3 connected workflows: Validate, Research, Due Diligence

## Quick Start

```bash
cd workspace
npm install
cp .env.local.example .env.local   # Set DEEPSEEK_API_KEY for AI features
npm run dev
```

Open http://localhost:3000

## Pages

| Route | Purpose | Status |
|-------|---------|--------|
| `/` | **Home / Control Room** — active jobs, recent results, quick actions | Live |
| `/validate` | **Validate** — run battery or PV benchmark evaluations | Live |
| `/research` | **Research** — explore new solution directions, generate research briefs | Live |
| `/diligence` | **Due Diligence** — assess companies and technologies, generate diligence briefs | Live |
| `/results` | **Results** — browse all briefs, compare, inspect JSON, view artifacts | Live |

## Workflows

### Validate
Submits benchmark jobs to the Python engine (battery or PV). Results are
decision briefs with candidate scores, caveats, and recommendations.
Job execution spawns Python CLI processes.

### Research
Submits research jobs that use AI (DeepSeek) to generate structured research
briefs grounded in available engine data. Produces:
- Promising directions with confidence levels
- Rejected directions with reasons
- Recommended next action
- Evidence quality assessment

### Due Diligence
Submits diligence jobs that use AI to produce structured diligence briefs.
Produces:
- Key signals (positive/negative/neutral)
- Risks with severity ratings
- Open questions
- Recommendation with confidence note

### All workflows share:
- Same job backbone (queued → running → completed/failed)
- Same output pattern: human-facing brief (default) + technical diagnostics (toggle)
- Same status polling and background execution
- Results browsable from the Results page

## Architecture

```
workspace/
├── src/app/           # Next.js App Router (pages + API routes)
│   ├── api/jobs/      # Job creation, status, background execution
│   ├── api/briefs/    # Brief listing (all types, with filtering)
│   ├── api/artifacts/ # Artifact browsing
│   └── api/assistant/ # AI assistant (DeepSeek, page-aware)
├── src/components/    # Reusable UI components
│   ├── layout/        # Sidebar, AssistantShell
│   ├── jobs/          # Job status cards
│   ├── results/       # Brief rendering (decision, research, diligence)
│   └── assistant/     # AI assistant drawer (page-aware)
├── src/hooks/         # React hooks (useJobs, useBriefs)
└── src/lib/           # Backend integration, TypeScript types
```

### Backend Integration

The workspace reads from the parent directory's `runtime/` for all data:
- Decision briefs: `runtime/battery_briefs/`, `runtime/battery_exports/`
- Research & diligence briefs: `runtime/workspace_briefs/`
- Evaluation artifacts: `runtime/battery_eval/`
- Loop artifacts: `runtime/battery_loop/`, `runtime/pv_loop/`
- Job state: `runtime/workspace_jobs/`

**Validation jobs** spawn Python CLI processes (e.g., `python -m breakthrough_engine battery benchmark`).

**Research and diligence jobs** call the DeepSeek API with structured prompts grounded in available engine data.

**The Python backend is the source of truth for science.** The workspace reads, submits, renders, and generates AI-assisted briefs — it does not contain engine logic.

## Output Separation

Every result has two views:

1. **Human-facing** (default): headline, recommendation, tradeoffs, confidence, caveats, next step
2. **Technical/diagnostic** (toggle): score components, parameters, raw JSON, sidecar details, grounding sources

This pattern applies to all three brief types:
- **Decision Briefs**: candidate score, family, fast-charge/degradation metrics, sidecar verification
- **Research Briefs**: promising/rejected directions, evidence quality, rationale
- **Diligence Briefs**: signals, risks, open questions, recommendation, confidence note

## Results and Comparison

The Results page supports:
- Browsing all briefs across all types
- Filtering by type (Decision, Research, Diligence)
- Search across title, headline, family, topic, subject
- Side-by-side comparison of any 2 briefs
- JSON inspector with copy-to-clipboard
- Artifact grid for raw JSON files

## AI Assistant

Right-side drawer accessible from any page via the floating "AI" button.

- **Task-oriented**, not freeform chat
- **Page-aware** — shows relevant quick tasks for the current page
- **Grounded** in all brief types (decision, research, diligence)
- Will not invent facts — guides users to run workflows when data is missing
- Requires `DEEPSEEK_API_KEY` in `.env.local`
- Degrades gracefully without API key

Supported tasks:
- Compare candidates or research directions
- Summarize validation runs, research briefs, or diligence findings
- Explain promotions/rejections
- Generate founder/investor summaries
- Analyze risks and open questions
- Suggest what to test next
- Create executive summaries

## Brief Types

| Type | Source | Storage | Renderer |
|------|--------|---------|----------|
| Decision | Python benchmark loop | `runtime/battery_briefs/` | DecisionBriefCard |
| Research | DeepSeek API + grounding | `runtime/workspace_briefs/` | ResearchBriefCard |
| Diligence | DeepSeek API + grounding | `runtime/workspace_briefs/` | DiligenceBriefCard |

## Migration Path

This workspace is designed to migrate into Project Zero later:
- Route names match future product surfaces
- Components are modular and brief-type-specific
- Backend integration is thin (read artifacts, spawn CLI, call AI API)
- No engine logic in the frontend
- TypeScript types mirror backend Pydantic models
- Job/brief backbone is reusable

## What This Is Not

- Not a polished production app
- Not a general-purpose chatbot
- Not an Omniverse integration
- Not a replacement for the CLI
- Not a place for engine logic
- Not a full market intelligence platform (diligence is grounded, not inventive)

## Development

```bash
npm run dev      # Start dev server (with Turbopack)
npm run build    # Production build
npm run start    # Serve production build
```
