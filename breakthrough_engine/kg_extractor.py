"""KG entity and relation extraction from paper segments.

Phase 10A: Extracts typed entities and relations from bt_paper_segments
into bt_kg_entities and bt_kg_relations. Extraction uses structured JSON
outputs from the local Ollama stack.

Shadow-only in this phase — does not affect production retrieval.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from .db import Repository
from .models import new_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENTITY_TYPES = frozenset({
    "material", "compound", "mechanism", "process", "property",
    "organism", "gene", "protein", "device", "method", "concept",
    "metric", "phenomenon", "structure", "technology",
})

RELATION_TYPES = frozenset({
    "causes", "inhibits", "enhances", "composed_of", "measured_by",
    "used_in", "produces", "degrades", "catalyzes", "related_to",
    "enables", "requires", "competes_with", "analog_of",
})

_EXTRACTION_PROMPT = """Extract scientific entities and relations from the text below.

Return ONLY valid JSON with this exact structure:
{
  "entities": [
    {"name": "entity name", "type": "one of: material|compound|mechanism|process|property|organism|gene|protein|device|method|concept|metric|phenomenon|structure|technology", "description": "brief description"}
  ],
  "relations": [
    {"source": "entity name 1", "target": "entity name 2", "type": "one of: causes|inhibits|enhances|composed_of|measured_by|used_in|produces|degrades|catalyzes|related_to|enables|requires|competes_with|analog_of", "description": "brief description of the relation"}
  ]
}

Rules:
- Extract only entities that are specific scientific concepts, not generic words.
- Each entity must have a type from the allowed list.
- Each relation must connect two entities found in the text.
- Return empty arrays if no meaningful entities or relations are found.
- Do NOT return markdown, explanations, or anything outside the JSON.

TEXT:
{text}
"""


@dataclass
class ExtractionConfig:
    """Configuration for entity/relation extraction."""
    ollama_host: str = "127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b-q4_K_M"
    ollama_timeout: int = 180
    min_confidence: float = 0.3
    max_entities_per_segment: int = 20
    max_relations_per_segment: int = 30


# ---------------------------------------------------------------------------
# LLM-based extractor
# ---------------------------------------------------------------------------

def _call_ollama_extraction(
    text: str,
    host: str = "127.0.0.1:11434",
    model: str = "qwen3.5:9b-q4_K_M",
    timeout: int = 180,
) -> Optional[dict]:
    """Call Ollama to extract entities and relations from text.

    Returns parsed JSON dict or None on failure.
    """
    import requests

    prompt = _EXTRACTION_PROMPT.format(text=text[:4000])

    try:
        resp = requests.post(
            f"http://{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {"num_predict": 2048, "temperature": 0.2},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        return _parse_extraction_response(content)
    except Exception as e:
        logger.warning("Ollama extraction call failed: %s", e)
        return None


def _parse_extraction_response(text: str) -> Optional[dict]:
    """Parse JSON from extraction response with fallback strategies."""
    if not text:
        return None

    # Try direct parse
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and ("entities" in data or "relations" in data):
            return data
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    import re
    for pattern in [r'```json\s*(.*?)\s*```', r'```\s*(.*?)\s*```', r'\{[\s\S]*\}']:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                candidate = match.group(1) if '```' in pattern else match.group()
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue

    return None


# ---------------------------------------------------------------------------
# Mock extractor for tests
# ---------------------------------------------------------------------------

class MockEntityRelationExtractor:
    """Deterministic extractor for offline tests. No LLM calls."""

    def extract_from_text(self, text: str, domain: str = "") -> dict:
        """Return a fixed extraction result based on text content."""
        words = text.lower().split()
        entities = []
        if any(w in words for w in ("solar", "perovskite", "photovoltaic")):
            entities.append({
                "name": "Perovskite Solar Cell",
                "type": "device",
                "description": "Solar cell using perovskite absorber",
            })
        if any(w in words for w in ("carbon", "co2", "capture")):
            entities.append({
                "name": "Carbon Capture",
                "type": "process",
                "description": "Process for capturing CO2",
            })
        if any(w in words for w in ("mof", "metal-organic", "framework")):
            entities.append({
                "name": "MOF-303",
                "type": "material",
                "description": "Metal-organic framework for gas adsorption",
            })

        if not entities:
            entities = [
                {"name": "Generic Concept", "type": "concept", "description": "Extracted concept"},
            ]

        relations = []
        if len(entities) >= 2:
            relations.append({
                "source": entities[0]["name"],
                "target": entities[1]["name"],
                "type": "related_to",
                "description": "Related concepts from the same text",
            })

        return {"entities": entities, "relations": relations}


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------

class EntityRelationExtractor:
    """Extracts entities and relations from paper segments.

    Processes bt_paper_segments with status 'scored' or 'ingested',
    writing results to bt_kg_entities and bt_kg_relations.
    """

    def __init__(
        self,
        repo: Repository,
        config: Optional[ExtractionConfig] = None,
        mock: bool = False,
    ):
        self.repo = repo
        self.config = config or ExtractionConfig()
        self._mock = MockEntityRelationExtractor() if mock else None

    def extract_from_segments(
        self, domain: str = "", limit: int = 50,
    ) -> dict:
        """Process pending segments and extract entities/relations.

        Returns summary stats.
        """
        stats = {
            "segments_processed": 0,
            "entities_extracted": 0,
            "relations_extracted": 0,
            "errors": 0,
            "domain": domain,
        }

        segments = self.repo.list_paper_segments(
            domain=domain, status="scored", limit=limit,
        )
        if not segments:
            # Also try 'ingested' status
            segments = self.repo.list_paper_segments(
                domain=domain, status="ingested", limit=limit,
            )

        for seg in segments:
            try:
                self._process_segment(seg, stats)
                stats["segments_processed"] += 1
            except Exception as e:
                logger.warning(
                    "Extraction error for segment %s: %s", seg["id"], e,
                )
                self.repo.update_segment_status(
                    seg["id"], "extraction_failed", str(e),
                )
                stats["errors"] += 1

        logger.info(
            "EntityRelationExtractor: processed=%d entities=%d relations=%d errors=%d",
            stats["segments_processed"], stats["entities_extracted"],
            stats["relations_extracted"], stats["errors"],
        )
        return stats

    def _process_segment(self, seg: dict, stats: dict) -> None:
        """Extract from a single segment."""
        text = seg.get("compressed_text") or seg.get("raw_text", "")
        if not text or len(text.strip()) < 30:
            self.repo.update_segment_status(seg["id"], "skipped", "text too short")
            return

        # Extract
        if self._mock:
            result = self._mock.extract_from_text(text, seg.get("domain", ""))
        else:
            result = _call_ollama_extraction(
                text,
                host=self.config.ollama_host,
                model=self.config.ollama_model,
                timeout=self.config.ollama_timeout,
            )

        if not result:
            self.repo.update_segment_status(
                seg["id"], "extraction_failed", "no extraction result",
            )
            stats["errors"] += 1
            return

        # Persist entities
        entity_name_to_id: dict[str, str] = {}
        raw_entities = result.get("entities", [])[:self.config.max_entities_per_segment]

        for raw_ent in raw_entities:
            name = str(raw_ent.get("name", "")).strip()
            if not name:
                continue
            etype = str(raw_ent.get("type", "concept")).lower()
            if etype not in ENTITY_TYPES:
                etype = "concept"

            ent_id = new_id()
            entity_name_to_id[name] = ent_id

            self.repo.save_kg_entity({
                "id": ent_id,
                "segment_id": seg["id"],
                "paper_id": seg.get("paper_id", ""),
                "entity_type": etype,
                "name": name,
                "canonical_name": name.lower().strip(),
                "description": str(raw_ent.get("description", ""))[:500],
                "confidence": 0.6,  # baseline for LLM extraction
                "domain": seg.get("domain", ""),
                "status": "extracted",
            })
            stats["entities_extracted"] += 1

        # Persist relations
        raw_relations = result.get("relations", [])[:self.config.max_relations_per_segment]

        for raw_rel in raw_relations:
            source_name = str(raw_rel.get("source", "")).strip()
            target_name = str(raw_rel.get("target", "")).strip()
            if not source_name or not target_name:
                continue

            source_id = entity_name_to_id.get(source_name)
            target_id = entity_name_to_id.get(target_name)
            if not source_id or not target_id:
                continue

            rtype = str(raw_rel.get("type", "related_to")).lower()
            if rtype not in RELATION_TYPES:
                rtype = "related_to"

            self.repo.save_kg_relation({
                "id": new_id(),
                "segment_id": seg["id"],
                "paper_id": seg.get("paper_id", ""),
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "relation_type": rtype,
                "description": str(raw_rel.get("description", ""))[:500],
                "confidence": 0.5,
                "domain": seg.get("domain", ""),
                "status": "extracted",
            })
            stats["relations_extracted"] += 1

        # Mark segment as extracted
        self.repo.update_segment_status(seg["id"], "extracted")
