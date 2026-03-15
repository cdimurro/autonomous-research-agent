// Core workspace types — mirrors backend objects for the UI layer.

// ── Job states ──────────────────────────────────────────────────────────

export type JobStatus = "queued" | "running" | "completed" | "failed";

export type JobType =
  | "battery_benchmark"
  | "battery_validation"
  | "pv_benchmark"
  | "pv_validation"
  | "research"
  | "diligence";

export type ProductArea = "validate" | "research" | "diligence";

export interface Job {
  id: string;
  type: JobType;
  product_area: ProductArea;
  status: JobStatus;
  domain: "battery" | "pv" | "general";
  config: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  result_id: string | null;
}

// ── Decision Brief (mirrors BatteryDecisionBrief schema) ────────────────

export type ReviewState =
  | "awaiting_review"
  | "approved_for_validation"
  | "rejected_by_operator"
  | "needs_more_analysis"
  | "exported";

export type SidecarStatus =
  | "success"
  | "unavailable"
  | "error"
  | "invalid"
  | "not_verified";

export type SidecarGateDecision =
  | "confirmed"
  | "caveat"
  | "veto"
  | "not_verified";

export type ConfidenceTier = "high" | "standard" | "low" | "unverified";

export interface ScoreComponent {
  name: string;
  value: number;
  weight: number;
}

export interface DecisionBrief {
  id: string;
  brief_type: "decision";
  created_at: string;
  title: string;
  headline: string;
  candidate_id: string;
  candidate_family: string;
  chemistry: string;
  profile_confidence: string;
  final_score: number;
  score_components: ScoreComponent[];
  score_summary: string;
  fast_charge_retention: number | null;
  resistance_growth_pct: number | null;
  worst_stress_retention: number | null;
  cathode_thermal_retention: number | null;
  sidecar_status: SidecarStatus;
  sidecar_concordance: number | null;
  sidecar_gate_decision: SidecarGateDecision;
  sidecar_calibration_note: string | null;
  caveats: string[];
  confidence_tier: ConfidenceTier;
  review_state: ReviewState;
  why_promising: string;
  fast_charge_summary: string;
  degradation_summary: string;
  recommended_next: string;
  benchmark_seed: number | null;
  run_id: string | null;
  parameters: Record<string, unknown>;
}

// ── Research Brief ──────────────────────────────────────────────────────

export type EvidenceQuality = "strong" | "moderate" | "weak" | "insufficient";

export interface ResearchDirection {
  title: string;
  description: string;
  confidence: "high" | "medium" | "low";
  rationale: string;
}

export interface RejectedDirection {
  title: string;
  description: string;
  reason: string;
}

export interface ResearchBrief {
  id: string;
  brief_type: "research";
  created_at: string;
  topic: string;
  domain: string;
  headline: string;
  summary: string;
  promising_directions: ResearchDirection[];
  rejected_directions: RejectedDirection[];
  recommended_next: string;
  evidence_quality: EvidenceQuality;
  caveats: string[];
  grounding_sources: string[];
  raw_analysis: string;
  review_state: ReviewState;
  review_notes: string;
}

// ── Diligence Brief ─────────────────────────────────────────────────────

export type SignalType = "positive" | "negative" | "neutral";
export type Severity = "high" | "medium" | "low";

export interface DiligenceSignal {
  title: string;
  description: string;
  signal_type: SignalType;
}

export interface DiligenceRisk {
  title: string;
  description: string;
  severity: Severity;
}

export interface DiligenceBrief {
  id: string;
  brief_type: "diligence";
  created_at: string;
  subject: string;
  focus_areas: string[];
  headline: string;
  summary: string;
  strongest_signals: DiligenceSignal[];
  risks: DiligenceRisk[];
  open_questions: string[];
  recommendation: string;
  confidence_note: string;
  caveats: string[];
  grounding_sources: string[];
  raw_analysis: string;
  review_state: ReviewState;
  review_notes: string;
}

// ── Unified brief type ──────────────────────────────────────────────────

export type WorkspaceBrief = DecisionBrief | ResearchBrief | DiligenceBrief;
export type BriefType = "decision" | "research" | "diligence";

// ── Result (generic wrapper for any workflow output) ────────────────────

export type ResultType =
  | "benchmark_report"
  | "decision_brief"
  | "research_brief"
  | "diligence_brief"
  | "value_report"
  | "eval_matrix"
  | "diagnostic";

export interface WorkspaceResult {
  id: string;
  type: ResultType;
  domain: "battery" | "pv" | "general";
  product_area: ProductArea;
  title: string;
  created_at: string;
  summary: string | null;
  artifact_path: string | null;
  data: Record<string, unknown>;
}

// ── API response shapes ────────────────────────────────────────────────

export interface JobsResponse {
  jobs: Job[];
}

export interface BriefsResponse {
  briefs: WorkspaceBrief[];
}

export interface ArtifactsResponse {
  artifacts: Array<{
    name: string;
    path: string;
    size: number;
    modified_at: string;
    type: ResultType | "unknown";
  }>;
}
