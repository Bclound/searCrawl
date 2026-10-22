# SearCrawl

[![Regression checks](https://github.com/Bclound/searCrawl/actions/workflows/check.yml/badge.svg)](https://github.com/Bclound/searCrawl/actions/workflows/check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

中文 | [English](README_EN.md)

基于 SearXNG、Crawl4AI 和 FastAPI 的自托管搜索与网页内容提取 API。搜索后提取网页正文，返回每条结果的 URL、标题、Markdown 和纯文本，便于 AI 应用保留引用来源。服务本身不需要 OpenAI 或其他模型的 API Key。

## v1.2.0

- 新增 `results` 来源列表，保留 `content`、`success_count`、`failed_urls` 三个原有字段。
- 同步搜索请求在线程池执行，避免阻塞其他 API 请求；增加搜索超时、整批爬取超时和明确的错误响应。
- 爬取结果按来源 URL 匹配并保持搜索顺序；失败页面最多重试一次，空正文不计为成功。
- 提供 Docker Compose、健康检查、契约自检和真实 Chromium 集成自检。

完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## Docker 一键启动

需要 Docker Engine / Docker Desktop 和 Compose v2：

```sh
git clone https://github.com/Bclound/searCrawl.git
cd searCrawl
docker compose up --build -d --wait
```

打开 [API 文档](http://127.0.0.1:3000/docs)，或检查：

```sh
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Python FastAPI","limit":3}'
```

Compose 会启动 SearXNG 和 SearCrawl。SearXNG 使用固定镜像摘要，首次启动自动生成随机密钥，JSON 搜索格式已启用。浏览器在构建阶段安装，服务启动时不会下载浏览器。首次构建需要联网下载依赖和 Chromium。

API 只映射到本机 `127.0.0.1:3000`；SearXNG 不向宿主机开放端口。更换本机端口：

```sh
SEARCRAWL_PORT=33080 docker compose up --build -d --wait
```

查看日志和停止服务：

```sh
docker compose logs --tail=100
docker compose down
```

SearXNG 配置保存在 `searxng-config` 卷中，重启不会覆盖。`deploy/searxng.yml` 是首次初始化模板。

## 本地运行

支持 Python 3.11+，需要一个可用的 SearXNG 实例：

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
python main.py
```

Linux 如缺少浏览器系统依赖，安装时使用 `python -m playwright install --with-deps chromium`。编辑 `.env` 设置 SearXNG 地址。SearXNG 必须允许 JSON 响应：

```yaml
search:
  formats:
    - html
    - json
```

## API

### `POST /search`

```json
{
  "query": "搜索关键词",
  "limit": 3
}
```

| 参数 | 说明 |
| --- | --- |
| `query` | 必填；去除两端空白后为 1–2,000 个字符 |
| `limit` | 1–20；默认 10 |
| `disabled_engines` | 可选；SearXNG 禁用引擎 Cookie 的逗号分隔值 |
| `enabled_engines` | 可选；SearXNG 启用引擎 Cookie 的逗号分隔值，默认 `baidu__general` |

引擎参数沿用原有 Cookie 格式，禁止换行和分号。默认搜索仍使用中文、最近一周和严格安全搜索；具体支持取决于所选引擎。

示例响应（示例 URL 和正文用于说明结构）：

```json
{
  "content": "页面一正文\n\n==========\n\n页面二正文",
  "success_count": 2,
  "failed_urls": [],
  "results": [
    {
      "url": "https://example.com/one",
      "title": "页面一标题",
      "markdown": "# 页面一标题\n\n页面一正文",
      "content": "页面一标题\n页面一正文"
    },
    {
      "url": "https://example.com/two",
      "title": "页面二标题",
      "markdown": "页面二正文",
      "content": "页面二正文"
    }
  ]
}
```

`results` 仅包含提取成功的页面，按原搜索顺序排列。`url` 为搜索结果中的来源地址；标题优先采用搜索结果标题，缺失时采用网页标题。`markdown` 优先使用过滤后的正文，为空时回退到原始 Markdown。`content` 保持原有合并文本接口。

每批最多并发抓取 5 个页面，页面导航超时为 30 秒，整批（含一次重试）默认最多等待 90 秒。若重试阶段超时，已完成的页面仍会返回，其余列入 `failed_urls`。搜索上游响应上限为 2 MiB。

| HTTP 状态 | 含义 |
| --- | --- |
| 200 | 至少一个页面提取成功 |
| 404 | 没有搜索结果或有效 HTTP(S) 来源 |
| 422 | 请求参数不合法 |
| 502 | 搜索上游异常、无效响应，或所有页面均未提取到正文 |
| 503 | 爬虫尚未就绪 |
| 504 | 搜索超时，或整批爬取超时且没有可返回的成功页面 |

### `GET /health`

浏览器初始化完成后返回 `{"status":"ok","version":"1.2.0"}`。该检查不访问公网搜索引擎。

## 配置

| 环境变量 | 默认值 |
| --- | --- |
| `SEARXNG_HOST` / `SEARXNG_PORT` / `SEARXNG_BASE_PATH` | `localhost` / `8080` / `/search` |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `3000` |
| `DEFAULT_SEARCH_LIMIT` | `10`，范围 1–20 |
| `SEARCH_TIMEOUT_SECONDS` | `15`，正数；上游连接及读写的 socket 超时 |
| `CRAWL_TIMEOUT_SECONDS` | `90`，正数；整批网页提取的等待上限 |
| `CONTENT_FILTER_THRESHOLD` / `WORD_COUNT_THRESHOLD` | `0.6` / `10` |
| `DISABLED_ENGINES` / `ENABLED_ENGINES` | 见 `.env.example` |

Compose 固定容器内服务地址，并只将本机端口、搜索超时和爬取超时暴露为覆盖项；其他部署配置可直接修改 `compose.yaml`。

本服务面向受信任的本地或私有网络调用，不包含用户认证。它会使用服务器网络抓取搜索结果；HTTP(S) 校验不是完整的 SSRF 隔离。若要对外服务，应配置认证、限流和出站网络隔离，不要将容器端口直接暴露到公网。网页内容属于不可信外部数据，接入 AI 应用时应作为引用资料处理。

## 开发验证

```sh
pip install -r requirements-dev.txt
python scripts/check.py
python -m playwright install chromium
python scripts/smoke.py
```

`check.py` 验证参数、上游状态/JSON/超时、URL 来源匹配、重试、空正文、旧字段、并发健康检查和资源释放。`smoke.py` 启动临时本地搜索响应与 HTML 页面，经真实 Chromium 验证完整提取链路，结束后清理临时服务与缓存。CI 在 Python 3.11 上执行这两项检查。

公网搜索结果受实例配置、搜索引擎可用性和目标网站限制影响；本地自检不依赖实时搜索排名。

## 许可证与致谢

[MIT](LICENSE)。基于 [SearXNG](https://github.com/searxng/searxng)、[Crawl4AI](https://github.com/unclecode/crawl4ai) 和 [FastAPI](https://github.com/fastapi/fastapi)。
