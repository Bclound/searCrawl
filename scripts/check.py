"""无需外部服务的 API 与爬取契约自检：python scripts/check.py。"""
import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import HTTPException
import main
import crawler as crawler_module
from crawler import WebCrawler


def page(url, text="正文内容", success=True, raw=None):
    return SimpleNamespace(url=url, success=success, metadata={"title": "网页标题"},
                           markdown=SimpleNamespace(fit_markdown=text, raw_markdown=raw))


def check_search_transport():
    for body, status, expected in [
        (b'{"results": []}', 200, None),
        (b'not-json', 200, 502),
        (b'{"results": {}}', 200, 502),
        (b'[]', 200, 502),
        (b'forbidden', 403, 502),
        (b'x' * (2 * 1024 * 1024 + 1), 200, 502),
    ]:
        connection = MagicMock()
        connection.getresponse.return_value.status = status
        connection.getresponse.return_value.read.return_value = body
        with patch.object(crawler_module.http.client, "HTTPConnection", return_value=connection) as constructor:
            try:
                assert WebCrawler.make_searxng_request("中文 & space") == {"results": []}
                assert expected is None
                encoded = connection.request.call_args.args[2]
                assert parse_qs(encoded)["q"] == ["中文 & space"]
                assert constructor.call_args.kwargs["timeout"] > 0
            except HTTPException as error:
                assert error.status_code == expected, (error.status_code, expected)
            assert connection.close.call_count == 1
    for failure, expected in [(TimeoutError(), 504), (OSError(), 502)]:
        connection = MagicMock()
        connection.request.side_effect = failure
        with patch.object(crawler_module.http.client, "HTTPConnection", return_value=connection):
            try:
                WebCrawler.make_searxng_request("query")
                raise AssertionError("请求应失败")
            except HTTPException as error:
                assert error.status_code == expected
            assert connection.close.call_count == 1


async def check_crawl():
    first, second, third = [f"https://example.org/{i}" for i in range(3)]
    service = WebCrawler()
    service.crawler = SimpleNamespace(arun_many=AsyncMock(side_effect=[
        [page(second, "# 第二条"), None, page(first, "  ", raw="# 第一条")],
        [page(third, success=False)],
    ]))
    result = await service.crawl_urls([first, second, third], "query")
    assert result["success_count"] == 2
    assert result["failed_urls"] == [third]
    assert [item["url"] for item in result["results"]] == [first, second]
    assert result["results"][0]["markdown"] == "# 第一条"
    assert "第一条" in result["content"] and "第二条" in result["content"]
    assert service.crawler.arun_many.call_args_list[1].kwargs["urls"] == [third]

    service.crawler.arun_many = AsyncMock(side_effect=[[page(second)], [page(first)]])
    result = await service.crawl_urls([first, second], "query")
    assert [item["url"] for item in result["results"]] == [first, second]
    assert result["failed_urls"] == []

    service.crawler.arun_many = AsyncMock(return_value=[page(first, "", raw="")])
    try:
        await service.crawl_urls([first], "query")
        raise AssertionError("空正文不得计为成功")
    except HTTPException as error:
        assert error.status_code == 502

    async def hang(**kwargs):
        await asyncio.sleep(1)
    service.crawler.arun_many = AsyncMock(side_effect=hang)
    with patch.object(crawler_module, "CRAWL_TIMEOUT_SECONDS", 0.01):
        try:
            await service.crawl_urls([first], "query")
            raise AssertionError("整批超时应返回 504")
        except HTTPException as error:
            assert error.status_code == 504

    service.crawler.arun_many = AsyncMock(side_effect=[[page(first)], TimeoutError()])
    result = await service.crawl_urls([first, second], "query")
    assert result["success_count"] == 1 and result["failed_urls"] == [second]


async def check_api():
    service = SimpleNamespace(crawler=object(), crawl_urls=AsyncMock(return_value={
        "content": "正文", "success_count": 1, "failed_urls": [],
        "results": [{"url": "https://example.org/", "title": "", "markdown": "正文", "content": "正文"}],
    }))
    transport = httpx.ASGITransport(app=main.app)
    with patch.object(main, "crawler", service), patch.object(WebCrawler, "make_searxng_request") as search:
        search.return_value = {"results": [{"url": "https://example.org/", "title": "来源标题"}]}
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            for payload in [{"query": " "}, {"query": "x", "limit": 0}, {"query": "x", "limit": 21},
                            {"query": "x", "enabled_engines": "baidu;unsafe=1"},
                            {"query": "x", "disabled_engines": "x\r\nHeader: bad"}, {"query": "x" * 2001}]:
                assert (await client.post("/search", json=payload)).status_code == 422
            search.assert_not_called()
            response = await client.post("/search", json={"query": " 中文 "})
            assert response.status_code == 200, response.text
            assert response.json()["results"][0]["title"] == "来源标题"
            assert search.call_args.kwargs["query"] == "中文"
            assert response.json()["content"] == "正文"

            for data, status in [({"results": []}, 404), ({"results": [{"url": "file:///etc/passwd"}]}, 404)]:
                search.return_value = data
                assert (await client.post("/search", json={"query": "x"})).status_code == status
            search.side_effect = HTTPException(status_code=504, detail="SearXNG 请求超时")
            assert (await client.post("/search", json={"query": "x"})).status_code == 504

            entered, release = threading.Event(), threading.Event()
            def slow_search(**kwargs):
                entered.set()
                assert release.wait(2), "健康检查被搜索请求阻塞"
                return {"results": []}
            search.side_effect = slow_search
            request = asyncio.create_task(client.post("/search", json={"query": "slow"}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                response = await asyncio.wait_for(client.get("/health"), 0.5)
                assert response.status_code == 200
            finally:
                release.set()
                await request

    service = SimpleNamespace(initialize=AsyncMock(), close=AsyncMock(), crawler=object())
    with patch.object(main, "WebCrawler", return_value=service):
        async with main.lifespan(main.app):
            assert main.crawler is service
        assert service.close.await_count == 1 and main.crawler is None
        service.initialize.side_effect = RuntimeError("启动失败")
        try:
            async with main.lifespan(main.app):
                raise AssertionError("初始化失败不得进入服务阶段")
        except RuntimeError:
            pass
        assert service.close.await_count == 2 and main.crawler is None
    async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
        assert (await client.get("/health")).status_code == 503


async def run():
    check_search_transport()
    await check_crawl()
    await check_api()
    print("契约自检通过：参数校验、旧字段兼容、来源顺序、失败重试、超时、并发健康检查与资源释放")


if __name__ == "__main__":
    asyncio.run(run())
