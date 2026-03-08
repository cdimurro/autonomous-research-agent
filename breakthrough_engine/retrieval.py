"""External retrieval sources for fresh evidence.

Adapters for OpenAlex and Crossref APIs with local caching,
retry/backoff, and normalization to EvidenceItem.
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
