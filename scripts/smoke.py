"""真实 Chromium 集成自检，搜索服务使用本地固定响应，不依赖公网搜索排名。"""
import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        assert form["q"] == ["SearCrawl verification"]
        base = f"http://127.0.0.1:{self.server.server_port}"
        body = json.dumps({"results": [
            {"url": base + "/first", "title": "First source"},
            {"url": base + "/second", "title": "Second source"},
        ]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/first":
            self.send_response(302)
            self.send_header("Location", "/first-final")
            self.end_headers()
            return
        title = "First source" if self.path == "/first-final" else "Second source"
        body = f'''<!doctype html><html><head><title>{title}</title></head>
<body><main><article><h1>{title}</h1>
<p>SearCrawl verification confirms that search results retain their source URLs,
titles and readable text. Developers can cite the original page while working
with a local search and extraction service. This paragraph contains enough real
text to exercise the configured content filter and Markdown generation.</p>
<p>The second paragraph checks that a complete page can be extracted by Chromium.
The legacy combined content is still available to existing clients. New clients
can use structured results in the same response without another request.</p>
</article></main></body></html>'''.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


async def run(server):
    import httpx
    import main
    import crawler
    with patch.object(crawler, "SEARXNG_HOST", "127.0.0.1"), patch.object(crawler, "SEARXNG_PORT", server.server_port):
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://local") as client:
                assert (await client.get("/health")).status_code == 200
                response = await client.post("/search", json={"query": "SearCrawl verification", "limit": 2})
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["success_count"] == 2 and data["failed_urls"] == []
                assert [item["title"] for item in data["results"]] == ["First source", "Second source"]
                assert [item["url"].rsplit("/", 1)[1] for item in data["results"]] == ["first", "second"]
                assert all("SearCrawl verification" in item["markdown"] for item in data["results"])
                assert all("SearCrawl verification" in item["content"] for item in data["results"])
                assert "SearCrawl verification" in data["content"]
                print("真实浏览器自检通过：API → 搜索 HTTP → Chromium → 来源、标题、正文与旧字段")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="searcrawl-check-") as cache:
        os.environ["CRAWL4_AI_BASE_DIRECTORY"] = cache
        server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(run(server))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
