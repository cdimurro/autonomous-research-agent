# Breakthrough Engine -- External Retrieval

## Overview

The retrieval module provides access to fresh evidence from external academic APIs. It currently supports OpenAlex and Crossref as data sources, with a composite interface that combines and deduplicates results across sources.

**Module:** `breakthrough_engine/retrieval.py`

## Retrieval Sources

### OpenAlexRetrievalSource

Queries the OpenAlex API for academic papers matching a given search term. Returns structured metadata including titles, abstracts, citations, and relevance indicators.

### CrossrefRetrievalSource

Queries the Crossref API for works matching a given search term. Provides complementary coverage to OpenAlex, particularly for recently published or cross-disciplinary work.

### CompositeRetrievalSource

Combines multiple retrieval sources into a single interface. When queried, it fans out to all configured sources, collects results, and deduplicates by title before returning a unified result set. This is the primary entry point for retrieval in the pipeline.

## Normalization

All retrieval results are normalized to the `EvidenceItem` model regardless of their original source:

| Field             | Type    | Description                                          |
|-------------------|---------|------------------------------------------------------|
| `title`           | `str`   | Title of the retrieved work                          |
| `quote`           | `str`   | Relevant excerpt or abstract snippet                 |
| `citation`        | `str`   | Formatted citation string                            |
| `relevance_score` | `float` | Source-provided or computed relevance score           |
| `source_type`     | `str`   | Origin source (e.g., `openalex`, `crossref`)         |
| `source_id`       | `str`   | Unique identifier within the source                  |

This normalization ensures that downstream consumers (evidence evaluation, novelty checking) operate on a consistent data structure regardless of where the evidence originated.

## Caching

A `RetrievalCache` layer sits in front of HTTP calls, backed by the `bt_retrieval_cache` table. Key characteristics:

- **Configurable TTL:** Default time-to-live is 24 hours. Cached results within the TTL window are returned without making external API calls.
- **Key structure:** Cache keys are derived from the query parameters and source type.
- **Purpose:** Reduces redundant API calls, respects rate limits, and enables offline replay of recent queries.

## Retry and Backoff

The `_http_get` helper function handles all outbound HTTP requests with:

- **Exponential backoff:** Failed requests are retried with increasing delays between attempts.
- **Rate limit handling:** HTTP 429 responses trigger backoff behavior, respecting the source API's rate limits.
- **Timeout management:** Requests that exceed a configured timeout are treated as failures and enter the retry cycle.

## Offline Testing

All tests for the retrieval module mock HTTP calls at the transport layer. No live internet connection is required to run the test suite. This ensures:

- Tests are deterministic and repeatable.
- CI pipelines do not depend on external API availability.
- Rate limits and API keys are not consumed during development.

## Usage

The typical usage pattern in the pipeline:

1. Instantiate individual sources (`OpenAlexRetrievalSource`, `CrossrefRetrievalSource`).
2. Wrap them in a `CompositeRetrievalSource`.
3. Call the composite source with a search query derived from the candidate hypothesis.
4. Receive a deduplicated list of `EvidenceItem` objects for downstream evaluation.

Deduplication in the composite source is performed by title, ensuring that papers indexed by both OpenAlex and Crossref appear only once in the result set.
