#!/usr/bin/env python3
"""Generate a low-token LLM daily digest and push it through ServerChan."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import textwrap
import time
import urllib.parse
import xml.etree.ElementTree as ET

import feedparser
from pypdf import PdfReader
import requests


ARXIV_API = "https://export.arxiv.org/api/query"
SERVERCHAN_API = "https://sctapi.ftqq.com/{sendkey}.send"

KEYWORDS = [
    '"large language models"',
    "LLM",
    "agents",
    "RAG",
    "reasoning",
    "alignment",
    "evaluation",
    '"multimodal LLM"',
    '"efficient inference"',
    '"tool use"',
    '"long context"',
    '"post-training"',
]

NEWS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss.xml",
    "https://deepmind.google/discover/blog/rss.xml",
    "https://ai.meta.com/blog/rss/",
    "https://blogs.nvidia.com/feed/",
]


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def shanghai_today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def parse_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_arxiv(max_candidates: int) -> list[dict]:
    query = " OR ".join(f"all:{kw}" for kw in KEYWORDS)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_candidates,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    response = requests.get(ARXIV_API, params=params, timeout=30)
    response.raise_for_status()

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(response.text)
    papers = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", "", ns) or "").split())
        summary = " ".join((entry.findtext("atom:summary", "", ns) or "").split())
        link = entry.findtext("atom:id", "", ns)
        published = entry.findtext("atom:published", "", ns)
        updated = entry.findtext("atom:updated", "", ns)
        authors = [
            author.findtext("atom:name", "", ns)
            for author in entry.findall("atom:author", ns)
        ]
        arxiv_id = link.rsplit("/", 1)[-1] if link else ""
        papers.append(
            {
                "title": title,
                "authors": ", ".join(a for a in authors if a),
                "arxiv_id": arxiv_id,
                "link": link,
                "published": published,
                "updated": updated,
                "abstract": summary[:1800],
            }
        )
    return papers[:max_candidates]


def fetch_news(limit: int) -> list[dict]:
    items: list[dict] = []
    for feed_url in NEWS_FEEDS:
        parsed = feedparser.parse(feed_url)
        source = parsed.feed.get("title", urllib.parse.urlparse(feed_url).netloc)
        for entry in parsed.entries[:4]:
            title = html.unescape(entry.get("title", "")).strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", entry.get("updated", ""))
            summary = html.unescape(entry.get("summary", "")).strip()
            if title and link:
                items.append(
                    {
                        "source": source,
                        "title": title,
                        "link": link,
                        "published": published,
                        "summary": " ".join(summary.split())[:900],
                    }
                )
    return items[: max(limit * 3, limit)]


def arxiv_pdf_url(abs_url: str) -> str:
    return abs_url.replace("/abs/", "/pdf/")


def enrich_papers_with_pdf_excerpt(papers: list[dict]) -> list[dict]:
    """Attach bounded PDF excerpts for a few top candidates."""
    max_pdfs = env_int("ARXIV_MAX_PDFS", 3)
    max_pages = env_int("PDF_MAX_PAGES", 8)
    max_chars = env_int("PDF_EXCERPT_CHARS", 9000)

    for paper in papers[:max_pdfs]:
        link = paper.get("link", "")
        if not link:
            continue
        try:
            pdf_response = requests.get(arxiv_pdf_url(link), timeout=45)
            pdf_response.raise_for_status()
            pdf_path = f"/tmp/{paper.get('arxiv_id', 'paper').replace('/', '_')}.pdf"
            with open(pdf_path, "wb") as handle:
                handle.write(pdf_response.content)

            reader = PdfReader(pdf_path)
            page_texts = []
            for page in reader.pages[:max_pages]:
                page_texts.append(page.extract_text() or "")
            excerpt = "\n".join(page_texts)
            excerpt = " ".join(excerpt.split())[:max_chars]
            if excerpt:
                paper["pdf_excerpt"] = excerpt
                paper["pdf_excerpt_note"] = (
                    f"Extracted from first {min(max_pages, len(reader.pages))} PDF pages; "
                    "use for lightweight paper-insight reading."
                )
        except Exception as exc:
            paper["pdf_excerpt_error"] = str(exc)[:240]
    return papers


def build_prompt(papers: list[dict], news: list[dict], today: dt.date) -> str:
    paper_limit = env_int("PAPER_LIMIT", 3)
    news_limit = env_int("NEWS_LIMIT", 3)
    return textwrap.dedent(
        f"""
        你是一个低 token 预算但重视理解质量的 LLM 研究日报编辑。请基于下面的候选材料，输出中文日报。

        日期：{today.isoformat()}

        约束：
        - 最终论文最多 {paper_limit} 篇，资讯最多 {news_limit} 条。
        - 全文 1800-2600 中文字以内。
        - 先从入选论文中选 1 篇“今日重点精读”，用 600-900 中文字展开讲清楚原理。
        - 其他论文每篇 100-160 中文字，每条资讯 80-120 中文字。
        - 使用 paper-insight 的轻量精读标准，并区分：论文声称、证据支持的结论、你的推断。
        - 重点精读必须包含：为什么选它、问题背景、核心机制/原理、方法流程、实验或证据、局限、对研究/工程的启发。
        - 如果某篇论文只有 abstract，没有 pdf_excerpt，必须标注“abstract-only”，不要假装读过全文。
        - 如果有 pdf_excerpt，请优先基于 abstract + pdf_excerpt 做分层阅读：title/abstract/introduction/method/experiments/limitations；只做轻量精读，不展开长综述。
        - 可以自然保留必要英文术语，不要为了中文化而硬翻；例如 LLM, agent, benchmark, inference, alignment, RAG, post-training, decode, KV cache, tool use, evaluation 等术语可以直接保留或中英混排。
        - 原始英文论文标题必须保留，可在后面加简短中文解释；不要把英文标题完全翻译成中文标题。
        - 不做 citation chaining，不扩展相关工作，不编造 DOI/venue/数据集/结果/发布日期。
        - 如果候选质量一般，少写，不要凑数。
        - 输出结构固定为：今日总览、今日重点精读、其他值得关注论文、重点资讯、优先阅读建议、来源链接。

        候选论文 JSON：
        {json.dumps(papers, ensure_ascii=False, separators=(",", ":"))}

        候选资讯 JSON：
        {json.dumps(news, ensure_ascii=False, separators=(",", ":"))}
        """
    ).strip()


def call_deepseek(prompt: str) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY")

    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    max_tokens = env_int("MAX_COMPLETION_TOKENS", 1800)
    response = None
    for attempt in range(4):
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个严谨、低 token 预算的 LLM 研究日报编辑。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
            timeout=120,
        )
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        if attempt == 3:
            break
        retry_after = response.headers.get("retry-after")
        delay = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt * 10
        print(
            f"DeepSeek API returned {response.status_code}; retrying in {delay}s",
            file=sys.stderr,
        )
        time.sleep(delay)

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        error_body = response.text[:1200] if response is not None else ""
        raise RuntimeError(f"DeepSeek API request failed: {exc}; body={error_body}") from exc
    payload = response.json()
    choices = payload.get("choices", [])
    text = ""
    if choices:
        text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise RuntimeError(f"DeepSeek response had no text: {payload}")
    return text


def push_serverchan(title: str, body: str) -> None:
    sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
    if not sendkey.startswith("SCT"):
        raise RuntimeError("Missing or invalid SERVERCHAN_SENDKEY")
    response = requests.post(
        SERVERCHAN_API.format(sendkey=sendkey),
        data={"title": title, "desp": body},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"ServerChan push failed: {payload}")


def main() -> int:
    today = shanghai_today()
    arxiv_max = env_int("ARXIV_MAX_CANDIDATES", 12)
    news_limit = env_int("NEWS_LIMIT", 3)

    papers = fetch_arxiv(arxiv_max)
    papers = enrich_papers_with_pdf_excerpt(papers)
    news = fetch_news(news_limit)
    prompt = build_prompt(papers, news, today)
    digest = call_deepseek(prompt)

    print(digest)
    push_serverchan(f"LLM 日报 {today.isoformat()}", digest)
    print("\nServerChan push: SUCCESS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
