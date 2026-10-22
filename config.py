# -*- coding: utf-8 -*-
"""
配置模块 - 负责从环境变量加载配置

This module loads configuration from environment variables and provides
default values when environment variables are not set.
"""

import os
from dotenv import load_dotenv
import logging
import math

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载.env文件中的环境变量
load_dotenv()
logger.info("加载环境变量配置")

# SearXNG 配置
SEARXNG_HOST = os.getenv("SEARXNG_HOST", "localhost")
SEARXNG_PORT = int(os.getenv("SEARXNG_PORT", "8080"))
SEARXNG_BASE_PATH = os.getenv("SEARXNG_BASE_PATH", "/search")
SEARXNG_API_BASE = f"http://{SEARXNG_HOST}:{SEARXNG_PORT}{SEARXNG_BASE_PATH}"

# API 服务配置
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "3000"))

# 爬虫配置
DEFAULT_SEARCH_LIMIT = int(os.getenv("DEFAULT_SEARCH_LIMIT", "10"))
SEARCH_TIMEOUT_SECONDS = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15"))
CRAWL_TIMEOUT_SECONDS = float(os.getenv("CRAWL_TIMEOUT_SECONDS", "90"))
if not 1 <= DEFAULT_SEARCH_LIMIT <= 20:
    raise ValueError("DEFAULT_SEARCH_LIMIT 必须在 1 到 20 之间")
if any(not math.isfinite(value) or value <= 0 for value in (SEARCH_TIMEOUT_SECONDS, CRAWL_TIMEOUT_SECONDS)):
    raise ValueError("搜索与爬取超时必须为正数")
CONTENT_FILTER_THRESHOLD = float(os.getenv("CONTENT_FILTER_THRESHOLD", "0.6"))
WORD_COUNT_THRESHOLD = int(os.getenv("WORD_COUNT_THRESHOLD", "10"))

# 搜索引擎配置
DISABLED_ENGINES = os.getenv(
    "DISABLED_ENGINES",
    "wikipedia__general,currency__general,wikidata__general,duckduckgo__general,google__general,lingva__general,qwant__general,startpage__general,dictzone__general,mymemory translated__general,brave__general"
)
ENABLED_ENGINES = os.getenv("ENABLED_ENGINES", "baidu__general")

# 导出配置信息函数
def get_config_info():
    """返回当前配置信息的字典

    Returns:
        dict: 包含所有配置参数的字典
    """
    return {
        "searxng": {
            "host": SEARXNG_HOST,
            "port": SEARXNG_PORT,
            "base_path": SEARXNG_BASE_PATH,
            "api_base": SEARXNG_API_BASE
        },
        "api": {
            "host": API_HOST,
            "port": API_PORT
        },
        "crawler": {
            "default_search_limit": DEFAULT_SEARCH_LIMIT,
            "content_filter_threshold": CONTENT_FILTER_THRESHOLD,
            "word_count_threshold": WORD_COUNT_THRESHOLD
        },
        "search_engines": {
            "disabled": DISABLED_ENGINES,
            "enabled": ENABLED_ENGINES
        }
    }
