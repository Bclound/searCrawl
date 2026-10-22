# SearCrawl

[![Regression checks](https://github.com/Bclound/searCrawl/actions/workflows/check.yml/badge.svg)](https://github.com/Bclound/searCrawl/actions/workflows/check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[中文](README.md) | English

A self-hosted search and web-content extraction API built on SearXNG, Crawl4AI and FastAPI. Each successful result includes its source URL, title, Markdown and plain text, so AI applications can retain citations. SearCrawl does not require an OpenAI or other model API key.

## v1.2.0

- Adds a structured `results` list while retaining `content`, `success_count` and `failed_urls`.
- Runs blocking search I/O in a thread pool, with explicit search and batch crawl timeouts.
- Matches crawled pages by URL, preserves search order, retries failures once, and rejects empty extracted content.
- Adds Docker Compose, health checks, contract checks and a real Chromium integration check.

See [CHANGELOG.md](CHANGELOG.md).

## Start with Docker

Requires Docker Engine / Desktop and Compose v2:

```sh
git clone https://github.com/Bclound/searCrawl.git
cd searCrawl
docker compose up --build -d --wait
```

Open [API docs](http://127.0.0.1:3000/docs), or run:

```sh
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Python FastAPI","limit":3}'
```

Compose starts SearXNG and SearCrawl. The SearXNG image is pinned by digest, JSON output is enabled, and a random secret is generated on first startup. Chromium is installed during the build, not at service startup. The initial build downloads dependencies and Chromium.

Only `127.0.0.1:3000` is published; SearXNG has no host port. To use a different local port:

```sh
SEARCRAWL_PORT=33080 docker compose up --build -d --wait
```

```sh
docker compose logs --tail=100
docker compose down
```

SearXNG settings persist in the `searxng-config` volume. `deploy/searxng.yml` is the initial template and does not overwrite existing settings on restart.

## Run locally

Python 3.11+ and a SearXNG instance are required:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
python main.py
```

On Linux, use `python -m playwright install --with-deps chromium` if browser system libraries are missing. Configure your SearXNG address in `.env` and enable JSON in its `settings.yml`:

```yaml
search:
  formats:
    - html
    - json
```

## API

### `POST /search`

```json
{"query":"search keywords","limit":3}
```

| Field | Meaning |
| --- | --- |
| `query` | Required, 1–2,000 characters after trimming whitespace |
| `limit` | 1–20, defaults to 10 |
| `disabled_engines` | Optional comma-separated SearXNG disabled-engine cookie value |
| `enabled_engines` | Optional enabled-engine cookie value, defaults to `baidu__general` |

Engine fields preserve the existing cookie format; line breaks and semicolons are rejected. Existing defaults remain Chinese, the past week and strict safe search, subject to engine support.

Example response (illustrative URLs and text):

```json
{
  "content": "First page text\n\n==========\n\nSecond page text",
  "success_count": 2,
  "failed_urls": [],
  "results": [
    {
      "url": "https://example.com/one",
      "title": "First page",
      "markdown": "# First page\n\nFirst page text",
      "content": "First page\nFirst page text"
    },
    {
      "url": "https://example.com/two",
      "title": "Second page",
      "markdown": "Second page text",
      "content": "Second page text"
    }
  ]
}
```

`results` contains successful extractions in search order. Each URL is the original search result URL. Titles prefer search metadata, falling back to the page title. Markdown prefers filtered content, falling back to raw Markdown if the filtered value is empty. The top-level `content` preserves the legacy combined-text interface.

Each batch crawls up to five pages concurrently. Navigation is limited to 30 seconds; the whole batch, including one retry, defaults to a 90-second wait limit. Successful pages from the first pass remain available if the retry times out; unfinished URLs appear in `failed_urls`. Search upstream responses are limited to 2 MiB.

| HTTP status | Meaning |
| --- | --- |
| 200 | At least one successful extraction |
| 404 | No search results or valid HTTP(S) sources |
| 422 | Invalid request fields |
| 502 | Upstream failure, malformed response, or no extracted content |
| 503 | Crawler not ready |
| 504 | Search timeout, or crawl batch timeout with no successful pages |

### `GET /health`

Returns `{"status":"ok","version":"1.2.0"}` once the browser is initialized. It does not query a public search engine.

## Configuration

| Environment variable | Default |
| --- | --- |
| `SEARXNG_HOST` / `SEARXNG_PORT` / `SEARXNG_BASE_PATH` | `localhost` / `8080` / `/search` |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `3000` |
| `DEFAULT_SEARCH_LIMIT` | `10`, allowed range 1–20 |
| `SEARCH_TIMEOUT_SECONDS` | `15`, positive; upstream socket connect/read/write timeout |
| `CRAWL_TIMEOUT_SECONDS` | `90`, positive; total batch wait limit |
| `CONTENT_FILTER_THRESHOLD` / `WORD_COUNT_THRESHOLD` | `0.6` / `10` |
| `DISABLED_ENGINES` / `ENABLED_ENGINES` | See `.env.example` |

Compose fixes internal service addresses and exposes the host port and two timeouts as overrides. Edit `compose.yaml` for other deployment settings.

The API is intended for trusted local/private-network callers and has no user authentication. It fetches search result pages using the server's network; HTTP(S) URL validation is not full SSRF isolation. Public hosting requires authentication, rate limiting and outbound network isolation. Treat retrieved content as untrusted source material when passing it to an AI application.

## Development checks

```sh
pip install -r requirements-dev.txt
python scripts/check.py
python -m playwright install chromium
python scripts/smoke.py
```

The contract check covers validation, upstream errors/JSON/timeouts, source matching, retries, empty content, legacy fields, concurrent health checks and cleanup. The integration check starts temporary local search responses and HTML pages, runs real Chromium extraction, then removes its temporary services and cache. CI runs both on Python 3.11.

Live searches depend on instance settings, search engines and target websites. Local checks do not depend on public search rankings.

## License and acknowledgments

[MIT](LICENSE). Built with [SearXNG](https://github.com/searxng/searxng), [Crawl4AI](https://github.com/unclecode/crawl4ai) and [FastAPI](https://github.com/fastapi/fastapi).
