"""External retrieval sources for fresh evidence.

Adapters for OpenAlex, Crossref, AlphaXiv, and Semantic Scholar APIs with
local caching, retry/backoff, and normalization to EvidenceItem.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

import requests

from .db import Repository
from .evidence_source import EvidenceSource
from .models import EvidenceItem, new_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

class RetrievalCache:
    """SQLite-backed cache for retrieval responses."""

    def __init__(self, repo: Repository, ttl_hours: int = 24):
        self.repo = repo
        self.ttl_hours = ttl_hours

    def _key(self, source: str, query: str) -> str:
        raw = f"{source}:{query}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, source: str, query: str) -> Optional[list[dict]]:
        key = self._key(source, query)
        cached = self.repo.get_cached_retrieval(key)
        if cached:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def put(self, source: str, query: str, results: list[dict]) -> None:
        key = self._key(source, query)
        self.repo.save_cached_retrieval(
            cache_key=key,
            source_name=source,
            query=query,
            response_json=json.dumps(results),
            result_count=len(results),
            ttl_hours=self.ttl_hours,
        )


# ---------------------------------------------------------------------------
# HTTP helper with retry/backoff
# ---------------------------------------------------------------------------

def _http_get(url: str, params: dict | None = None, headers: dict | None = None,
              timeout: int = 15, max_retries: int = 2, backoff: float = 1.0) -> Optional[dict]:
    """GET with retry/backoff. Returns parsed JSON or None on failure."""
    hdrs = {"User-Agent": "BreakthroughEngine/1.0 (mailto:noreply@scires.dev)"}
    if headers:
        hdrs.update(headers)

    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = backoff * (2 ** attempt)
                logger.warning("Rate limited by %s, waiting %.1fs", url, wait)
                time.sleep(wait)
                continue
            logger.warning("HTTP %d from %s", resp.status_code, url)
            return None
        except requests.RequestException as e:
            logger.warning("Request failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, e)
            if attempt < max_retries:
                time.sleep(backoff * (2 ** attempt))
    return None


# ---------------------------------------------------------------------------
# OpenAlex Retrieval Source
# ---------------------------------------------------------------------------

OPENALEX_API = "https://api.openalex.org/works"


class OpenAlexRetrievalSource(EvidenceSource):
    """Retrieves evidence from OpenAlex (free, no API key required)."""

    def __init__(
        self,
        cache: Optional[RetrievalCache] = None,
        from_date: Optional[str] = None,
        timeout: int = 15,
    ):
        self.cache = cache
        self.from_date = from_date
        self.timeout = timeout

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        query = domain.replace("-", " ")
        cache_key_query = f"openalex:{query}:{limit}:{self.from_date or ''}"

        if self.cache:
            cached = self.cache.get("openalex", cache_key_query)
            if cached is not None:
                logger.info("OpenAlex cache hit for '%s' (%d results)", query, len(cached))
                return [EvidenceItem(**item) for item in cached]

        params: dict = {
            "search": query,
            "per_page": min(limit, 50),
            "sort": "relevance_score:desc",
            "select": "id,doi,title,publication_date,authorships,abstract_inverted_index,relevance_score",
        }
        if self.from_date:
            params["filter"] = f"from_publication_date:{self.from_date}"

        data = _http_get(OPENALEX_API, params=params, timeout=self.timeout)
        if not data or "results" not in data:
            logger.warning("OpenAlex returned no results for '%s'", query)
            return []

        items = []
        for work in data["results"][:limit]:
            item = self._parse_work(work)
            if item:
                items.append(item)

        if self.cache and items:
            self.cache.put("openalex", cache_key_query,
                           [item.model_dump() for item in items])

        logger.info("OpenAlex: retrieved %d items for '%s'", len(items), query)
        return items

    def _parse_work(self, work: dict) -> Optional[EvidenceItem]:
        title = work.get("title") or ""
        if not title or len(title.strip()) < 5:
            return None

        # Reconstruct abstract from inverted index if available
        abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
        quote = abstract[:500] if abstract else title

        # Authors
        authorships = work.get("authorships") or []
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in authorships[:3]
        )
        if len(authorships) > 3:
            authors += " et al."

        doi = work.get("doi") or ""
        pub_date = work.get("publication_date") or ""
        openalex_id = work.get("id") or ""
        relevance = work.get("relevance_score")
        if relevance is not None:
            # OpenAlex relevance_score can be large; normalize to 0-1
            relevance = min(1.0, float(relevance) / 200.0) if relevance > 1 else float(relevance)
        else:
            relevance = 0.5

        source_id = doi if doi else openalex_id
        citation = f"{authors} ({pub_date[:4]})" if authors else f"OpenAlex {pub_date[:4]}"

        return EvidenceItem(
            id=new_id(),
            source_type="openalex",
            source_id=source_id,
            title=title[:200],
            quote=quote,
            citation=citation,
            relevance_score=relevance,
        )

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict | None) -> str:
        """Reconstruct abstract text from OpenAlex inverted index format."""
        if not inverted_index:
            return ""
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return " ".join(w for _, w in word_positions)


# ---------------------------------------------------------------------------
# Crossref Retrieval Source
# ---------------------------------------------------------------------------

CROSSREF_API = "https://api.crossref.org/works"


class CrossrefRetrievalSource(EvidenceSource):
    """Retrieves evidence from Crossref (free, no API key required)."""

    def __init__(
        self,
        cache: Optional[RetrievalCache] = None,
        from_date: Optional[str] = None,
        timeout: int = 15,
    ):
        self.cache = cache
        self.from_date = from_date
        self.timeout = timeout

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        query = domain.replace("-", " ")
        cache_key_query = f"crossref:{query}:{limit}:{self.from_date or ''}"

        if self.cache:
            cached = self.cache.get("crossref", cache_key_query)
            if cached is not None:
                logger.info("Crossref cache hit for '%s' (%d results)", query, len(cached))
                return [EvidenceItem(**item) for item in cached]

        params: dict = {
            "query": query,
            "rows": min(limit, 50),
            "sort": "relevance",
            "order": "desc",
            "select": "DOI,title,author,abstract,published-print,published-online,score",
        }
        if self.from_date:
            params["filter"] = f"from-pub-date:{self.from_date}"

        data = _http_get(CROSSREF_API, params=params, timeout=self.timeout)
        if not data or "message" not in data:
            logger.warning("Crossref returned no results for '%s'", query)
            return []

        message = data["message"]
        works = message.get("items", [])

        items = []
        for work in works[:limit]:
            item = self._parse_work(work)
            if item:
                items.append(item)

        if self.cache and items:
            self.cache.put("crossref", cache_key_query,
                           [item.model_dump() for item in items])

        logger.info("Crossref: retrieved %d items for '%s'", len(items), query)
        return items

    def _parse_work(self, work: dict) -> Optional[EvidenceItem]:
        titles = work.get("title") or []
        title = titles[0] if titles else ""
        if not title or len(title.strip()) < 5:
            return None

        abstract = work.get("abstract") or ""
        # Crossref abstracts may contain JATS XML tags
        if abstract:
            import re
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        quote = abstract[:500] if abstract else title

        authors = work.get("author") or []
        author_str = ", ".join(
            f"{a.get('family', '')}" for a in authors[:3]
        )
        if len(authors) > 3:
            author_str += " et al."

        doi = work.get("DOI") or ""
        pub_date_parts = (
            work.get("published-print", {}).get("date-parts", [[]])
            or work.get("published-online", {}).get("date-parts", [[]])
        )
        year = str(pub_date_parts[0][0]) if pub_date_parts and pub_date_parts[0] else ""

        score = work.get("score")
        if score is not None:
            relevance = min(1.0, float(score) / 200.0) if score > 1 else float(score)
        else:
            relevance = 0.5

        source_id = f"doi:{doi}" if doi else f"crossref:{new_id()}"
        citation = f"{author_str} ({year})" if author_str else f"Crossref {year}"

        return EvidenceItem(
            id=new_id(),
            source_type="crossref",
            source_id=source_id,
            title=title[:200],
            quote=quote,
            citation=citation,
            relevance_score=relevance,
        )


# ---------------------------------------------------------------------------
# AlphaXiv Retrieval Source
# ---------------------------------------------------------------------------

ALPHAXIV_PAPER_API = "https://api.alphaxiv.org/papers/v3"


class AlphaXivRetrievalSource(EvidenceSource):
    """Retrieves structured AI-generated overviews of arXiv papers via alphaxiv.org.

    For each arXiv paper in the local DB that matches the domain, fetches a
    machine-readable summary (intermediateReport) from the AlphaXiv API instead
    of requiring a full PDF download and parse cycle.

    API flow (no auth required):
      1. GET /papers/v3/{arxiv_id}           → resolve versionId UUID
      2. GET /papers/v3/{versionId}/overview/en → structured overview
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        cache: Optional[RetrievalCache] = None,
        timeout: int = 15,
    ):
        self.db = db
        self.cache = cache
        self.timeout = timeout

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        arxiv_papers = self._query_arxiv_papers(domain, limit)
        results: list[EvidenceItem] = []
        for paper in arxiv_papers:
            item = self._fetch_overview(paper)
            if item:
                results.append(item)
        logger.info(
            "AlphaXivRetrievalSource: fetched=%d/%d overviews, domain=%s",
            len(results), len(arxiv_papers), domain,
        )
        return results

    def _query_arxiv_papers(self, domain: str, limit: int) -> list[sqlite3.Row]:
        """Query DB for arXiv papers matching the domain keyword."""
        like = f"%{domain}%"
        try:
            return self.db.execute(
                """
                SELECT paper_id, arxiv_id, title, authors, doi
                FROM papers
                WHERE arxiv_id IS NOT NULL
                  AND (subjects LIKE ? OR title LIKE ?)
                ORDER BY relevance_score DESC
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        except Exception as e:
            logger.warning("AlphaXivRetrievalSource: DB query failed: %s", e)
            return []

    def _fetch_overview(self, paper: sqlite3.Row) -> Optional[EvidenceItem]:
        arxiv_id = paper["arxiv_id"]

        # Check cache first
        if self.cache:
            cached = self.cache.get("alphaxiv", arxiv_id)
            if cached and cached:
                return self._map_overview(paper, cached[0] if cached else {})

        # Step 1: resolve versionId
        meta = _http_get(f"{ALPHAXIV_PAPER_API}/{arxiv_id}", timeout=self.timeout)
        if not meta:
            logger.debug("AlphaXiv: no metadata for %s (paper may not be indexed)", arxiv_id)
            return None

        version_id = meta.get("versionId")
        if not version_id:
            return None

        # Step 2: fetch overview
        overview = _http_get(
            f"{ALPHAXIV_PAPER_API}/{version_id}/overview/en", timeout=self.timeout
        )
        if not overview:
            logger.debug("AlphaXiv: no overview for %s (versionId=%s)", arxiv_id, version_id)
            return None

        if self.cache:
            self.cache.put("alphaxiv", arxiv_id, [overview])

        return self._map_overview(paper, overview)

    def _map_overview(self, paper: sqlite3.Row, overview: dict) -> Optional[EvidenceItem]:
        arxiv_id = paper["arxiv_id"]
        title = paper["title"] or "Unknown Paper"

        # Prefer intermediateReport (LLM-optimised), fall back to summary fields
        quote = overview.get("intermediateReport") or ""
        if not quote:
            summary = overview.get("summary") or {}
            if isinstance(summary, dict):
                parts = []
                for field in ("problem", "solution", "results", "insights"):
                    val = summary.get(field)
                    if val:
                        parts.append(str(val))
                quote = " ".join(parts)
            elif isinstance(summary, str):
                quote = summary

        if not quote or len(quote.strip()) < 10:
            return None

        citation_parts = []
        authors_raw = paper["authors"] if "authors" in paper.keys() else ""
        if authors_raw:
            citation_parts.append(str(authors_raw)[:60])
        citation_parts.append(f"arXiv:{arxiv_id}")
        citation = " ".join(citation_parts)

        return EvidenceItem(
            id=new_id(),
            source_type="paper",
            source_id=f"arxiv:{arxiv_id}",
            title=title[:200],
            quote=quote[:1000],
            citation=citation,
            relevance_score=0.72,  # alphaxiv preprint tier (above 0.65 baseline, structured summary bonus)
        )


# ---------------------------------------------------------------------------
# Semantic Scholar Retrieval Source
# ---------------------------------------------------------------------------

S2_PAPER_SEARCH_API = "https://api.semanticscholar.org/graph/v1/paper/search"

# Fields to request from the S2 API in a single call
_S2_FIELDS = (
    "paperId,title,abstract,tldr,citationCount,influentialCitationCount,"
    "year,authors,externalIds,openAccessPdf"
)

# Baseline relevance score for S2 results (above OpenAlex 0.5 baseline due to
# TLDR quality and influential-citation signal)
_S2_BASE_RELEVANCE = 0.70


class SemanticScholarRetrievalSource(EvidenceSource):
    """Retrieves evidence from Semantic Scholar (https://api.semanticscholar.org).

    Fetches papers via /paper/search with the following enhancements over
    OpenAlex/Crossref:

    - **TLDR**: AI-generated one-sentence summary. Used as the quote when
      available — higher signal density than reconstructed abstracts.
    - **influentialCitationCount**: Citations where S2 classifies the citing
      paper as methodologically building on this work. Used to boost the
      relevance score, rewarding highly-cited foundational results.

    Authentication:
        Set ``SEMANTIC_SCHOLAR_API_KEY`` in the environment to use the
        authenticated tier (higher rate limits). If unset, falls back to the
        public (unauthenticated) tier — still functional but limited to
        ~100 req / 5 min.

    Usage:
        source = SemanticScholarRetrievalSource(api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"))
        items = source.gather("perovskite solar cells", limit=20)
    """

    def __init__(
        self,
        api_key: str = "",
        cache: Optional[RetrievalCache] = None,
        timeout: int = 15,
    ):
        self.api_key = api_key
        self.cache = cache
        self.timeout = timeout

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        query = domain.replace("-", " ").replace("_", " ")
        cache_key_query = f"s2:{query}:{limit}"

        if self.cache:
            cached = self.cache.get("semantic_scholar", cache_key_query)
            if cached is not None:
                logger.info("Semantic Scholar cache hit for '%s' (%d results)", query, len(cached))
                return [EvidenceItem(**item) for item in cached]

        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        params = {
            "query": query,
            "fields": _S2_FIELDS,
            "limit": min(limit, 100),
        }

        data = _http_get(S2_PAPER_SEARCH_API, params=params, headers=headers, timeout=self.timeout)
        if not data or "data" not in data:
            logger.warning("Semantic Scholar returned no results for '%s'", query)
            return []

        items = []
        for paper in data["data"][:limit]:
            item = self._parse_paper(paper)
            if item:
                items.append(item)

        if self.cache and items:
            self.cache.put("semantic_scholar", cache_key_query,
                           [item.model_dump() for item in items])

        logger.info("Semantic Scholar: retrieved %d items for '%s'", len(items), query)
        return items

    def _parse_paper(self, paper: dict) -> Optional[EvidenceItem]:
        title = (paper.get("title") or "").strip()
        if not title or len(title) < 5:
            return None

        # Prefer TLDR over abstract: more concise and already distilled
        tldr_obj = paper.get("tldr") or {}
        tldr_text = (tldr_obj.get("text") or "").strip() if tldr_obj else ""
        abstract = (paper.get("abstract") or "").strip()
        quote = tldr_text or abstract[:500] or title

        # Authors: up to 3, then "et al."
        authors_list = paper.get("authors") or []
        author_names = [a.get("name", "") for a in authors_list[:3] if a.get("name")]
        authors_str = ", ".join(author_names)
        if len(authors_list) > 3:
            authors_str += " et al."

        year = paper.get("year") or ""
        citation = f"{authors_str} ({year})" if authors_str else f"S2 {year}"

        # Resolve a stable source_id: prefer DOI, then arXiv, then S2 paper ID
        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI", "")
        arxiv_id = external_ids.get("ArXiv", "")
        s2_id = paper.get("paperId", "")
        if doi:
            source_id = f"doi:{doi}"
        elif arxiv_id:
            source_id = f"arxiv:{arxiv_id}"
        else:
            source_id = f"s2:{s2_id}"

        # Relevance score: base + influential-citation bonus (capped at 1.0)
        influential = paper.get("influentialCitationCount") or 0
        # Log scale so that 1 → +0.02, 10 → +0.06, 100 → +0.10, 1000 → +0.14
        import math
        influential_bonus = min(0.15, math.log1p(influential) * 0.03)
        relevance = min(1.0, _S2_BASE_RELEVANCE + influential_bonus)

        return EvidenceItem(
            id=new_id(),
            source_type="semantic_scholar",
            source_id=source_id,
            title=title[:200],
            quote=quote[:500],
            citation=citation,
            relevance_score=round(relevance, 4),
        )


# ---------------------------------------------------------------------------
# Composite Retrieval Source
# ---------------------------------------------------------------------------

class CompositeRetrievalSource(EvidenceSource):
    """Combines multiple retrieval sources into one, deduplicating by title."""

    def __init__(self, sources: list[EvidenceSource]):
        self.sources = sources

    def gather(self, domain: str, limit: int = 20) -> list[EvidenceItem]:
        all_items: list[EvidenceItem] = []
        seen_titles: set[str] = set()

        per_source = max(1, limit // max(1, len(self.sources)))
        for source in self.sources:
            try:
                items = source.gather(domain, limit=per_source)
                for item in items:
                    title_key = item.title.lower().strip()
                    if title_key not in seen_titles:
                        seen_titles.add(title_key)
                        all_items.append(item)
            except Exception as e:
                logger.warning("Retrieval source %s failed: %s", type(source).__name__, e)

        # Sort by relevance and trim
        all_items.sort(key=lambda x: x.relevance_score, reverse=True)
        return all_items[:limit]


# ---------------------------------------------------------------------------
# Phase 4B: Retrieval ranking and query construction
# ---------------------------------------------------------------------------

import re as _re

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "to",
    "for", "with", "on", "at", "from", "by", "as", "into", "through",
    "during", "before", "after", "and", "but", "or", "not", "so", "yet",
    "that", "this", "it", "its", "we", "our", "they", "their",
})


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text, removing stop words."""
    words = _re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2]


def build_retrieval_query(
    domain: str,
    mechanism: str = "",
    program_goal: str = "",
    prior_art_keywords: list[str] | None = None,
) -> str:
    """Build an improved retrieval query from multiple signal sources.

    Combines domain terms, mechanism keywords, program goal terms,
    and optional prior-art keywords for better retrieval precision.
    """
    parts: list[str] = []

    # Domain as base
    parts.append(domain.replace("-", " ").replace("_", " "))

    # Top mechanism keywords
    if mechanism:
        mech_kw = _extract_keywords(mechanism)[:6]
        if mech_kw:
            parts.append(" ".join(mech_kw))

    # Program goal keywords
    if program_goal:
        goal_kw = _extract_keywords(program_goal)[:4]
        if goal_kw:
            parts.append(" ".join(goal_kw))

    # Prior-art keywords
    if prior_art_keywords:
        parts.extend(prior_art_keywords[:3])

    # Deduplicate while preserving order
    seen: set[str] = set()
    tokens: list[str] = []
    for part in parts:
        for word in part.split():
            w = word.lower().strip()
            if w and w not in seen:
                seen.add(w)
                tokens.append(w)

    return " ".join(tokens[:20])


def rank_evidence(
    items: list[EvidenceItem],
    domain: str,
    mechanism: str = "",
    domain_keywords: set[str] | None = None,
    recency_weight: float = 0.1,
    evidence_ranking_weights: dict | None = None,
) -> list[tuple[EvidenceItem, dict]]:
    """Rank evidence items using a layered scoring approach.

    Returns list of (item, ranking_detail) sorted by composite score.
    Ranking layers:
    1. API relevance score (from OpenAlex/Crossref)
    2. Title/abstract domain keyword overlap
    3. Mechanism keyword overlap
    4. Recency bonus (if publication date available)

    Phase 9: evidence_ranking_weights allows policy-configurable layer weights.
    Keys: "api_relevance", "domain_overlap", "mechanism_overlap", "baseline"
    If None, uses defaults: api=0.35, domain=0.30, mech=0.20, baseline=0.15
    """
    if not items:
        return []

    mech_keywords = set(_extract_keywords(mechanism)) if mechanism else set()
    dom_keywords = domain_keywords or set()
    domain_terms = set(_extract_keywords(domain.replace("-", " ")))
    all_domain_kw = dom_keywords | domain_terms

    scored: list[tuple[EvidenceItem, dict, float]] = []

    for item in items:
        detail: dict = {}

        # Layer 1: API relevance
        api_score = item.relevance_score
        detail["api_relevance"] = round(api_score, 3)

        # Layer 2: Domain keyword overlap in title + quote
        item_text = f"{item.title} {item.quote}".lower()
        if all_domain_kw:
            dom_hits = sum(1 for kw in all_domain_kw if kw in item_text)
            domain_overlap = min(1.0, dom_hits / max(1, len(all_domain_kw)) * 3)
        else:
            domain_overlap = 0.5
        detail["domain_overlap"] = round(domain_overlap, 3)

        # Layer 3: Mechanism keyword overlap
        if mech_keywords:
            mech_hits = sum(1 for kw in mech_keywords if kw in item_text)
            mech_overlap = min(1.0, mech_hits / max(1, len(mech_keywords)) * 2)
        else:
            mech_overlap = 0.0
        detail["mechanism_overlap"] = round(mech_overlap, 3)

        # Layer 4: Recency bonus (parse year from citation)
        recency_bonus = 0.0
        year_match = _re.search(r"\b(20[12]\d)\b", item.citation)
        if year_match:
            year = int(year_match.group(1))
            if year >= 2024:
                recency_bonus = recency_weight
            elif year >= 2022:
                recency_bonus = recency_weight * 0.5
        detail["recency_bonus"] = round(recency_bonus, 3)

        # Composite score — weights configurable via evidence_ranking_weights policy param
        _w = evidence_ranking_weights or {}
        _api_w = _w.get("api_relevance", 0.35)
        _dom_w = _w.get("domain_overlap", 0.30)
        _mech_w = _w.get("mechanism_overlap", 0.20)
        _base_w = _w.get("baseline", 0.15)

        # Phase 10D: source-type-aware ranking adjustments
        # KG evidence gets a diversity bonus; findings retain trusted-anchor value
        _source_type_adj = _w.get("source_type_adjustments", {})
        _st_adj = _source_type_adj.get(item.source_type, 0.0)
        detail["source_type_adjustment"] = round(_st_adj, 3)

        composite = (
            api_score * _api_w
            + domain_overlap * _dom_w
            + mech_overlap * _mech_w
            + recency_bonus
            + _base_w * 0.5  # baseline
            + _st_adj  # source-type adjustment
        )
        detail["composite_score"] = round(composite, 3)
        detail["rank_explanation"] = (
            f"api={api_score:.2f} dom={domain_overlap:.2f} "
            f"mech={mech_overlap:.2f} recency={recency_bonus:.2f}"
        )

        scored.append((item, detail, composite))

    # Sort by composite score descending
    scored.sort(key=lambda x: x[2], reverse=True)

    # Phase 10I: Annotate with source_id for downstream diversity selection
    for item, detail, _ in scored:
        detail["source_id"] = item.source_id

    return [(item, detail) for item, detail, _ in scored]


def select_diverse_top_k(
    ranked: list[tuple[EvidenceItem, dict]],
    k: int,
    max_per_source: int = 1,
    diversity_penalty: float = 0.05,
) -> list[tuple[EvidenceItem, dict]]:
    """Select top-k items from ranked list with source diversity awareness.

    Phase 10I: Prevents ranking-layer concentration where all top-k items
    come from the same source_id. Uses a greedy selection with per-source
    cap and diversity penalty for already-seen sources.

    Algorithm:
    1. Start with the full ranked list (by composite score).
    2. Greedily select items: if a source is already represented,
       apply a diversity penalty to its effective score.
    3. Enforce max_per_source cap: skip items exceeding the cap.
    4. Extremely strong items (composite > 2nd-best by >=0.15) bypass the cap.

    Returns top-k (item, detail) pairs with updated ranking details.
    """
    if not ranked or k <= 0:
        return []

    # Annotate all items even for early return
    if len(ranked) <= k:
        result = []
        for item, detail in ranked:
            detail = dict(detail)
            detail["diversity_penalty"] = 0.0
            detail["effective_score"] = detail.get("composite_score", 0)
            detail["source_capped"] = False
            result.append((item, detail))
        return result

    selected: list[tuple[EvidenceItem, dict]] = []
    source_counts: dict[str, int] = {}
    bypass_threshold = 0.15  # score margin for cap bypass

    for item, detail in ranked:
        if len(selected) >= k:
            break

        source = item.source_id
        count = source_counts.get(source, 0)
        score = detail.get("composite_score", 0)

        # Check if this item should bypass the cap (exceptionally strong)
        # Only bypass when other sources ARE already represented in selected
        bypass = False
        if count >= max_per_source:
            other_scores = [
                d.get("composite_score", 0) for it, d in selected
                if it.source_id != source
            ]
            if other_scores:
                best_other_score = max(other_scores)
                if score - best_other_score >= bypass_threshold:
                    bypass = True

        if count >= max_per_source and not bypass:
            continue

        # Apply diversity penalty for repeated sources
        effective_score = score - (diversity_penalty * count)
        detail = dict(detail)  # copy to avoid mutating original
        detail["diversity_penalty"] = round(diversity_penalty * count, 3)
        detail["effective_score"] = round(effective_score, 3)
        detail["source_capped"] = count >= max_per_source

        selected.append((item, detail))
        source_counts[source] = count + 1

    # If we couldn't fill k items due to caps, relax and fill from remaining
    if len(selected) < k:
        selected_ids = {item.id for item, _ in selected}
        for item, detail in ranked:
            if len(selected) >= k:
                break
            if item.id not in selected_ids:
                detail = dict(detail)
                detail["diversity_penalty"] = 0.0
                detail["effective_score"] = detail.get("composite_score", 0)
                detail["source_capped"] = False
                detail["diversity_relaxed"] = True
                selected.append((item, detail))
                selected_ids.add(item.id)

    return selected
