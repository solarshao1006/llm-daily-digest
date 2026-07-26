#!/usr/bin/env python3
"""Generate topic-specific daily digests and push them through ServerChan."""

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
PUBMED_ESEARCH_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
SERVERCHAN_API = "https://sctapi.ftqq.com/{sendkey}.send"


TOPICS = {
    "ai_llm": {
        "title_prefix": "LLM 日报",
        "system_prompt": "你是一个严谨、低 token 预算的 LLM 研究日报编辑。",
        "source_mode": "ai_llm",
        "arxiv_keywords": [
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
        ],
        "feeds": [
            "https://openai.com/news/rss.xml",
            "https://www.anthropic.com/news/rss.xml",
            "https://deepmind.google/discover/blog/rss.xml",
            "https://ai.meta.com/blog/rss/",
            "https://blogs.nvidia.com/feed/",
        ],
        "prompt": """
        你是一个低 token 预算但重视理解质量的 LLM 研究日报编辑。请基于候选材料输出中文日报。

        输出结构固定为：今日总览、今日重点精读、其他值得关注论文、重点资讯、优先阅读建议、来源链接。
        要求：
        - 最终论文最多 {paper_limit} 篇，资讯最多 {news_limit} 条。
        - 全文 1800-2600 中文字以内。
        - 先从入选论文中选 1 篇“今日重点精读”，用 600-900 中文字讲清楚原理。
        - 其他论文每篇 100-160 中文字，每条资讯 80-120 中文字。
        - 使用 paper-insight 的轻量精读标准，并区分：论文声称、证据支持的结论、你的推断。
        - 重点精读包含：为什么选它、问题背景、核心机制/原理、方法流程、实验或证据、局限、对研究/工程的启发。
        - 如果某篇论文只有 abstract，没有 pdf_excerpt，必须标注 abstract-only。
        - 保留原始英文论文标题和必要英文术语，如 LLM, agent, benchmark, inference, alignment, RAG, decode, KV cache。
        - 不做 citation chaining，不扩展相关工作，不编造 DOI/venue/数据集/结果/发布日期。
        """,
    },
    "china_cyber_strategy": {
        "title_prefix": "中国网络安全策略日报",
        "system_prompt": "你是一个关注中国网络安全、数据安全、AI 安全治理和标准政策的策略分析员。",
        "source_mode": "feeds_only",
        "feeds": [
            "https://www.cac.gov.cn/rss.xml",
            "https://www.tc260.org.cn/rss.xml",
            "https://www.caict.ac.cn/kxyj/qwfb/bps/index.htm",
            "https://www.freebuf.com/feed",
            "https://www.secrss.com/rss.xml",
        ],
        "manual_sources": [
            {
                "source": "中央网信办/中国网信网",
                "title": "网信发布：网络安全、数据安全、个人信息保护、算法与生成式 AI 治理政策",
                "link": "https://www.cac.gov.cn/wxzw/wxfb/A093702index_1.htm",
                "summary": "优先用于确认中国网络安全和数据治理政策原文。",
            },
            {
                "source": "全国网络安全标准化技术委员会 TC260",
                "title": "网络安全国家标准、实践指南、AI 安全和个人信息保护标准动态",
                "link": "https://www.tc260.org.cn/",
                "summary": "优先用于确认标准征求意见稿、正式标准、实践指南和安全要求。",
            },
            {
                "source": "国家标准全文公开系统",
                "title": "GB/T 网络安全、数据安全、电子政务安全相关国家标准",
                "link": "https://openstd.samr.gov.cn/",
                "summary": "用于核对国家标准编号、状态和公开文本。",
            },
            {
                "source": "公安标准化信息服务平台",
                "title": "等保、关键信息基础设施、安全监测预警、主动防御相关标准",
                "link": "https://ywtb.mps.gov.cn/gabzh/portal/xxcx/std",
                "summary": "用于跟踪公安行业标准和等保/关基相关技术要求。",
            },
            {
                "source": "中国信通院 CAICT",
                "title": "网络安全、数据安全、AI 安全、数字经济治理白皮书与研究报告",
                "link": "https://www.caict.ac.cn/kxyj/qwfb/bps/",
                "summary": "用于产业安全策略、治理框架和技术路线研判。",
            },
        ],
        "prompt": """
        你是中国网络安全、数据安全、信息智能化安全策略日报编辑。请基于候选材料输出中文日报。

        输出结构固定为：今日总览、重点文章/政策精读、监管与标准变化、对组织安全策略的影响、落地动作建议、来源链接。
        要求：
        - 全文 1800-2600 中文字以内。
        - 从候选中选 1 条最值得精读的中国网络安全政策/标准/报告/文章，用 700-1000 中文字展开。
        - 精读必须包含：发布主体、政策/标准/报告背景、适用对象、核心要求或观点、与等保/关基/数据安全/个人信息保护/AI 安全治理的关系、组织侧落地动作。
        - 重点关注中国监管、标准、产业安全策略；国外来源只作对照，不作为主线。
        - 不要退化成漏洞新闻列表；除非漏洞事件体现出策略变化，否则不作为重点。
        - 对“信息智能化安全”优先分析 AI 安全治理、算法/生成式 AI 管理、数据要素流通安全、模型供应链、内容安全、自动化安全运营。
        - 明确区分：原文事实、政策含义、你的策略判断。
        - 不编造标准编号、发布日期、监管要求；无法确认时标注“待核验”。
        """,
    },
    "repro_ai_pgt": {
        "title_prefix": "辅助生殖 AI/PGT 日报",
        "system_prompt": "你是一个谨慎的辅助生殖 AI 与 PGT 医学文献编辑，不提供诊疗建议。",
        "source_mode": "pubmed",
        "pubmed_query": (
            '("artificial intelligence"[Title/Abstract] OR AI[Title/Abstract] '
            'OR "machine learning"[Title/Abstract] OR "deep learning"[Title/Abstract]) '
            'AND ("assisted reproduction"[Title/Abstract] OR IVF[Title/Abstract] '
            'OR embryo[Title/Abstract] OR "embryo selection"[Title/Abstract] '
            'OR "preimplantation genetic testing"[Title/Abstract] OR PGT[Title/Abstract] '
            'OR PGT-A[Title/Abstract] OR PGT-M[Title/Abstract] OR PGT-SR[Title/Abstract])'
        ),
        "pubmed_journals": [
            "The New England Journal of Medicine",
            "Lancet",
            "BMJ",
            "JAMA",
            "Cell",
            "Nature",
            "Science",
        ],
        "feeds": [
            "https://academic.oup.com/rss/site_5306/3372.xml",
            "https://www.rbmojournal.com/current.rss",
            "https://www.fertstert.org/current.rss",
            "https://www.eshre.eu/Press-Room/RSS",
            "https://www.bmj.com/rss/recent.xml",
            "https://jamanetwork.com/rss/site_2/0.xml",
            "https://www.nature.com/nm.rss",
            "https://www.nature.com/nature.rss",
        ],
        "prompt": """
        你是辅助生殖 AI 与胚胎植入前遗传学检测（PGT）进展日报编辑。请基于候选材料输出中文日报。

        输出结构固定为：今日总览、重点论文精读、其他研究进展、临床可用性判断、证据强度与风险、来源链接。
        要求：
        - 全文 1800-2600 中文字以内。
        - 从候选中选 1 篇最值得精读的论文，用 700-1000 中文字展开。
        - 精读必须包含：研究问题、研究设计、样本/数据来源、AI 模型或 PGT 技术、主要终点、核心结果、局限、临床适用边界、伦理/监管注意事项。
        - 区分 AI embryo selection、time-lapse embryo assessment、live birth prediction、PGT-A、PGT-M、PGT-SR、non-invasive PGT。
        - 医学论文来源要特别留意 New England Journal of Medicine, The Lancet, BMJ, JAMA, Cell, Nature, Science；如果候选来自这些期刊，请优先考虑其证据质量和临床影响。
        - 标注证据强度：RCT/前瞻性队列/回顾性研究/技术验证/综述/abstract-only。
        - 不提供诊疗建议，不暗示可替代医生判断。
        - 不编造样本量、终点、统计显著性、指南建议；无法确认时标注“摘要未说明”或“待核验”。
        """,
    },
}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def shanghai_today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def fetch_arxiv(keywords: list[str], max_candidates: int) -> list[dict]:
    query = " OR ".join(f"all:{kw}" for kw in keywords)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_candidates,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    response = requests.get(ARXIV_API, params=params, timeout=30)
    response.raise_for_status()

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(response.text)
    papers = []
    for entry in root.findall("atom:entry", ns):
        link = entry.findtext("atom:id", "", ns)
        papers.append(
            {
                "type": "paper",
                "source": "arXiv",
                "title": " ".join((entry.findtext("atom:title", "", ns) or "").split()),
                "authors": ", ".join(
                    author.findtext("atom:name", "", ns)
                    for author in entry.findall("atom:author", ns)
                    if author.findtext("atom:name", "", ns)
                ),
                "id": link.rsplit("/", 1)[-1] if link else "",
                "link": link,
                "published": entry.findtext("atom:published", "", ns),
                "updated": entry.findtext("atom:updated", "", ns),
                "abstract": " ".join((entry.findtext("atom:summary", "", ns) or "").split())[:1800],
            }
        )
    return papers[:max_candidates]


def fetch_feeds(feed_urls: list[str], limit: int) -> list[dict]:
    items: list[dict] = []
    for feed_url in feed_urls:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            items.append(
                {
                    "type": "source_error",
                    "source": urllib.parse.urlparse(feed_url).netloc,
                    "link": feed_url,
                    "summary": f"Feed parse failed: {exc}",
                }
            )
            continue
        source = parsed.feed.get("title", urllib.parse.urlparse(feed_url).netloc)
        for entry in parsed.entries[:4]:
            title = html.unescape(entry.get("title", "")).strip()
            link = entry.get("link", "").strip()
            summary = html.unescape(entry.get("summary", "")).strip()
            if title and link:
                items.append(
                    {
                        "type": "news_or_report",
                        "source": source,
                        "title": title,
                        "link": link,
                        "published": entry.get("published", entry.get("updated", "")),
                        "summary": " ".join(summary.split())[:900],
                    }
                )
    return items[:limit]


def fetch_pubmed(query: str, limit: int) -> list[dict]:
    search_response = requests.get(
        PUBMED_ESEARCH_API,
        params={
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": limit,
            "sort": "pub date",
        },
        timeout=30,
    )
    search_response.raise_for_status()
    ids = search_response.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    fetch_response = requests.get(
        PUBMED_EFETCH_API,
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        timeout=30,
    )
    fetch_response.raise_for_status()
    root = ET.fromstring(fetch_response.text)

    papers = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", "")
        title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else ""
        abstract_parts = [
            "".join(part.itertext())
            for part in article.findall(".//Abstract/AbstractText")
        ]
        journal = article.findtext(".//Journal/Title", "")
        pub_date = " ".join(
            value
            for value in [
                article.findtext(".//PubDate/Year", ""),
                article.findtext(".//PubDate/Month", ""),
                article.findtext(".//PubDate/Day", ""),
            ]
            if value
        )
        authors = []
        for author in article.findall(".//Author")[:8]:
            last = author.findtext("LastName", "")
            fore = author.findtext("ForeName", "")
            full = " ".join(part for part in [fore, last] if part)
            if full:
                authors.append(full)
        papers.append(
            {
                "type": "medical_paper",
                "source": "PubMed",
                "title": " ".join(title.split()),
                "authors": ", ".join(authors),
                "journal": journal,
                "pmid": pmid,
                "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "published": pub_date,
                "abstract": " ".join(" ".join(abstract_parts).split())[:2200],
            }
        )
    return papers


def dedupe_items(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        key = item.get("pmid") or item.get("link") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def fetch_pubmed_with_journals(query: str, journals: list[str], limit: int) -> list[dict]:
    primary = fetch_pubmed(query, limit)
    if not journals:
        return primary

    journal_query = " OR ".join(f'"{journal}"[Journal]' for journal in journals)
    expanded_query = f"({query}) AND ({journal_query})"
    journal_hits = fetch_pubmed(expanded_query, limit)
    return dedupe_items(journal_hits + primary)[:limit]


def arxiv_pdf_url(abs_url: str) -> str:
    return abs_url.replace("/abs/", "/pdf/")


def enrich_papers_with_pdf_excerpt(papers: list[dict]) -> list[dict]:
    max_pdfs = env_int("ARXIV_MAX_PDFS", 3)
    max_pages = env_int("PDF_MAX_PAGES", 8)
    max_chars = env_int("PDF_EXCERPT_CHARS", 9000)

    for paper in papers[:max_pdfs]:
        if paper.get("source") != "arXiv":
            continue
        link = paper.get("link", "")
        if not link:
            continue
        try:
            pdf_response = requests.get(arxiv_pdf_url(link), timeout=45)
            pdf_response.raise_for_status()
            pdf_path = f"/tmp/{paper.get('id', 'paper').replace('/', '_')}.pdf"
            with open(pdf_path, "wb") as handle:
                handle.write(pdf_response.content)

            reader = PdfReader(pdf_path)
            excerpt = " ".join(
                "\n".join(page.extract_text() or "" for page in reader.pages[:max_pages]).split()
            )[:max_chars]
            if excerpt:
                paper["pdf_excerpt"] = excerpt
                paper["pdf_excerpt_note"] = (
                    f"Extracted from first {min(max_pages, len(reader.pages))} PDF pages."
                )
        except Exception as exc:
            paper["pdf_excerpt_error"] = str(exc)[:240]
    return papers


def load_paper_insight_skill() -> str:
    skill_path = os.getenv("PAPER_INSIGHT_SKILL_PATH", "")
    if not skill_path:
        return ""
    max_chars = env_int("PAPER_INSIGHT_SKILL_CHARS", 6000)
    try:
        with open(skill_path, "r", encoding="utf-8") as handle:
            return handle.read()[:max_chars]
    except OSError as exc:
        print(f"Could not read paper-insight skill: {exc}", file=sys.stderr)
        return ""


def collect_sources(topic_key: str, topic: dict) -> tuple[list[dict], list[dict]]:
    candidate_limit = env_int("CANDIDATE_LIMIT", env_int("ARXIV_MAX_CANDIDATES", 12))
    news_limit = env_int("NEWS_LIMIT", 9)
    mode = topic["source_mode"]

    if mode == "ai_llm":
        papers = fetch_arxiv(topic["arxiv_keywords"], candidate_limit)
        return enrich_papers_with_pdf_excerpt(papers), fetch_feeds(topic["feeds"], news_limit)
    if mode == "feeds_only":
        manual_sources = topic.get("manual_sources", [])
        return [], manual_sources + fetch_feeds(topic["feeds"], news_limit)
    if mode == "pubmed":
        papers = fetch_pubmed_with_journals(
            topic["pubmed_query"],
            topic.get("pubmed_journals", []),
            candidate_limit,
        )
        return papers, fetch_feeds(topic.get("feeds", []), news_limit)
    raise ValueError(f"Unsupported source mode for {topic_key}: {mode}")


def build_prompt(topic_key: str, topic: dict, papers: list[dict], items: list[dict], today: dt.date) -> str:
    paper_limit = env_int("PAPER_LIMIT", 3)
    news_limit = env_int("NEWS_LIMIT", 3)
    paper_insight_skill = load_paper_insight_skill()
    topic_prompt = textwrap.dedent(topic["prompt"]).strip()
    return textwrap.dedent(
        f"""
        日期：{today.isoformat()}
        主题：{topic_key}

        paper-insight skill 摘录（适用于论文精读；优先遵循，但受本任务 token 预算约束）：
        {paper_insight_skill or "未读取到外部 paper-insight skill；使用内置轻量精读规则。"}

        主题分析规则：
        {topic_prompt.format(paper_limit=paper_limit, news_limit=news_limit)}

        通用要求：
        - 今日候选不够强时可以少写，不要凑数。
        - 所有重要判断都附来源链接或标注待核验。
        - 正文中仍要尽量在相关段落内写出关键来源链接；脚本会在末尾自动追加来源清单作为兜底。
        - 不要输出 API key、SendKey 或 GitHub secret 名称的值。

        候选论文/医学文献 JSON：
        {json.dumps(papers, ensure_ascii=False, separators=(",", ":"))}

        候选文章/资讯/政策/报告 JSON：
        {json.dumps(items, ensure_ascii=False, separators=(",", ":"))}
        """
    ).strip()


def append_source_links(digest: str, papers: list[dict], items: list[dict]) -> str:
    limit = env_int("SOURCE_LINK_LIMIT", 16)
    sources = []
    for item in papers + items:
        link = item.get("link", "")
        if not link:
            continue
        label = item.get("title") or item.get("source") or link
        source = item.get("source", "")
        display = f"{source}: {label}" if source and source not in label else label
        sources.append({"display": " ".join(display.split())[:140], "link": link})

    deduped = []
    seen = set()
    for source in sources:
        if source["link"] in seen:
            continue
        seen.add(source["link"])
        deduped.append(source)
        if len(deduped) >= limit:
            break

    if not deduped:
        return digest

    link_lines = "\n".join(
        f"- {idx}. {source['display']}: {source['link']}"
        for idx, source in enumerate(deduped, start=1)
    )
    return f"{digest.rstrip()}\n\n---\n自动来源清单（脚本追加，防漏链）\n{link_lines}"


def call_deepseek(prompt: str, system_prompt: str) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY")

    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    max_tokens = env_int("MAX_COMPLETION_TOKENS", 2600)
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
                    {"role": "system", "content": system_prompt},
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
    text = choices[0].get("message", {}).get("content", "").strip() if choices else ""
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
    topic_key = os.getenv("DIGEST_TOPIC", "ai_llm")
    if topic_key not in TOPICS:
        raise RuntimeError(f"Unknown DIGEST_TOPIC: {topic_key}. Valid topics: {', '.join(TOPICS)}")

    today = shanghai_today()
    topic = TOPICS[topic_key]
    papers, items = collect_sources(topic_key, topic)
    prompt = build_prompt(topic_key, topic, papers, items, today)
    digest = call_deepseek(prompt, topic["system_prompt"])
    digest = append_source_links(digest, papers, items)

    title = f"{topic['title_prefix']} {today.isoformat()}"
    print(digest)
    if os.getenv("DRY_RUN") == "1":
        print(f"\nDRY_RUN=1: skipped ServerChan push ({topic_key})")
        return 0
    push_serverchan(title, digest)
    print(f"\nServerChan push: SUCCESS ({topic_key})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
