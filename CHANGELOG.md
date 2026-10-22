# Changelog

## 1.2.0 — 2026-10-22

### Added

- Per-source `results` with original search URL, title, Markdown and plain text, ordered by search results.
- Docker Compose with a pinned SearXNG image, generated secret, JSON search, preinstalled Chromium and localhost-only API publishing.
- `/health`, contract checks, real Chromium integration checks and a GitHub Actions workflow.

### Fixed

- Blocking search I/O now runs in a thread pool; upstream sockets and crawl batches have explicit timeouts.
- Upstream HTTP/JSON errors produce clear 502/504 responses and connections are always closed.
- Blank queries, out-of-range result limits and unsafe engine-cookie values are rejected.
- Crawl results are associated by URL rather than completion order; failed pages are retried once.
- Empty filtered Markdown falls back to raw Markdown; empty pages are not counted as successful.
- Browser installation no longer runs on every application startup.

### Compatibility

- `POST /search` and its existing `content`, `success_count`, `failed_urls` fields remain available.
- `limit` is now restricted to 1–20. `query` is trimmed and restricted to 1–2,000 characters.
- Python 3.11+ is the supported runtime. Existing direct dependency pins are retained.
- Local runs bind to `127.0.0.1` by default; set `API_HOST` explicitly for another trusted interface.
- Unavailable/invalid upstream responses and total extraction failures now use 502, timeouts use 504.
