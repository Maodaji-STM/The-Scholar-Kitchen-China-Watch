"""
scraper.py — 发现 The Scholarly Kitchen 新文章，匹配 China/Chinese，提取摘录。

发现顺序：
  1. RSS feed（最新文章，最快、最省流量）
  2. WordPress REST API 分页（/wp-json/wp/v2/posts），用于首次历史回溯，
     或 RSS 覆盖不到的更早文章
  3. Archives 分页（留作接口不可用时的兜底，当前未实现具体解析，
     REST API 通常已足够，需要时再补）

去重：以文章永久链接（link）为唯一标识，处理状态存在 state/state.json。

匹配规则：不区分大小写的独立词 China / Chinese，支持 China's / China’s，
不匹配 Chinatown 等包含关系。只在标题和正文（REST API 的 content.rendered，
不含导航/评论/作者简介）中查找。
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

SITE = "https://scholarlykitchen.sspnet.org"
RSS_URL = f"{SITE}/feed/"
REST_POSTS_URL = f"{SITE}/wp-json/wp/v2/posts"
USER_AGENT = "TSK-China-Watch/1.0 (+https://github.com/; contact via repo issues)"

STATE_PATH = Path("state/state.json")

# 独立词匹配：China / Chinese，允许 's 或 ’s 所有格，不匹配 Chinatown 等前缀延伸词
MATCH_PATTERN = re.compile(
    r"\bChina(?:['’]s)?\b|\bChinese\b",
    re.IGNORECASE,
)

REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.0  # 限速：请求间隔
MAX_RETRIES = 3


def _request_with_retry(url, params=None):
    """带指数退避重试的 GET 请求。"""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY_SECONDS)
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(REQUEST_DELAY_SECONDS * (2**attempt))
    raise RuntimeError(f"请求失败（已重试 {MAX_RETRIES} 次）：{url}") from last_exc


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"processed": {}, "last_success_run": None}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_recent_from_rss():
    """RSS 通常只覆盖最近一批文章，用作日常增量发现的第一来源。"""
    feed = feedparser.parse(RSS_URL)
    articles = []
    for entry in feed.entries:
        articles.append(
            {
                "url": entry.link,
                "title": entry.title,
                "author": entry.get("author", "TSK staff"),
                "published": entry.get("published", ""),
                "body_html": entry.get("summary", ""),  # RSS 摘要，非全文
            }
        )
    return articles


def fetch_from_rest_api(after_iso=None, max_pages=50):
    """
    通过 WordPress REST API 分页抓取，返回完整正文（content.rendered）。
    after_iso: 只取该 ISO 时间之后发布的文章（用于增量运行的重叠窗口）；
               为 None 时从头分页抓取（用于首次历史回溯）。
    """
    articles = []
    page = 1
    while page <= max_pages:
        params = {"page": page, "per_page": 100, "orderby": "date", "order": "desc"}
        if after_iso:
            params["after"] = after_iso
        resp = _request_with_retry(REST_POSTS_URL, params=params)
        posts = resp.json()
        if not posts:
            break
        for post in posts:
            articles.append(
                {
                    "url": post["link"],
                    "title": BeautifulSoup(
                        post["title"]["rendered"], "html.parser"
                    ).get_text(),
                    "author": post.get("_embedded", {})
                    .get("author", [{}])[0]
                    .get("name", "TSK staff"),
                    "published": post["date"],
                    "body_html": post["content"]["rendered"],
                }
            )
        if len(posts) < 100:
            break
        page += 1
    return articles


def extract_excerpt(text, match, window=140):
    """在匹配词前后各取约 window 字符，返回带 <mark> 高亮的 HTML 片段。"""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    before = text[start : match.start()]
    matched = text[match.start() : match.end()]
    after = text[match.end() : end]
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{before}<mark>{matched}</mark>{after}{suffix}"


def find_match(title, body_html):
    """
    在标题和正文纯文本中查找 China/Chinese。
    body_html 应为 REST API 的 content.rendered（不含导航/评论/作者简介），
    这里转成纯文本再匹配和截取上下文。
    """
    body_text = BeautifulSoup(body_html, "html.parser").get_text(separator=" ")
    body_text = re.sub(r"\s+", " ", body_text).strip()

    title_match = MATCH_PATTERN.search(title)
    if title_match:
        return title_match.group(0), extract_excerpt(title, title_match)

    body_match = MATCH_PATTERN.search(body_text)
    if body_match:
        return body_match.group(0), extract_excerpt(body_text, body_match)

    return None, None


def discover_new_articles(state, backfill=False):
    """
    返回本次运行中新发现、且匹配 China/Chinese 的文章列表（未做摘要）。
    backfill=True 时执行全站历史回溯；否则只做增量抓取（RSS + 近期 REST 补齐）。
    """
    processed = state["processed"]
    candidates = []

    if backfill:
        candidates.extend(fetch_from_rest_api(after_iso=None))
    else:
        candidates.extend(fetch_recent_from_rss())
        # 用重叠窗口（近 7 天）通过 REST API 再补一遍，防止 RSS 遗漏或调度延迟漏抓
        seven_days_ago = (
            datetime.now(timezone.utc).replace(microsecond=0) - _days(7)
        ).isoformat()
        candidates.extend(fetch_from_rest_api(after_iso=seven_days_ago))

    # 按 URL 去重（同一文章可能同时出现在 RSS 和 REST 结果里）
    seen_urls = set()
    deduped = []
    for art in candidates:
        if art["url"] in seen_urls:
            continue
        seen_urls.add(art["url"])
        deduped.append(art)

    new_hits = []
    for art in deduped:
        if art["url"] in processed:
            continue  # 已处理过（无论是否命中），不重复通知

        term, excerpt_html = find_match(art["title"], art["body_html"])
        matched = term is not None

        state_entry = {
            "published": art["published"],
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "matched": matched,
        }
        if matched:
            # 把完整展示所需字段存进 state，这样重建 dashboard 时不用重新抓取全文
            state_entry.update(
                {
                    "title": art["title"],
                    "author": art["author"],
                    "matched_term": term,
                    "excerpt_html": excerpt_html,
                    "summary": "",  # 由 summarize.py 在 main.py 里补上
                }
            )
        processed[art["url"]] = state_entry

        if matched:
            new_hits.append(
                {
                    "url": art["url"],
                    "title": art["title"],
                    "author": art["author"],
                    "published": art["published"],
                    "matched_term": term,
                    "excerpt_html": excerpt_html,
                }
            )

    return new_hits


def _days(n):
    from datetime import timedelta

    return timedelta(days=n)
