# -*- coding: utf-8 -*-
"""
爬虫模块 - 提供网页爬取和内容处理功能

This module provides web crawling and content processing functionality.
It encapsulates the AsyncWebCrawler from crawl4ai library and provides
high-level methods for crawling web pages and processing their content.
"""

from typing import List, Dict, Any
import asyncio
import socket
from urllib.parse import urlencode
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    SemaphoreDispatcher
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
import markdown
from bs4 import BeautifulSoup
import re
import http.client
import json
from fastapi import HTTPException

# 导入配置和日志模块
from config import (
    SEARXNG_HOST,
    SEARXNG_PORT,
    SEARXNG_BASE_PATH,
    DISABLED_ENGINES,
    ENABLED_ENGINES,
    CONTENT_FILTER_THRESHOLD,
    WORD_COUNT_THRESHOLD,
    SEARCH_TIMEOUT_SECONDS,
    CRAWL_TIMEOUT_SECONDS
)
import logger


class WebCrawler:
    """网页爬虫类，封装了网页爬取和内容处理的功能"""

    def __init__(self):
        """初始化爬虫实例"""
        self.crawler = None
        logger.info("初始化WebCrawler实例")

    async def initialize(self) -> None:
        """初始化AsyncWebCrawler实例

        必须在使用爬虫前调用此方法
        """
        # 配置浏览器
        browser_config = BrowserConfig(headless=True, verbose=True)
        # 初始化爬虫
        self.crawler = AsyncWebCrawler(config=browser_config)
        await self.crawler.__aenter__()
        logger.info("AsyncWebCrawler初始化完成")

    async def close(self) -> None:
        """关闭爬虫实例，释放资源"""
        if self.crawler:
            await self.crawler.__aexit__(None, None, None)
            self.crawler = None
            logger.info("AsyncWebCrawler已关闭")

    @staticmethod
    def markdown_to_text_regex(markdown_str: str) -> str:
        """使用正则表达式将Markdown文本转换为纯文本

        Args:
            markdown_str: Markdown格式的文本

        Returns:
            str: 转换后的纯文本
        """
        # 移除标题符号
        text = re.sub(r'#+\s*', '', markdown_str)

        # 移除链接和图片
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # 移除粗体、斜体等强调符号
        text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
        text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)

        # 移除列表符号
        text = re.sub(r'^[\*\-\+]\s*', '', text, flags=re.MULTILINE)

        # 移除代码块
        text = re.sub(r'`{3}.*?`{3}', '', text, flags=re.DOTALL)
        text = re.sub(r'`(.*?)`', r'\1', text)

        # 移除引用块
        text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)

        return text.strip()

    @staticmethod
    def markdown_to_text(markdown_str: str) -> str:
        """使用markdown和BeautifulSoup库将Markdown文本转换为纯文本

        Args:
            markdown_str: Markdown格式的文本

        Returns:
            str: 转换后的纯文本
        """
        html = markdown.markdown(markdown_str, extensions=['fenced_code'])
        # 用 BeautifulSoup 提取纯文本
        soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text(separator="\n")  # 保留段落换行

        # 清理多余空行
        cleaned_text = "\n".join([line.strip()
                             for line in text.split("\n") if line.strip()])

        return cleaned_text

    @staticmethod
    def make_searxng_request(query: str, limit: int = 10,
                           disabled_engines: str = DISABLED_ENGINES,
                           enabled_engines: str = ENABLED_ENGINES) -> dict:
        """以有限超时请求 SearXNG；调用方须在线程池中执行。"""
        conn = http.client.HTTPConnection(
            SEARXNG_HOST, SEARXNG_PORT, timeout=SEARCH_TIMEOUT_SECONDS
        )
        try:
            body = urlencode({
                "q": query, "format": "json", "language": "zh",
                "time_range": "week", "safesearch": "2",
                "pageno": "1", "category_general": "1",
            })
            conn.request("POST", SEARXNG_BASE_PATH, body, {
                "Cookie": f"disabled_engines={disabled_engines};enabled_engines={enabled_engines};method=POST",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "SearCrawl/1.2.0",
            })
            response = conn.getresponse()
            if response.status != 200:
                raise HTTPException(status_code=502, detail=f"SearXNG 返回 HTTP {response.status}")
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise HTTPException(status_code=502, detail="SearXNG 响应超过 2 MiB")
            result = json.loads(data.decode("utf-8"))
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise HTTPException(status_code=502, detail="SearXNG 响应缺少 results 数组")
            return result
        except (socket.timeout, TimeoutError):
            raise HTTPException(status_code=504, detail="SearXNG 请求超时")
        except (OSError, http.client.HTTPException, ValueError) as error:
            logger.warning(f"SearXNG 请求失败: {type(error).__name__}")
            raise HTTPException(status_code=502, detail="SearXNG 不可用或返回了无效 JSON")
        finally:
            conn.close()

    async def crawl_urls(self, urls: List[str], instruction: str) -> Dict[str, Any]:
        """保留来源和搜索顺序，失败页面最多重试一次，并限制整批等待时间。"""
        if not self.crawler:
            raise HTTPException(status_code=503, detail="爬虫尚未就绪")

        run_config = CrawlerRunConfig(
            word_count_threshold=WORD_COUNT_THRESHOLD,
            exclude_external_links=True,
            remove_overlay_elements=True,
            excluded_tags=['img', 'header', 'footer', 'iframe', 'nav'],
            process_iframes=True,
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(threshold=CONTENT_FILTER_THRESHOLD),
                options={"ignore_links": True, "ignore_images": True, "escape_html": False},
            ),
            cache_mode=CacheMode.BYPASS,
            page_timeout=30000,
        )
        urls = list(dict.fromkeys(urls))
        pending = urls
        pages = {}
        deadline = asyncio.get_running_loop().time() + CRAWL_TIMEOUT_SECONDS
        timed_out = False
        for attempt in range(2):
            if not pending:
                break
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                timed_out = True
                break
            try:
                results = await asyncio.wait_for(
                    self.crawler.arun_many(
                        urls=pending, config=run_config,
                        dispatcher=SemaphoreDispatcher(semaphore_count=5),
                    ),
                    timeout=remaining,
                )
            except TimeoutError:
                timed_out = True
                break
            except Exception:
                logger.warning(f"第 {attempt + 1} 次批量爬取失败", exc_info=True)
                continue
            for result in results:
                url = getattr(result, "url", None)
                if url not in pending or not getattr(result, "success", False):
                    continue
                markdown_result = getattr(result, "markdown", None)
                markdown_text = getattr(markdown_result, "fit_markdown", None)
                if not isinstance(markdown_text, str) or not markdown_text.strip():
                    markdown_text = getattr(markdown_result, "raw_markdown", None)
                if not isinstance(markdown_text, str) or not markdown_text.strip():
                    continue
                metadata = getattr(result, "metadata", None) or {}
                title = metadata.get("title", "") if isinstance(metadata, dict) else ""
                pages[url] = {
                    "url": url,
                    "title": title if isinstance(title, str) else "",
                    "markdown": markdown_text,
                    "content": self.markdown_to_text(markdown_text),
                }
            pending = [url for url in urls if url not in pages]

        if not pages:
            if timed_out:
                raise HTTPException(status_code=504, detail="网页爬取超时")
            raise HTTPException(status_code=502, detail="所有 URL 均未能提取有效正文")
        results = [pages[url] for url in urls if url in pages]
        combined = '\n\n==========\n\n'.join(result["markdown"] + '\n\n' for result in results)
        return {
            "content": self.markdown_to_text_regex(self.markdown_to_text(combined)),
            "success_count": len(results),
            "failed_urls": [url for url in urls if url not in pages],
            "results": results,
        }
