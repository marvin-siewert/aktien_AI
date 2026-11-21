"""
Multi-Source & Multi-Facet News Fetcher Service.

Combines 4 independent news channels:
1. Google News RSS (German DE + English US feeds — indexes Reuters, Handelsblatt, Tagesschau, Bloomberg, CNBC, etc.)
2. DuckDuckGo News Search (`duckduckgo-search`)
3. Tavily Search API (`tavily-python`) if `TAVILY_API_KEY` is configured
4. Yahoo Finance Ticker News (`yfinance.Ticker(ticker).news`)

Executes 3 targeted facet searches per stock so critical risks are never drowned out by routine earnings news:
- Facet A [RISK / SCANDAL]: Espionage, smuggling, SEC/DOJ investigation, lawsuit, fraud, accounting scandal
- Facet B [POLITICS / REGULATION]: Election impact, Democrats/Republicans, export restrictions, China ban, tariffs, sanctions
- Facet C [FINANCIALS / MARKET]: Earnings, analyst ratings, guidance, market demand
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

import requests
import yfinance as yf

from src.models.entities import NewsArticle

logger = logging.getLogger(__name__)


def _clean_company_query_name(company_name: str, ticker: str) -> str:
    """Strip corporate legal suffixes (Corp., Inc., SE, AG, N.V.) for cleaner news search queries."""
    base = company_name.strip() if company_name else ticker.strip()
    for suffix in (
        "Corporation", "Corp.", "Corp", "Incorporated", "Inc.", "Inc",
        "Holding N.V.", "N.V.", "SE", "AG", "Co.", "Ltd.", "PLC", "plc", ".DE", ".AS",
    ):
        base = re.sub(rf"\b{re.escape(suffix)}\b", "", base, flags=re.IGNORECASE).strip()
    base = base.strip(" ,.-")
    return base if len(base) >= 2 else ticker.split(".")[0]


class NewsFetcher:
    """
    Retrieves recent financial, investigative/scandal, and geopolitical/regulatory news articles
    with verified URLs across multiple international and German news sources.
    """

    def __init__(self, tavily_api_key: Optional[str] = None) -> None:
        env_key = tavily_api_key if tavily_api_key is not None else os.getenv("TAVILY_API_KEY", "")
        if env_key and env_key != "your_tavily_api_key_here":
            self.tavily_api_key: Optional[str] = env_key.strip()
        else:
            self.tavily_api_key = None

    def fetch_news(
        self,
        ticker: str,
        company_name: str = "",
        days: int = 30,
        max_results: int = 12,
    ) -> List[NewsArticle]:
        """
        Fetch a diversified set of up to `max_results` news articles covering:
        1. Scandals, espionage, investigations & legal risks
        2. Geopolitics, elections, export restrictions & tariffs
        3. Financials, earnings & market developments
        """
        clean_ticker = ticker.strip().upper()
        short_name = _clean_company_query_name(company_name, clean_ticker)
        time_window = f"when:{max(1, days)}d"

        # 3-Facet Search Queries (German + English) to guarantee risk & political coverage
        facet_queries = [
            # 1. Scandal / Espionage / Legal Probe (DE + EN)
            (
                "RISIKO/SKANDAL",
                f'"{short_name}" (Spionage OR Affäre OR Skandal OR Ermittlung OR Schmuggel OR Klage OR Untersuchung) {time_window}',
                "de",
            ),
            (
                "RISIKO/SKANDAL",
                f'"{short_name}" (espionage OR smuggling OR scandal OR investigation OR probe OR SEC OR lawsuit OR fraud) {time_window}',
                "en",
            ),
            # 2. Politics / Election / Export Restrictions (DE + EN)
            (
                "POLITIK/RESTRIKTION",
                f'"{short_name}" (Restriktionen OR Export OR Wahl OR Demokraten OR China OR Sanktionen OR Zölle OR Verbot) {time_window}',
                "de",
            ),
            (
                "POLITIK/RESTRIKTION",
                f'"{short_name}" (restrictions OR "export controls" OR election OR Democrats OR China OR ban OR tariff OR regulation) {time_window}',
                "en",
            ),
            # 3. General Financials & Market News (DE + EN)
            (
                "FINANZEN/MARKT",
                f'"{short_name}" Aktie (Kurs OR Quartalszahlen OR Ausblick OR Analysten) {time_window}',
                "de",
            ),
            (
                "FINANZEN/MARKT",
                f'"{short_name}" ({clean_ticker}) stock news {time_window}',
                "en",
            ),
        ]

        collected: List[NewsArticle] = []

        # Channel 1: Google News RSS Multi-Facet Search (DE + EN)
        for facet_tag, q_str, lang_code in facet_queries:
            rss_items = self._fetch_google_news_rss(
                query=q_str,
                lang=lang_code,
                facet_tag=facet_tag,
                limit=3,
            )
            collected.extend(rss_items)

        # Channel 2: Tavily API (if configured)
        if self.tavily_api_key:
            collected.extend(
                self._fetch_via_tavily(
                    f"{short_name} ({clean_ticker}) stock scandal investigation export restrictions election earnings",
                    days=days,
                    max_results=5,
                )
            )

        # Channel 3: DuckDuckGo News Search (Risk + General)
        ddg_queries = [
            ("RISIKO/POLITIK", f"{short_name} espionage scandal investigation export restrictions election China"),
            ("FINANZEN/MARKT", f"{short_name} {clean_ticker} stock financial news"),
        ]
        for facet_tag, dq in ddg_queries:
            collected.extend(self._fetch_via_duckduckgo(dq, days=days, max_results=3, facet_tag=facet_tag))

        # Channel 4: Yahoo Finance Ticker News
        collected.extend(self._fetch_via_yfinance(clean_ticker, max_results=4))

        # Deduplicate by normalized title and URL while preserving balanced facet priority
        deduped = self._deduplicate_articles(collected, max_results=max_results)

        if deduped:
            return deduped

        # Offline safety fallback
        return [
            NewsArticle(
                title=f"{short_name} ({clean_ticker}) - Yahoo Finance Market Quote & News Overview",
                url=f"https://finance.yahoo.com/quote/{clean_ticker}",
                source="Yahoo Finance",
                published_at=datetime.now().strftime("%Y-%m-%d"),
                snippet=f"Official market quote and financial news summary page for {short_name} ({clean_ticker}).",
            )
        ]

    def _fetch_google_news_rss(
        self,
        query: str,
        lang: str = "de",
        facet_tag: str = "NEWS",
        limit: int = 3,
    ) -> List[NewsArticle]:
        """
        Query Google News RSS feed (free, no API key required, aggregates Reuters, Handelsblatt,
        Tagesschau, Bloomberg, FAZ, CNBC, WSJ, etc.).
        """
        try:
            encoded_q = urllib.parse.quote(query)
            if lang == "de":
                url = f"https://news.google.com/rss/search?q={encoded_q}&hl=de&gl=DE&ceid=DE:de"
            else:
                url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code != 200 or not resp.text.strip():
                return []

            root = ET.fromstring(resp.content)
            articles: List[NewsArticle] = []
            for item in root.findall(".//item")[:limit]:
                raw_title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                source_el = item.find("source")
                source_name = (source_el.text if source_el is not None and source_el.text else "Google News").strip()
                raw_desc = (item.findtext("description") or "").strip()
                clean_desc = re.sub(r"<[^>]+>", " ", raw_desc)
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

                if not raw_title or not link:
                    continue

                tagged_title = f"[{facet_tag}] {raw_title}" if not raw_title.startswith("[") else raw_title
                articles.append(
                    NewsArticle(
                        title=tagged_title,
                        url=link,
                        source=source_name,
                        published_at=pub_date[:25],
                        snippet=(clean_desc or raw_title)[:600],
                    )
                )
            return articles
        except Exception as exc:
            logger.debug("Google News RSS fetch failed for '%s': %s", query, exc)
            return []

    def _fetch_via_tavily(self, query_subject: str, days: int, max_results: int) -> List[NewsArticle]:
        """Fetch financial news articles using the Tavily Python SDK."""
        try:
            from tavily import TavilyClient  # type: ignore

            client = TavilyClient(api_key=self.tavily_api_key)
            response = client.search(
                query=query_subject,
                topic="news",
                days=max(1, days),
                max_results=max_results,
            )
            results = response.get("results", []) if isinstance(response, dict) else []
            articles: List[NewsArticle] = []
            for item in results:
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                if not url or not title:
                    continue
                articles.append(
                    NewsArticle(
                        title=title,
                        url=url,
                        source=str(item.get("source") or "Tavily News"),
                        published_at=str(item.get("published_date") or ""),
                        snippet=str(item.get("content") or "")[:600],
                    )
                )
            return articles[:max_results]
        except Exception as exc:
            logger.warning("Tavily news fetch failed for %s: %s", query_subject, exc)
            return []

    def _fetch_via_duckduckgo(
        self,
        query: str,
        days: int,
        max_results: int,
        facet_tag: str = "NEWS",
    ) -> List[NewsArticle]:
        """Fetch recent news articles using duckduckgo-search without requiring an API key."""
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from duckduckgo_search import DDGS  # type: ignore

                timelimit = "d" if days <= 2 else "m"
                articles: List[NewsArticle] = []
                with DDGS() as ddgs:
                    results = list(ddgs.news(query, timelimit=timelimit, max_results=max_results))
                for item in results:
                    url = str(item.get("url") or "").strip()
                    title = str(item.get("title") or "").strip()
                    if not url or not title:
                        continue
                    tagged = f"[{facet_tag}] {title}" if not title.startswith("[") else title
                    articles.append(
                        NewsArticle(
                            title=tagged,
                            url=url,
                            source=str(item.get("source") or "DuckDuckGo News"),
                            published_at=str(item.get("date") or "")[:25],
                            snippet=str(item.get("body") or title)[:600],
                        )
                    )
                return articles[:max_results]
        except Exception as exc:
            logger.debug("DuckDuckGo news fetch failed for %s: %s", query, exc)
            return []

    def _fetch_via_yfinance(self, ticker: str, max_results: int) -> List[NewsArticle]:
        """Fetch recent news items directly from Yahoo Finance ticker object."""
        try:
            raw_news = yf.Ticker(ticker).news or []
            articles: List[NewsArticle] = []
            for item in raw_news[:max_results]:
                if not isinstance(item, dict):
                    continue
                content = item.get("content", item) if isinstance(item.get("content"), dict) else item
                title = str(content.get("title") or item.get("title") or "").strip()
                url = ""
                if isinstance(content.get("canonicalUrl"), dict):
                    url = str(content["canonicalUrl"].get("url") or "")
                elif isinstance(content.get("clickThroughUrl"), dict):
                    url = str(content["clickThroughUrl"].get("url") or "")
                else:
                    url = str(item.get("link") or content.get("url") or "")
                if not title or not url:
                    continue
                provider = (
                    content.get("provider", {}).get("displayName", "Yahoo Finance")
                    if isinstance(content.get("provider"), dict)
                    else item.get("publisher", "Yahoo Finance")
                )
                articles.append(
                    NewsArticle(
                        title=f"[FINANZEN/MARKT] {title}" if not title.startswith("[") else title,
                        url=url,
                        source=str(provider),
                        published_at=str(content.get("pubDate") or "")[:25],
                        snippet=str(content.get("summary") or title)[:600],
                    )
                )
            return articles
        except Exception as exc:
            logger.debug("yfinance news fetch failed for %s: %s", ticker, exc)
            return []

    def _deduplicate_articles(self, articles: List[NewsArticle], max_results: int) -> List[NewsArticle]:
        """Deduplicate articles by URL and normalized title while keeping diverse risk/political coverage."""
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        unique: List[NewsArticle] = []

        for art in articles:
            u = art.url.strip()
            # Normalize title without facet prefix and publisher trailer
            core_title = re.sub(r"^\[[^\]]+\]\s*", "", art.title).split(" - ")[0].strip().lower()
            norm_title = re.sub(r"[^a-z0-9äöüß]+", "", core_title)[:65]
            if not u or not norm_title:
                continue
            if u in seen_urls or norm_title in seen_titles:
                continue
            seen_urls.add(u)
            seen_titles.add(norm_title)
            unique.append(art)
            if len(unique) >= max_results:
                break
        return unique
