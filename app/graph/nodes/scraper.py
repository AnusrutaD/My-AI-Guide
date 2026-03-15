"""
The Trend Scraper Node — powered by Tavily.

Strategy: three concurrent search passes per session
  Pass 1  — Company-specific recent interview reports (LeetCode Discuss / Reddit)
  Pass 2  — Topic + subtopic technical questions (last 12 months)
  Pass 3  — Target company engineering blog / tech talk (authoritative signal)

Results are deduplicated by URL, scored by recency + company relevance,
then synthesised into a single context block for the Question Setter.
"""

import asyncio
import logging
import re
from datetime import date
from urllib.parse import urlparse

from tavily import AsyncTavilyClient

from app.config import get_settings
from app.graph.state import AgentState

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Company profiles ──────────────────────────────────────────────────────────

_COMPANY_PROFILES: dict[str, dict] = {
    "Visa": {
        "aliases": ["Visa Inc", "Visa payments", "Visa Grid Dynamics"],
        "tech_keywords": [
            "ISO 8583", "payment processing", "authorization", "settlement",
            "idempotency", "distributed transaction", "Kafka", "Spring Boot",
            "high throughput", "rate limiting", "PCI-DSS",
        ],
        "blog_domains": ["developer.visa.com", "visatechblog.com"],
        "reddit_flair": "Visa",
        "interview_focus": "system design at fintech scale, concurrency, Java",
    },
    "Google": {
        "aliases": ["Google LLC", "Alphabet", "Google SWE"],
        "tech_keywords": [
            "MapReduce", "Bigtable", "Spanner", "Borg", "Colossus",
            "consistent hashing", "LRU cache", "distributed systems",
            "graph algorithms", "dynamic programming",
        ],
        "blog_domains": ["research.google", "engineering.googleblog.com"],
        "reddit_flair": "Google",
        "interview_focus": "LeetCode Hard, system design at planetary scale",
    },
    "Meta": {
        "aliases": ["Facebook", "Meta Platforms", "Meta SWE"],
        "tech_keywords": [
            "social graph", "TAO", "Cassandra", "RocksDB", "Thrift",
            "graph BFS/DFS at scale", "news feed", "real-time messaging",
            "eventual consistency", "CRDT",
        ],
        "blog_domains": ["engineering.fb.com", "research.facebook.com"],
        "reddit_flair": "Meta",
        "interview_focus": "graph problems, product-sense system design, scale",
    },
    "Amazon": {
        "aliases": ["AWS", "Amazon.com"],
        "tech_keywords": [
            "DynamoDB", "SQS", "S3", "Lambda", "event-driven",
            "two-phase commit", "leader election", "distributed locking",
        ],
        "blog_domains": ["aws.amazon.com/blogs", "developer.amazon.com"],
        "reddit_flair": "Amazon",
        "interview_focus": "leadership principles + system design, OOP",
    },
}

_YEAR = date.today().year
_PREV_YEAR = _YEAR - 1

# ── Query builders ────────────────────────────────────────────────────────────


def _query_company_interview_reports(company: str, topic: str, subtopic: str) -> str:
    """LeetCode Discuss + Reddit: recent interview reports mentioning this company and topic."""
    profile = _COMPANY_PROFILES.get(company, {})
    aliases = " OR ".join(f'"{a}"' for a in [company] + profile.get("aliases", [])[:1])
    return (
        f'({aliases}) interview experience "{topic}" {subtopic} '
        f'({_YEAR} OR {_PREV_YEAR}) '
        f'site:leetcode.com/discuss OR site:reddit.com/r/cscareerquestions '
        f'OR site:reddit.com/r/leetcode OR site:reddit.com/r/ExperiencedDevs'
    )


def _query_topic_deep_dive(topic: str, subtopic: str, difficulty: str) -> str:
    """Broad technical search for edge cases and hard variants of the topic."""
    diff_keywords = {
        "EXPERT": "staff engineer principal hard advanced edge case pitfall",
        "HARD": "senior engineer hard edge case concurrency distributed",
        "MEDIUM": "engineer medium tricky interview",
    }.get(difficulty, "senior engineer interview")
    return (
        f'"{topic}" "{subtopic}" interview question {diff_keywords} '
        f'({_YEAR} OR {_PREV_YEAR})'
    )


def _query_eng_blog(company: str, topic: str, subtopic: str) -> str:
    """Official engineering blog posts — authoritative signal on how the company uses this tech."""
    profile = _COMPANY_PROFILES.get(company, {})
    domains = profile.get("blog_domains", [])
    if not domains:
        return f'{company} engineering {topic} {subtopic} production scale'
    domain_filter = " OR ".join(f"site:{d}" for d in domains)
    return f'({domain_filter}) {topic} {subtopic}'


# ── Result processing ─────────────────────────────────────────────────────────


def _score_result(result: dict, company: str, topic: str, subtopic: str) -> float:
    """Heuristic relevance score for ranking Tavily results."""
    score = 0.0
    text = (result.get("title", "") + " " + result.get("content", "")).lower()
    url = result.get("url", "").lower()

    # Recency bonus — Tavily sometimes embeds year in content
    if str(_YEAR) in text:
        score += 3.0
    elif str(_PREV_YEAR) in text:
        score += 1.5

    # Company name match
    if company.lower() in text:
        score += 2.0
    profile = _COMPANY_PROFILES.get(company, {})
    for kw in profile.get("tech_keywords", []):
        if kw.lower() in text:
            score += 0.5

    # Topic relevance
    if topic.lower() in text:
        score += 1.5
    if subtopic.lower() in text:
        score += 1.0

    # Source quality
    high_signal_domains = [
        "leetcode.com/discuss", "engineering.fb.com", "research.google",
        "engineering.googleblog.com", "developer.visa.com",
        "reddit.com/r/ExperiencedDevs",
    ]
    for domain in high_signal_domains:
        if domain in url:
            score += 2.0
            break

    # Penalise very short snippets (low info density)
    if len(result.get("content", "")) < 100:
        score -= 1.0

    return score


def _deduplicate(results: list[dict]) -> list[dict]:
    """Remove results with duplicate domains (keep highest-scored copy)."""
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(r)
    return unique


def _format_snippet(result: dict, idx: int) -> str:
    title = result.get("title", f"Source {idx}")
    url = result.get("url", "")
    content = result.get("content", "")[:500].strip()
    domain = urlparse(url).netloc
    return f"[{idx}] **{title}** · {domain}\n{content}"


# ── Main scraper node ─────────────────────────────────────────────────────────


async def _run_search(
    client: AsyncTavilyClient,
    query: str,
    max_results: int = 5,
    include_answer: bool = False,
) -> dict:
    try:
        return await client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=include_answer,
            include_raw_content=False,
        )
    except Exception as exc:
        logger.warning("[Scraper] Search failed for query '%s…': %s", query[:60], exc)
        return {"results": [], "answer": None}


async def scraper_node(state: AgentState) -> AgentState:
    """
    Fetch trending interview questions using three concurrent Tavily passes.
    Returns a rich trend_context block for the Question Setter.
    """
    topic = state.get("current_topic", "System Design")
    subtopic = state.get("current_subtopic", "general")
    companies = state.get("target_companies", ["Visa", "Google", "Meta"])
    difficulty = state.get("suggested_difficulty", "HARD")

    logger.info(
        "[Scraper] Searching for %s / %s | companies=%s | difficulty=%s",
        topic, subtopic, companies, difficulty,
    )

    if not settings.tavily_api_key:
        logger.warning("[Scraper] TAVILY_API_KEY not set — returning curated fallback context")
        return {"recent_trend_context": _fallback_context(topic, subtopic, companies)}

    client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    # Primary company is the first in the list (usually Visa for this user)
    primary_company = companies[0] if companies else "Visa"

    # Build three query variants
    q1 = _query_company_interview_reports(primary_company, topic, subtopic)
    q2 = _query_topic_deep_dive(topic, subtopic, difficulty)
    q3 = _query_eng_blog(primary_company, topic, subtopic)

    # Also search secondary companies if provided
    secondary_queries = [
        _query_company_interview_reports(c, topic, subtopic)
        for c in companies[1:3]
    ]

    logger.debug("[Scraper] Queries:\n  P1: %s\n  P2: %s\n  P3: %s", q1, q2, q3)

    # Run all searches concurrently
    all_queries = [q1, q2, q3] + secondary_queries
    responses = await asyncio.gather(
        *[_run_search(client, q, max_results=4, include_answer=(i == 0)) for i, q in enumerate(all_queries)]
    )

    # Collect Tavily-synthesised answer from pass 1 (most targeted)
    synthesis = responses[0].get("answer", "") if responses else ""

    # Merge, score, deduplicate, and select top results
    all_results: list[dict] = []
    for resp in responses:
        all_results.extend(resp.get("results", []))

    scored = sorted(
        _deduplicate(all_results),
        key=lambda r: _score_result(r, primary_company, topic, subtopic),
        reverse=True,
    )
    top_results = scored[:6]

    snippets = [_format_snippet(r, i + 1) for i, r in enumerate(top_results)]

    # Build the context block
    parts: list[str] = []

    if synthesis:
        parts.append(f"## TAVILY SYNTHESIS (Company: {primary_company}, Topic: {topic}/{subtopic})\n{synthesis}")

    # Company tech context — inject known focus areas even without live results
    profile = _COMPANY_PROFILES.get(primary_company, {})
    if focus := profile.get("interview_focus"):
        parts.append(f"## {primary_company} KNOWN INTERVIEW FOCUS\n{focus}")
    if tech_kws := profile.get("tech_keywords", []):
        parts.append(f"## {primary_company} KEY TECHNOLOGIES\n{', '.join(tech_kws)}")

    if snippets:
        parts.append("## LIVE SOURCES\n" + "\n\n".join(snippets))
    else:
        parts.append(f"## NOTE\nNo live results returned. Rely on known {primary_company} patterns above.")

    trend_context = "\n\n".join(parts)

    logger.info(
        "[Scraper] Collected %d results → top %d, context=%d chars",
        len(all_results), len(top_results), len(trend_context),
    )

    return {"recent_trend_context": trend_context}


# ── Fallback (no API key) ─────────────────────────────────────────────────────


def _fallback_context(topic: str, subtopic: str, companies: list[str]) -> str:
    """
    Curated static context for when Tavily is unavailable.
    Hardcoded from what's publicly known about Visa/Google/Meta interview patterns.
    """
    company_contexts = []
    for c in companies[:2]:
        profile = _COMPANY_PROFILES.get(c)
        if not profile:
            continue
        kws = ", ".join(profile.get("tech_keywords", [])[:6])
        focus = profile.get("interview_focus", "")
        company_contexts.append(
            f"**{c}**: Focus → {focus}\n"
            f"Key tech/concepts seen in interviews: {kws}"
        )

    return (
        f"## STATIC FALLBACK (Tavily unavailable)\n"
        f"Topic: {topic} / {subtopic}\n\n"
        + "\n\n".join(company_contexts)
        + f"\n\n**Action for Question Setter:** Generate a question that specifically "
        f"tests edge cases in {subtopic} that would surface in a {', '.join(companies[:2])} "
        f"production system context."
    )
