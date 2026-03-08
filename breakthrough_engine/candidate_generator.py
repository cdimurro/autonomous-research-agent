"""Candidate hypothesis generation with provider abstraction.

Provides:
- FakeCandidateGenerator: deterministic output for tests
- DemoCandidateGenerator: varied but fake output for demos
- OllamaCandidateGenerator: real LLM-powered generation via Ollama
"""

from __future__ import annotations

import abc
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from .models import CandidateHypothesis, EvidenceItem, new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ollama configuration
# ---------------------------------------------------------------------------

@dataclass
class OllamaConfig:
    """Configuration for OllamaCandidateGenerator."""
    host: str = "127.0.0.1:11434"
    model: str = "qwen3.5:9b-q4_K_M"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: int = 300
    max_candidates: int = 10
    prompt_template: str = "default"
    retry_attempts: int = 3

    @classmethod
    def from_env(cls) -> OllamaConfig:
        return cls(
            host=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434"),
            model=os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M"),
            temperature=float(os.environ.get("BT_OLLAMA_TEMPERATURE", "0.7")),
            max_tokens=int(os.environ.get("BT_OLLAMA_MAX_TOKENS", "4096")),
            timeout_seconds=int(os.environ.get("BT_OLLAMA_TIMEOUT", "300")),
        )


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

CANDIDATE_GENERATION_PROMPT = """You are a scientific hypothesis generation engine. Your task is to generate novel, testable breakthrough candidate hypotheses based on provided evidence.

RULES:
- Each hypothesis must have an explicit mechanism (how it works physically/chemically/biologically)
- Each hypothesis must have a measurable expected outcome
- Each hypothesis must be testable within a realistic timeframe
- State all assumptions explicitly
- Note all risk flags
- Do NOT use marketing language, superlatives, or vague claims
- Do NOT claim "confirmed discovery" — these are candidates only
- Each hypothesis must reference at least one piece of evidence

OUTPUT FORMAT: Return ONLY valid JSON array. No markdown, no explanation, no preamble.
```json
[
  {
    "title": "Short descriptive title (max 80 chars)",
    "statement": "Clear, specific, testable hypothesis statement (2-4 sentences)",
    "mechanism": "Detailed explanation of the physical/chemical/biological mechanism (2-4 sentences)",
    "expected_outcome": "Quantitative or measurable expected result with units where applicable",
    "testability_window_hours": 24.0,
    "novelty_notes": "What makes this novel — cite specific gaps or cross-domain connections",
    "assumptions": ["assumption 1", "assumption 2"],
    "risk_flags": ["risk 1"]
  }
]
```
"""

EVIDENCE_BLOCK_TEMPLATE = """DOMAIN: {domain}

EVIDENCE ({count} items):
{evidence_text}

Generate {budget} candidate hypotheses. Focus on cross-evidence connections and testable predictions.
Each hypothesis must cite evidence by reference number."""


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------

class CandidateGenerator(abc.ABC):
    """Abstract interface for generating candidate hypotheses from evidence."""

    @abc.abstractmethod
    def generate(
        self,
        evidence: list[EvidenceItem],
        domain: str,
        budget: int = 10,
        run_id: str = "",
        diversity_context=None,
    ) -> list[CandidateHypothesis]:
        """Generate up to `budget` candidate hypotheses from evidence.

        diversity_context: optional DiversityContext used to steer generation
        away from saturated semantic regions. Ignored if None.
        """


# ---------------------------------------------------------------------------
# OllamaCandidateGenerator
# ---------------------------------------------------------------------------

class OllamaCandidateGenerator(CandidateGenerator):
    """Real candidate generation via local Ollama API.

    Calls the Ollama chat endpoint, parses structured JSON output into
    CandidateHypothesis objects, and applies validation/repair.
    """

    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or OllamaConfig.from_env()

    def generate(
        self,
        evidence: list[EvidenceItem],
        domain: str,
        budget: int = 10,
        run_id: str = "",
        diversity_context=None,
    ) -> list[CandidateHypothesis]:
        budget = min(budget, self.config.max_candidates)

        # Build the evidence block
        evidence_text = self._format_evidence(evidence)
        user_message = EVIDENCE_BLOCK_TEMPLATE.format(
            domain=domain,
            count=len(evidence),
            evidence_text=evidence_text,
            budget=budget,
        )

        # Append diversity steering if provided
        if diversity_context is not None:
            try:
                from .diversity import build_diversity_prompt_addendum
                addendum = build_diversity_prompt_addendum(diversity_context)
                if addendum:
                    user_message = user_message + addendum
                    logger.debug(
                        "Diversity addendum applied: sub_domain=%s excluded_topics=%d",
                        diversity_context.sub_domain,
                        len(diversity_context.excluded_topics),
                    )
            except Exception as e:
                logger.warning("Could not build diversity addendum: %s", e)

        # Call Ollama
        raw_response = self._call_ollama(
            system_prompt=CANDIDATE_GENERATION_PROMPT,
            user_message=user_message,
        )

        if not raw_response:
            logger.warning("Empty response from Ollama, returning empty candidate list")
            return []

        # Parse JSON from response
        parsed = self._parse_json_response(raw_response)
        if not parsed:
            logger.warning("Failed to parse Ollama response into candidates")
            return []

        # Convert to CandidateHypothesis objects
        candidates = self._convert_to_candidates(parsed, domain, run_id, evidence)

        # Deduplicate within this generation batch
        candidates = self._deduplicate_batch(candidates)

        return candidates[:budget]

    def _format_evidence(self, evidence: list[EvidenceItem]) -> str:
        lines = []
        for i, e in enumerate(evidence, 1):
            lines.append(
                f"[{i}] {e.title} ({e.citation})\n"
                f"    Quote: \"{e.quote[:300]}\"\n"
                f"    Relevance: {e.relevance_score:.2f}"
            )
        return "\n".join(lines)

    def _call_ollama(self, system_prompt: str, user_message: str) -> str:
        import requests

        url = f"http://{self.config.host}/api/chat"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "think": False,
            "options": {
                "num_predict": self.config.max_tokens,
                "temperature": self.config.temperature,
            },
        }

        for attempt in range(self.config.retry_attempts):
            try:
                resp = requests.post(
                    url, json=payload, timeout=self.config.timeout_seconds
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                if content:
                    return content
                logger.warning("Ollama returned empty content (attempt %d)", attempt + 1)
            except Exception as e:
                logger.warning("Ollama request failed (attempt %d): %s", attempt + 1, e)
                if attempt < self.config.retry_attempts - 1:
                    import time
                    time.sleep(2 ** (attempt + 1))

        return ""

    def _parse_json_response(self, text: str) -> list[dict] | None:
        """Extract JSON array from LLM response with multiple fallback strategies."""
        # Strategy 1: Direct parse
        stripped = text.strip()
        result = self._try_parse(stripped)
        if result is not None:
            return result

        # Strategy 2: Extract from markdown code block
        if "```json" in text:
            block = text.split("```json")[1].split("```")[0]
            result = self._try_parse(block.strip())
            if result is not None:
                return result
        elif "```" in text:
            block = text.split("```")[1].split("```")[0]
            result = self._try_parse(block.strip())
            if result is not None:
                return result

        # Strategy 3: Find JSON array via regex
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            result = self._try_parse(match.group())
            if result is not None:
                return result

        # Strategy 4: Find individual JSON objects and wrap in array
        objects = list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text))
        if objects:
            parsed_objects = []
            for m in objects:
                try:
                    obj = json.loads(m.group())
                    if "title" in obj or "statement" in obj:
                        parsed_objects.append(obj)
                except json.JSONDecodeError:
                    continue
            if parsed_objects:
                return parsed_objects

        logger.warning("All JSON parsing strategies failed")
        return None

    @staticmethod
    def _try_parse(text: str) -> list[dict] | None:
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Handle {"hypotheses": [...]} or {"candidates": [...]}
                for key in ("hypotheses", "candidates", "results"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                return [data]
        except (json.JSONDecodeError, TypeError):
            return None

    def _convert_to_candidates(
        self,
        parsed: list[dict],
        domain: str,
        run_id: str,
        evidence: list[EvidenceItem],
    ) -> list[CandidateHypothesis]:
        candidates = []
        for raw in parsed:
            try:
                candidate = self._coerce_candidate(raw, domain, run_id, evidence)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.warning("Failed to convert candidate: %s", e)
        return candidates

    def _coerce_candidate(
        self,
        raw: dict,
        domain: str,
        run_id: str,
        evidence: list[EvidenceItem],
    ) -> CandidateHypothesis | None:
        """Coerce a raw dict into a CandidateHypothesis, repairing common issues."""
        title = str(raw.get("title", "")).strip()
        statement = str(raw.get("statement", raw.get("hypothesis", ""))).strip()
        mechanism = str(raw.get("mechanism", "")).strip()
        expected_outcome = str(raw.get("expected_outcome", raw.get("outcome", ""))).strip()

        # Reject if critical fields are empty
        if not statement or len(statement) < 20:
            logger.debug("Rejecting candidate: statement too short or empty")
            return None
        if not mechanism or len(mechanism) < 10:
            logger.debug("Rejecting candidate: mechanism too short or empty")
            return None

        # Generate title if missing
        if not title:
            title = statement[:80].rstrip(". ") + "..."

        # Default expected outcome
        if not expected_outcome:
            expected_outcome = "Measurable outcome to be determined through experimentation."

        # Parse assumptions
        assumptions = raw.get("assumptions", [])
        if isinstance(assumptions, str):
            assumptions = [a.strip() for a in assumptions.split(",") if a.strip()]
        elif not isinstance(assumptions, list):
            assumptions = []
        assumptions = [str(a) for a in assumptions]

        # Parse risk flags
        risk_flags = raw.get("risk_flags", raw.get("risks", []))
        if isinstance(risk_flags, str):
            risk_flags = [r.strip() for r in risk_flags.split(",") if r.strip()]
        elif not isinstance(risk_flags, list):
            risk_flags = []
        risk_flags = [str(r) for r in risk_flags]

        # Parse testability window
        testability = raw.get("testability_window_hours", 24.0)
        try:
            testability = float(testability)
            if testability <= 0:
                testability = 24.0
        except (ValueError, TypeError):
            testability = 24.0

        # Novelty notes
        novelty = str(raw.get("novelty_notes", raw.get("novelty", ""))).strip()

        # Evidence refs - try to map reference numbers to actual evidence IDs
        evidence_refs = []
        raw_refs = raw.get("evidence_refs", raw.get("supporting_evidence", []))
        if isinstance(raw_refs, list):
            for ref in raw_refs:
                ref_str = str(ref).strip()
                # If it's a number, map to evidence by index
                try:
                    idx = int(ref_str) - 1
                    if 0 <= idx < len(evidence):
                        evidence_refs.append(evidence[idx].id)
                except ValueError:
                    # If it matches an evidence ID directly, use it
                    if any(e.id == ref_str for e in evidence):
                        evidence_refs.append(ref_str)
        # Default: attach first two evidence items
        if not evidence_refs and evidence:
            evidence_refs = [e.id for e in evidence[:2]]

        return CandidateHypothesis(
            id=new_id(),
            run_id=run_id,
            title=title[:200],
            domain=domain,
            statement=statement,
            mechanism=mechanism,
            expected_outcome=expected_outcome,
            testability_window_hours=testability,
            novelty_notes=novelty,
            assumptions=assumptions,
            risk_flags=risk_flags,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _deduplicate_batch(candidates: list[CandidateHypothesis]) -> list[CandidateHypothesis]:
        """Remove near-duplicates within a single generation batch."""
        from difflib import SequenceMatcher

        unique = []
        for c in candidates:
            is_dup = False
            for u in unique:
                sim = SequenceMatcher(None, c.statement.lower(), u.statement.lower()).ratio()
                if sim > 0.85:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(c)
        return unique


# ---------------------------------------------------------------------------
# Fake / Demo generators (preserved from v1)
# ---------------------------------------------------------------------------

class FakeCandidateGenerator(CandidateGenerator):
    """Fixed deterministic output for tests. Always returns the same candidates."""

    def generate(
        self,
        evidence: list[EvidenceItem],
        domain: str,
        budget: int = 10,
        run_id: str = "",
        diversity_context=None,
    ) -> list[CandidateHypothesis]:
        candidates = [
            CandidateHypothesis(
                id=f"fake_cand_001_{run_id[:8]}",
                run_id=run_id,
                title="Perovskite-Topological Insulator Hybrid Solar Cell",
                domain=domain,
                statement="Combining methylammonium-free perovskite absorbers with Bi2Te3 topological insulator contacts will increase power conversion efficiency to >26% by reducing surface recombination through topological surface states.",
                mechanism="Topological surface states in Bi2Te3 provide spin-momentum locked charge transport channels at the perovskite-contact interface, suppressing surface recombination. The spin-polarized nature of these states reduces backscattering of photogenerated carriers.",
                expected_outcome="Power conversion efficiency exceeding 26% in single-junction configuration, with reduced voltage deficit at the perovskite-contact interface measurable via photoluminescence quantum yield.",
                testability_window_hours=48.0,
                novelty_notes="No prior work has combined topological insulator contacts with methylammonium-free perovskites. This bridges two recent breakthroughs in independent fields.",
                assumptions=["Bi2Te3 surface states survive perovskite deposition", "Lattice mismatch is manageable at the interface"],
                risk_flags=["Interface stability under illumination unknown"],
                evidence_refs=[e.id for e in evidence[:2]] if evidence else [],
            ),
            CandidateHypothesis(
                id=f"fake_cand_002_{run_id[:8]}",
                run_id=run_id,
                title="MOF-Enhanced CRISPR Diagnostic Platform",
                domain=domain,
                statement="Integrating MOF-303 as a nucleic acid pre-concentration layer with CRISPR-Cas13 lateral flow assays will lower the detection limit to 1 copy/uL while maintaining >98% specificity.",
                mechanism="MOF-303's high surface area (1200 m2/g) and tunable pore chemistry selectively adsorb and concentrate target RNA from clinical samples. Released concentrated RNA is then detected by the CRISPR-Cas13 collateral cleavage reporter.",
                expected_outcome="10-fold improvement in detection limit (from 10 copies/uL to 1 copy/uL) with <5 minutes added to total assay time, validated on synthetic RNA standards.",
                testability_window_hours=24.0,
                novelty_notes="MOFs have not been applied as pre-concentration layers for CRISPR diagnostics. Combines materials science innovation with molecular biology.",
                assumptions=["MOF-303 does not inhibit Cas13 enzymatic activity", "RNA desorption from MOF is efficient at room temperature"],
                risk_flags=["MOF synthesis batch variability may affect reproducibility"],
                evidence_refs=[e.id for e in evidence[2:4]] if len(evidence) > 3 else [],
            ),
            CandidateHypothesis(
                id=f"fake_cand_003_{run_id[:8]}",
                run_id=run_id,
                title="Neuromorphic Carbon Capture Controller",
                domain=domain,
                statement="Deploying spiking neural network chips to control MOF-based carbon capture adsorption-desorption cycles will reduce energy consumption by 30% through real-time adaptive cycle optimization.",
                mechanism="Spiking neural networks process sensor data (CO2 concentration, temperature, pressure) with 10x lower power than GPUs. Real-time inference enables sub-second adjustment of desorption heating profiles, minimizing thermal energy waste during regeneration.",
                expected_outcome="30% reduction in energy consumption per kg CO2 captured, measured across 1000 automated cycles with consistent capture capacity (>7 mmol/g).",
                testability_window_hours=168.0,
                novelty_notes="First application of neuromorphic computing to direct air capture process control. Cross-domain innovation between computing architecture and climate technology.",
                assumptions=["Sensor data rates are compatible with SNN inference latency", "MOF thermal cycling does not degrade under rapid optimization"],
                risk_flags=["SNN training for process control is immature", "Long-term MOF stability needs validation"],
                evidence_refs=[e.id for e in evidence[4:6]] if len(evidence) > 5 else [],
            ),
        ]
        return candidates[:budget]


class DemoCandidateGenerator(CandidateGenerator):
    """Varied but fake output for local demos. Uses evidence content to seed variation."""

    def generate(
        self,
        evidence: list[EvidenceItem],
        domain: str,
        budget: int = 10,
        run_id: str = "",
        diversity_context=None,
    ) -> list[CandidateHypothesis]:
        # Reuse FakeCandidateGenerator but add variation based on evidence count
        base = FakeCandidateGenerator().generate(evidence, domain, budget, run_id)

        # Add a 4th candidate if budget allows and evidence is available
        if budget > 3 and evidence:
            base.append(
                CandidateHypothesis(
                    id=new_id(),
                    run_id=run_id,
                    title=f"Cross-Domain Synthesis: {evidence[0].title[:40]}",
                    domain=domain,
                    statement=f"Evidence from '{evidence[0].title}' suggests a novel pathway when combined with recent findings, potentially enabling a 2x improvement in the target metric.",
                    mechanism="Cross-domain evidence synthesis reveals complementary mechanisms that have not been tested in combination.",
                    expected_outcome="Measurable improvement in primary outcome metric, quantifiable within standard laboratory conditions.",
                    testability_window_hours=72.0,
                    novelty_notes="Cross-domain synthesis of independent research lines.",
                    assumptions=["Mechanisms from different domains are compatible"],
                    risk_flags=["Cross-domain transfer may not hold"],
                    evidence_refs=[evidence[0].id],
                )
            )

        return base[:budget]
