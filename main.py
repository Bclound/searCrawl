"""SearCrawl 搜索与网页内容提取 API。"""

from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from config import API_HOST, API_PORT, DEFAULT_SEARCH_LIMIT, DISABLED_ENGINES, ENABLED_ENGINES
from crawler import WebCrawler
import logger


crawler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global crawler
    logger.setup_logger("INFO")
    crawler = WebCrawler()
    try:
        await crawler.initialize()
        logger.info("SearCrawl 服务已就绪")
        yield
    finally:
        await crawler.close()
        crawler = None


app = FastAPI(
    title="SearCrawl API",
    description="基于 SearXNG 和 Crawl4AI 的搜索与网页内容提取服务",
    version="1.2.0",
    lifespan=lifespan,
)


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT, ge=1, le=20)
    disabled_engines: str = Field(default=DISABLED_ENGINES, max_length=4000, pattern=r"^[^\r\n;]*$")
    enabled_engines: str = Field(default=ENABLED_ENGINES, max_length=4000, pattern=r"^[^\r\n;]*$")


@app.get("/health")
async def health():
    if crawler is None or crawler.crawler is None:
        raise HTTPException(status_code=503, detail="爬虫尚未就绪")
    return {"status": "ok", "version": app.version}


@app.post("/search")
async def search(request: SearchRequest):
    if crawler is None:
        raise HTTPException(status_code=503, detail="爬虫尚未就绪")
    try:
        # 同步网络请求在线程池执行，避免阻塞其他请求。
        response = await run_in_threadpool(
            WebCrawler.make_searxng_request,
            query=request.query,
            limit=request.limit,
            disabled_engines=request.disabled_engines,
            enabled_engines=request.enabled_engines,
        )
        results = response.get("results", [])
        if not results:
            raise HTTPException(status_code=404, detail="未找到搜索结果")

        titles = {}
        for result in results[:request.limit]:
            if not isinstance(result, dict):
                continue
            url = result.get("url")
            if not isinstance(url, str):
                continue
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
                    continue
            except ValueError:
                continue
            titles.setdefault(url, result.get("title") if isinstance(result.get("title"), str) else "")
        if not titles:
            raise HTTPException(status_code=404, detail="未找到有效的 HTTP(S) URL")

        response = await crawler.crawl_urls(list(titles), request.query)
        for result in response["results"]:
            result["title"] = titles[result["url"]] or result["title"]
        return response
    except HTTPException:
        raise
    except Exception:
        logger.error("搜索处理失败", exc_info=True)
        raise HTTPException(status_code=500, detail="搜索处理失败，请查看服务日志")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
