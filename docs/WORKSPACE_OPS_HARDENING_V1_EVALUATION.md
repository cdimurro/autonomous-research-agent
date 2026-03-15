# Workspace Ops Hardening v1 — Post-Implementation Evaluation

**Date:** 2026-03-15
**Branch:** `battery-loop-hardening`
**Batch:** `workspace-ops-hardening-v1` (CC-BE-2465–2469)
**Tests:** 1650 passing, 0 failures
**Build:** Clean (Next.js production build, all pages compile)

---

## What Improved

### Job lifecycle (CC-BE-2466)
- Every job is now inspectable via `/jobs/[id]` with lifecycle timeline, config, output log, error display
- All job cards across all pages are clickable links to the detail page
- Rerun with same config supported
- Job detail page polls while running and reflects completion live

### Review workflow (CC-BE-2465)
- All three brief types (decision, research, diligence) now support review states
- Review states: awaiting_review, approved_for_validation, rejected_by_operator, needs_more_analysis, exported
- Review notes can be attached to any brief
- Review state visible as badges on brief cards
- PATCH API for updating review state programmatically
- Reusable ReviewControls component

### Auto-refresh (CC-BE-2467)
- useJobs hook detects running→completed transitions
- Research and Diligence pages auto-refresh briefs when their jobs finish
- Home page auto-refreshes all briefs on any job completion
- No more manual page reload needed after job submission

### Export (CC-BE-2468)
- Markdown export for all three brief types via `/api/briefs/export`
- Decision briefs: score, family, metrics, caveats, recommendation
- Research briefs: directions, evidence quality, provenance footer
- Diligence briefs: signals, risks, recommendation, provenance footer
- Browser download triggered by ExportButton component
- Export available from Results page and individual brief pages

### Provenance/grounding (CC-BE-2468)
- ProvenancePanel component shows:
  - Generation source (AI/DeepSeek)
  - Whether structured engine data was used for grounding
  - Evidence quality (research) or confidence note (diligence)
  - Source list
  - Trust notice ("should be reviewed before use in decisions")
- Visible on Research and Diligence brief cards by default
- Clearly separates engine-grounded facts from LLM synthesis

---

## What Remains Awkward or Incomplete

### Medium priority
1. **No brief detail page** — briefs expand inline on their respective pages but there's no dedicated `/briefs/[id]` URL. This limits deep-linking and sharing.
2. **Review workflow is workspace-only** — decision briefs from the Python backend already have review states via `battery_review.py` CLI. The workspace can update them but there's no sync mechanism. Two sources of truth for decision brief review state.
3. **No notification/toast system** — job completion, review saves, and exports are silent or use inline state. A minimal toast system would improve feedback.
4. **Validate page doesn't auto-refresh** — validation jobs produce decision briefs, but the Validate page doesn't watch for job completions to refresh its view.

### Low priority
5. **No HTML/PDF export** — only Markdown is supported. HTML would be trivial to add but PDF requires a dependency.
6. **Research/diligence don't link back to their source job** — briefs don't store which job created them (only jobs store result_id, not vice versa).
7. **No brief deletion** — once created, briefs can only be reviewed/exported, not deleted.
8. **Assistant doesn't know about review state changes** — the assistant's grounding context includes brief data but doesn't reflect review state or notes.
9. **Job rerun doesn't navigate to the originating page** — the rerun button creates the job and navigates to the new job detail, but the user might expect to return to the workflow page.

---

## Evaluation of Specific Flows

### Validation flow (end to end)
- Submit battery benchmark from /validate → job created → appears in job list → clickable to /jobs/[id]
- Job runs → completes → decision brief generated → appears on Home and Results
- Brief expandable with human-facing summary, caveats, recommendation
- Technical details toggle for score components and parameters
- Export to Markdown works
- Review state update works
- **Verdict:** Solid. Main gap: Validate page doesn't auto-refresh briefs.

### Research flow (end to end)
- Submit topic from /research → job created → shown in Active Jobs
- Job completes → brief auto-appears (no reload needed)
- Brief shows: headline, summary, directions, rejections, recommendation
- Provenance panel shows grounding status and evidence quality
- Review controls allow state changes with notes
- Export produces well-structured Markdown with provenance footer
- **Verdict:** Good. Main gap: grounding is weak when no engine data exists (honest about it, but still limited).

### Diligence flow (end to end)
- Submit subject + focus areas from /diligence → job created → runs
- Brief auto-appears on completion
- Shows: signals, risks, open questions, recommendation, confidence note
- Provenance panel shows confidence and grounding status
- Review and export work
- **Verdict:** Good. Same grounding gap as research.

### Review/update/export cycle
- Open a brief → expand review section → select new state → add notes → save
- Review state badge updates on card
- Export brief → Markdown file downloads with current review state included
- **Verdict:** Works cleanly. Missing: no review history (only current state persisted).

---

## Where Is the Next Bottleneck?

### Bottleneck analysis

| Area | Status | Bottleneck? |
|------|--------|-------------|
| Product/workflow | 3 workflows connected, review/export work | **No** — adequate for internal use |
| Assistant quality | Page-aware, grounded in all brief types | **Moderate** — quality depends entirely on DeepSeek + available engine data |
| Storage/persistence | File-based, simple, works | **No** — fine for development scale |
| Domain breadth | Battery + PV benchmarks, AI research/diligence | **No** — not the current constraint |
| Deeper battery capability | Battery benchmark v2 + sidecar complete | **Low** — working well |
| Engine data density | Few decision briefs available for grounding | **Yes** — this is the bottleneck |

### The bottleneck is **engine data density**

The research and diligence workflows are honest about their grounding quality, but they're limited by how much structured engine data exists. When there are few or no decision briefs, the AI briefs are effectively ungrounded — the system correctly labels them as such, but the outputs are less useful.

The highest-leverage move is not more workspace features — it's generating more benchmark results so the AI workflows have richer grounding material.

---

## Recommendation: Next Focus

### Priority 1: Battery evaluation matrix sweep
Run the battery evaluation matrix on real infrastructure to generate a batch of decision briefs with diverse seeds, modes (ECM-only, sidecar, cathode, full V2), and families. This directly increases engine data density and makes research/diligence outputs meaningfully better.

### Priority 2: PyBaMM sidecar stability
Complete the live PyBaMM sidecar validation checkpoint. This unlocks higher-confidence decision briefs and makes the sidecar verification column in decision briefs genuinely informative rather than mocked.

### Priority 3: PV baseline on real infrastructure
Run the PV benchmark to establish a PV decision brief baseline. This adds cross-domain grounding material and tests the workspace with a second domain.

### Not recommended next
- DC-DC domain (no engine data yet to justify it)
- More workspace features (diminishing returns without more engine data)
- Project Zero merge (workspace needs more data-backed testing first)
- Design polish (not the constraint)
- Broader AI assistant features (grounding data is the constraint, not assistant capability)

---

## Summary

The workspace is now a credible internal operator tool:
- All workflows produce real outputs with clear provenance
- Every job is inspectable with lifecycle visibility
- Briefs are reviewable, exportable, and auto-refreshed
- AI-generated outputs are clearly labeled with grounding status
- The backend remains stable (1650 tests passing)

The next highest-value move is generating more engine data through benchmark sweeps, not adding more workspace features.
