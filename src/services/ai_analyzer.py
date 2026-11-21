"""
AI & Forensic News Risk Analyzer Service.

Implements:
1. Red-Team / Devil's Advocate Gemini LLM Prompting (`google-genai` SDK with Structured Outputs):
   - Explicitly forces the model to prioritize acute governance/espionage/legal scandals and
     geopolitical/election/export restriction risks over stale analyst price targets.
2. Local Headline & Content Risk Intelligence Engine (when no `GEMINI_API_KEY` is configured):
   - Scans all retrieved multi-source news articles for 3 intelligence clusters:
     a) Espionage, Smuggling, Accounting Probes, SEC/DOJ Investigations & Lawsuits
     b) Elections (Democrats/Republicans), Export Restrictions, China Bans, Tariffs & Regulation
     c) Positive & Negative Fundamental Earnings/Demand Catalysts
   - Automatically downgrades the Traffic Light (`GREEN` -> `YELLOW` or `RED`) when acute scandals
     or political/export restriction risks are detected, citing the exact articles and URLs!
3. Strict anti-hallucination URL filter: strips any URL not present in the retrieved news input.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from src.models.entities import (
    AIAnalysisResult,
    NewsArticle,
    SentinelLLMOutput,
    StockMetrics,
    ThesisRecord,
)

logger = logging.getLogger(__name__)

# Keyword patterns for local Forensic & Geopolitical News Intelligence (German + English)
SCANDAL_ESPIONAGE_KEYWORDS: Tuple[str, ...] = (
    "spionage", "espionage", "spying", "affäre", "affaere", "schmuggel", "smuggl",
    "skandal", "scandal", "sec probe", "sec-untersuchung", "sec investiga", "doj",
    "ermittlung", "investigation", "probe", "untersuchung", "betrug", "fraud",
    "accounting", "bilanz", "klage", "lawsuit", "subpoena", "indictment", "razzia",
    "raid", "korruption", "bribery", "datendiebstahl", "theft", "trade secret",
    "kartell", "antitrust", "whistleblower", "manipulation", "illegal",
)

POLITICAL_RESTRICTION_KEYWORDS: Tuple[str, ...] = (
    "restriktion", "restriction", "export control", "exportkontrolle", "exportverbot",
    "export ban", "chip ban", "embargo", "sanktion", "sanction", "wahl", "wahlsieg",
    "election", "demokraten", "democrat", "republikaner", "republican", "zoll", "zölle",
    "tariff", "regulierung", "regulation", "commerce department", "handelsministerium",
    "china-restriktion", "china restriction", "china curb", "chip-krieg", "chip war",
    "geopolit", "national security", "nationale sicherheit", "blacklist", "entity list",
)

NEGATIVE_MARKET_KEYWORDS: Tuple[str, ...] = (
    "gewinnwarnung", "profit warning", "einbruch", "rout", "sell-off", "selloff",
    "absturz", "plunge", "slump", "downgrade", "herabstufung", "miss", "enttäusch",
    "verlust", "verzögerung", "delay", "rückruf", "recall", "insolvenz", "krise",
)

POSITIVE_CATALYST_KEYWORDS: Tuple[str, ...] = (
    "rekord", "record", "wachstum", "growth", "beat", "übertrifft", "boom",
    "starke nachfrage", "strong demand", "upgrade", "kursziel erhöht", "auftrag",
    "partnership", "kooperation", "dividende", "buyback", "aktienrückkauf", "ki-boom",
)


@dataclass
class NewsRiskIntelligence:
    """Extracted forensic, geopolitical, and fundamental findings from retrieved news articles."""

    scandal_articles: List[NewsArticle] = field(default_factory=list)
    political_articles: List[NewsArticle] = field(default_factory=list)
    negative_market_articles: List[NewsArticle] = field(default_factory=list)
    positive_articles: List[NewsArticle] = field(default_factory=list)


def extract_news_intelligence(articles: List[NewsArticle]) -> NewsRiskIntelligence:
    """
    Scan all retrieved NewsArticle titles and snippets for espionage/scandals/probes,
    political/election/export restrictions, and fundamental catalysts.
    """
    intel = NewsRiskIntelligence()
    for art in articles:
        clean_title = re.sub(r"^\[[^\]]+\]\s*", "", art.title)
        text_lower = f"{clean_title} {art.snippet}".lower()

        is_scandal = any(kw in text_lower for kw in SCANDAL_ESPIONAGE_KEYWORDS)
        is_political = any(kw in text_lower for kw in POLITICAL_RESTRICTION_KEYWORDS)
        is_neg = any(kw in text_lower for kw in NEGATIVE_MARKET_KEYWORDS)
        is_pos = any(kw in text_lower for kw in POSITIVE_CATALYST_KEYWORDS)

        if is_scandal:
            intel.scandal_articles.append(art)
        if is_political:
            intel.political_articles.append(art)
        if is_neg and not is_scandal:
            intel.negative_market_articles.append(art)
        if is_pos:
            intel.positive_articles.append(art)

    return intel


def filter_verified_urls(cited_urls: List[str], input_articles: List[NewsArticle], max_urls: int = 6) -> List[str]:
    """
    Anti-hallucination guard: only keep URLs that match the exact URLs provided in `input_articles`.
    If the LLM omitted valid URLs or hallucinated non-existent ones, fall back to the verified input URLs.
    """
    allowed_urls = [art.url.strip() for art in input_articles if art.url.strip()]
    allowed_set = set(allowed_urls)

    verified = [u.strip() for u in cited_urls if u.strip() in allowed_set]
    seen: set[str] = set()
    unique_verified = [u for u in verified if not (u in seen or seen.add(u))]

    if not unique_verified and allowed_urls:
        return allowed_urls[:max_urls]
    return unique_verified[:max_urls]


def _clean_headline(title: str) -> str:
    """Remove internal facet tag prefix like '[RISIKO/SKANDAL] ' for clean display."""
    return re.sub(r"^\[[^\]]+\]\s*", "", title).strip()


class AIAnalyzer:
    """
    Qualitative financial news and forensic risk analyzer powered by Google Gemini Structured Outputs
    and a local multi-cluster News Risk Intelligence Engine.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        raw_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        if raw_key and raw_key != "your_gemini_api_key_here":
            self.api_key: Optional[str] = raw_key.strip()
        else:
            self.api_key = None
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def analyze_monthly_deep_dive(
        self,
        metrics: StockMetrics,
        articles: List[NewsArticle],
        language: str = "de",
    ) -> AIAnalysisResult:
        """
        Analyze 30-day multi-source news and analyst metrics for a stock without Sunk Cost bias.
        Prioritizes forensic risks (espionage, investigations, lawsuits) and political/regulatory
        shifts (election outcomes, export restrictions, tariffs) over lagging analyst consensus.
        """
        lang_name = "German (Deutsch)" if language.lower().startswith("de") else "English"
        intel = extract_news_intelligence(articles)

        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                articles_text = "\n\n".join(
                    f"[{idx}] Title: {art.title}\nSource: {art.source} ({art.published_at})\nURL: {art.url}\nSnippet: {art.snippet}"
                    for idx, art in enumerate(articles, start=1)
                )

                pre_detected_note = (
                    f"Pre-Scan Forensic Flags Detected:\n"
                    f"- Scandal/Espionage/Probe articles: {len(intel.scandal_articles)}\n"
                    f"- Political/Election/Export-Restriction articles: {len(intel.political_articles)}\n"
                )

                prompt = (
                    f"You are a Forensic Senior Equity & Risk Analyst ('Devil's Advocate'). Evaluate {metrics.name} ({metrics.ticker}) "
                    f"objectively based on the provided 30-day multi-source news articles and quantitative metrics.\n\n"
                    f"CRITICAL OVERRIDE RULE (Avoid Analyst Anchoring Bias):\n"
                    f"Wall Street analyst consensus ({metrics.recommendation_key}, +{metrics.upside_pct}% upside) often lags behind breaking news by weeks.\n"
                    f"You MUST actively inspect all provided articles for:\n"
                    f"1. Corporate Scandals, Espionage/Smuggling Affairs, SEC/DOJ Accounting Probes, or Lawsuits.\n"
                    f"2. Political Risks, Election Outcomes (e.g. Democrats/Republicans policy shifts), Export Restrictions (e.g. China chip controls), Tariffs, or Sanctions.\n"
                    f"If ANY acute scandal, espionage affair, regulatory investigation, or severe political/export restriction risk is present in the news, "
                    f"you MUST highlight it prominently in `summary` and `risks`, and downgrade `traffic_light` to YELLOW or RED even if analyst consensus is Strong Buy!\n\n"
                    f"{pre_detected_note}\n"
                    f"Quantitative Context:\n"
                    f"- Current Price: {metrics.current_price} {metrics.currency}\n"
                    f"- Analyst Mean Target Price: {metrics.target_mean_price} {metrics.currency} (Upside: {metrics.upside_pct}%)\n"
                    f"- Analyst Consensus: {metrics.recommendation_key} ({metrics.number_of_analyst_opinions} analysts)\n"
                    f"- Sector: {metrics.assigned_sector} | Country: {metrics.assigned_country}\n\n"
                    f"Provided News Articles (ONLY cite URLs from this exact list):\n{articles_text}\n\n"
                    f"Write `summary`, `catalysts`, and `risks` in {lang_name}. Cite ONLY exact URLs from the list above."
                )

                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AIAnalysisResult,
                        temperature=0.15,
                    ),
                )
                parsed = AIAnalysisResult.model_validate_json(response.text)
                parsed.cited_urls = filter_verified_urls(parsed.cited_urls, articles)
                return parsed
            except Exception as exc:
                logger.warning("Gemini Deep Dive call failed for %s (%s); using local News Risk Intelligence Engine.", metrics.ticker, exc)

        return self._local_intelligence_deep_dive(metrics, articles, intel=intel, language=language)

    def _local_intelligence_deep_dive(
        self,
        metrics: StockMetrics,
        articles: List[NewsArticle],
        intel: Optional[NewsRiskIntelligence] = None,
        language: str = "de",
    ) -> AIAnalysisResult:
        """
        Comprehensive local News & Risk Intelligence Engine (runs when no Gemini API key is configured).
        Evaluates all retrieved headlines and snippets for espionage/scandals, political/election
        export restrictions, and fundamental news, overriding purely quantitative buy ratings when risks appear.
        """
        if intel is None:
            intel = extract_news_intelligence(articles)

        is_de = language.lower().startswith("de")
        has_scandal = len(intel.scandal_articles) > 0
        has_political = len(intel.political_articles) > 0
        has_quant_buy = metrics.upside_pct >= 20.0 and metrics.recommendation_key in ("buy", "strong_buy", "outperform")

        # Prioritize URLs from scandal and political articles first so the user can inspect the exact risk sources
        priority_articles = (
            intel.scandal_articles[:3]
            + intel.political_articles[:3]
            + intel.negative_market_articles[:2]
            + intel.positive_articles[:2]
            + articles[:4]
        )
        priority_urls = filter_verified_urls([a.url for a in priority_articles], articles, max_urls=6)

        # Build concrete Risk bullets from actual news headlines
        risks: List[str] = []
        for art in intel.scandal_articles[:3]:
            headline = _clean_headline(art.title)
            prefix = "🚨 [Skandal / Spionage / Ermittlung]" if is_de else "🚨 [Scandal / Espionage / Probe]"
            risks.append(f"{prefix} {headline} ({art.source})")

        for art in intel.political_articles[:3]:
            headline = _clean_headline(art.title)
            prefix = "⚠️ [Politik / Wahl / Restriktionen]" if is_de else "⚠️ [Politics / Election / Restrictions]"
            risks.append(f"{prefix} {headline} ({art.source})")

        for art in intel.negative_market_articles[:2]:
            headline = _clean_headline(art.title)
            prefix = "📉 [Markt- & Kursdruck]" if is_de else "📉 [Market & Price Pressure]"
            risks.append(f"{prefix} {headline} ({art.source})")

        if not risks:
            risks = (
                [
                    f"Branchen- und Bewertungsrisiken im Sektor {metrics.assigned_sector}",
                    "Keine akuten Skandal- oder Sanktionsmeldungen in den abgerufenen Artikeln erkannt, jedoch allgemeine Marktvolatilität beachten.",
                ]
                if is_de
                else [
                    f"Sector and valuation headwinds in {metrics.assigned_sector}",
                    "No acute scandal or sanction headlines detected in retrieved articles, monitor general macro volatility.",
                ]
            )

        # Build concrete Catalyst bullets from positive news + analyst targets
        catalysts: List[str] = []
        for art in intel.positive_articles[:3]:
            headline = _clean_headline(art.title)
            catalysts.append(f"📈 {headline} ({art.source})")
        if metrics.upside_pct > 0:
            catalysts.append(
                f"Analysten-Konsensziel liegt bei {metrics.target_mean_price} {metrics.currency} "
                f"({metrics.upside_pct:+.1f}% Upside, {metrics.number_of_analyst_opinions} Analysten: {metrics.recommendation_key.upper()})"
                if is_de
                else f"Analyst mean target at {metrics.target_mean_price} {metrics.currency} "
                f"({metrics.upside_pct:+.1f}% upside, {metrics.number_of_analyst_opinions} analysts: {metrics.recommendation_key.upper()})"
            )
        if not catalysts:
            catalysts.append(
                "Operative Margenstabilisierung und nächste Quartalszahlen abwarten"
                if is_de
                else "Await operational margin stabilization and upcoming quarterly earnings"
            )

        # Determine Traffic Light & Root-Cause Summary (Risk-First Override Logic!)
        if has_scandal and (has_political or len(intel.scandal_articles) >= 2 or metrics.daily_change_pct <= -5.0):
            traffic = "RED"
            cause = "STRUCTURAL_PROBLEM"
            scandal_top = _clean_headline(intel.scandal_articles[0].title)
            pol_top = _clean_headline(intel.political_articles[0].title) if has_political else ""
            summary = (
                f"🚨 AKUTE RISIKO-WARNUNG trotz positivem Analysten-Konsens ({metrics.recommendation_key.upper()}, {metrics.upside_pct:+.1f}% Upside): "
                f"In den aktuellen Nachrichten wurden gravierende Risiko-Meldungen zu Skandalen/Spionage/Ermittlungen "
                f"('{scandal_top}')"
                + (f" sowie politischen Restriktionen/Wahlfolgen ('{pol_top}')" if pol_top else "")
                + " identifiziert. Analysten-Kursziele reagieren auf solche Ereignisse oft verzögert – vor einem Einstieg oder Nachkauf zwingend die verlinkten Originalquellen prüfen!"
                if is_de
                else f"🚨 ACUTE RISK WARNING despite positive analyst consensus ({metrics.recommendation_key.upper()}, {metrics.upside_pct:+.1f}% upside): "
                f"Current news articles reveal severe risk headlines regarding scandals/espionage/investigations "
                f"('{scandal_top}')"
                + (f" as well as political/election/export restrictions ('{pol_top}')" if pol_top else "")
                + ". Analyst price targets often lag behind breaking affairs — inspect the linked sources before buying!"
            )
        elif has_scandal or has_political:
            traffic = "YELLOW"
            cause = "NEUTRAL_OR_FAIRLY_VALUED"
            warn_items = []
            if has_scandal:
                warn_items.append(
                    f"Spionage-/Ermittlungs-/Skandal-Berichte ('{_clean_headline(intel.scandal_articles[0].title)}')"
                    if is_de
                    else f"Espionage/Investigation/Scandal reports ('{_clean_headline(intel.scandal_articles[0].title)}')"
                )
            if has_political:
                warn_items.append(
                    f"Politische Restriktions-/Wahl-Risiken ('{_clean_headline(intel.political_articles[0].title)}')"
                    if is_de
                    else f"Political restriction/election risks ('{_clean_headline(intel.political_articles[0].title)}')"
                )
            warn_joined = " & ".join(warn_items)
            summary = (
                f"⚠️ VORSICHT / BEOBACHTEN: Quantitativ zeigt {metrics.name} ({metrics.ticker}) zwar {metrics.upside_pct:+.1f}% Upside "
                f"({metrics.number_of_analyst_opinions} Analysten: {metrics.recommendation_key.upper()}), ABER die Nachrichtenanalyse meldet akute Warnsignale: "
                f"{warn_joined}. Aufgrund dieser politisch-rechtlichen Unsicherheiten wird die Kaufempfehlung auf GELB (Beobachten) herabgestuft."
                if is_de
                else f"⚠️ CAUTION / WATCH: Quantitatively {metrics.name} ({metrics.ticker}) shows {metrics.upside_pct:+.1f}% upside "
                f"({metrics.number_of_analyst_opinions} analysts: {metrics.recommendation_key.upper()}), BUT news intelligence flags acute risks: "
                f"{warn_joined}. Due to these political/legal uncertainties, the rating is downgraded to YELLOW (Watch)."
            )
        elif has_quant_buy:
            traffic = "GREEN"
            cause = "TEMPORARY_OVERREACTION"
            summary = (
                f"{metrics.name} ({metrics.ticker}) weist mit {metrics.upside_pct:.1f}% Kurspotenzial zum Analysten-Konsensziel "
                f"({metrics.target_mean_price} {metrics.currency}, {metrics.number_of_analyst_opinions} Analysten: {metrics.recommendation_key.upper()}) "
                f"eine klare Unterbewertung auf. In den {len(articles)} geprüften Nachrichtenquellen wurden keine akuten Spionage-, Ermittlungs- oder Restriktions-Skandale gefunden."
                if is_de
                else f"{metrics.name} ({metrics.ticker}) shows a clear {metrics.upside_pct:.1f}% upside to the analyst consensus target "
                f"({metrics.target_mean_price} {metrics.currency}, {metrics.number_of_analyst_opinions} analysts: {metrics.recommendation_key.upper()}). "
                f"Across {len(articles)} inspected news sources, no acute espionage, investigation, or restriction scandals were detected."
            )
        elif metrics.upside_pct < 0 or metrics.recommendation_key in ("sell", "underperform", "strong_sell"):
            traffic = "RED"
            cause = "STRUCTURAL_PROBLEM"
            summary = (
                f"{metrics.name} ({metrics.ticker}) notiert über oder nahe dem durchschnittlichen Analystenziel "
                f"(Upside: {metrics.upside_pct:.1f}%, Konsens: {metrics.recommendation_key.upper()}). Ungünstiges Chancen-Risiko-Verhältnis."
                if is_de
                else f"{metrics.name} ({metrics.ticker}) trades above or near the mean analyst target "
                f"(Upside: {metrics.upside_pct:.1f}%, Consensus: {metrics.recommendation_key.upper()}). Unfavorable risk/reward."
            )
        else:
            traffic = "YELLOW"
            cause = "NEUTRAL_OR_FAIRLY_VALUED"
            summary = (
                f"{metrics.name} ({metrics.ticker}) bietet aktuell ein moderates Upside von {metrics.upside_pct:.1f}% "
                f"bei einem Konsens von '{metrics.recommendation_key.upper()}' ({metrics.number_of_analyst_opinions} Analysten). Halten/Beobachten empfohlen."
                if is_de
                else f"{metrics.name} ({metrics.ticker}) currently offers a moderate upside of {metrics.upside_pct:.1f}% "
                f"with '{metrics.recommendation_key.upper()}' consensus ({metrics.number_of_analyst_opinions} analysts). Hold/Watch recommended."
            )

        return AIAnalysisResult(
            traffic_light=traffic,  # type: ignore[arg-type]
            movement_cause=cause,  # type: ignore[arg-type]
            summary=summary,
            catalysts=catalysts,
            risks=risks,
            cited_urls=priority_urls,
        )

    def evaluate_sentinel_move(
        self,
        ticker: str,
        company_name: str,
        daily_change_pct: float,
        thesis: Optional[ThesisRecord],
        articles_24h: List[NewsArticle],
        language: str = "de",
    ) -> SentinelLLMOutput:
        """
        Compare a >= +/-5% daily price move and 24-hour news against the investor's stored buy thesis.
        Classifies the thesis as CONFIRMED, BROKEN, or UNTOUCHED.
        """
        lang_name = "German (Deutsch)" if language.lower().startswith("de") else "English"
        thesis_text = (
            f"Summary: {thesis.thesis_summary}\nCatalysts: {', '.join(thesis.catalysts)}\nRisks: {', '.join(thesis.risks)}"
            if thesis
            else "No explicit saved buy thesis on file; evaluate general long-term fundamental intactness."
        )

        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                articles_text = "\n\n".join(
                    f"[{idx}] Title: {art.title}\nSource: {art.source} ({art.published_at})\nURL: {art.url}\nSnippet: {art.snippet}"
                    for idx, art in enumerate(articles_24h, start=1)
                )

                prompt = (
                    f"You are a Forensic Portfolio Risk Sentinel monitoring {company_name} ({ticker}), which moved {daily_change_pct:+.2f}% today.\n\n"
                    f"Original Saved Buy Thesis:\n{thesis_text}\n\n"
                    f"Last 24-Hour News Articles (ONLY cite URLs from this list):\n{articles_text}\n\n"
                    f"Classify the impact of today's news on the original buy thesis:\n"
                    f"- CONFIRMED: Expected positive catalyst materialized.\n"
                    f"- BROKEN: Core fundamental premise invalidated, or acute scandal/espionage/probe/export restriction hit.\n"
                    f"- UNTOUCHED: General market noise or macro swing unrelated to the core thesis.\n"
                    f"Respond in {lang_name} and cite ONLY exact URLs from the provided 24h articles."
                )

                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SentinelLLMOutput,
                        temperature=0.1,
                    ),
                )
                parsed = SentinelLLMOutput.model_validate_json(response.text)
                parsed.cited_urls = filter_verified_urls(parsed.cited_urls, articles_24h)
                return parsed
            except Exception as exc:
                logger.warning("Gemini Sentinel call failed for %s (%s); using local intelligence fallback.", ticker, exc)

        return self._fallback_sentinel(
            ticker=ticker,
            company_name=company_name,
            daily_change_pct=daily_change_pct,
            thesis=thesis,
            articles_24h=articles_24h,
            language=language,
        )

    def _fallback_sentinel(
        self,
        ticker: str,
        company_name: str,
        daily_change_pct: float,
        thesis: Optional[ThesisRecord],
        articles_24h: List[NewsArticle],
        language: str = "de",
    ) -> SentinelLLMOutput:
        """Local News Risk Intelligence evaluation for the 24h Daily Sentinel."""
        intel = extract_news_intelligence(articles_24h)
        verified_urls = filter_verified_urls(
            [a.url for a in (intel.scandal_articles + intel.political_articles + articles_24h)],
            articles_24h,
        )
        is_de = language.lower().startswith("de")

        if daily_change_pct <= -5.0 and (intel.scandal_articles or intel.political_articles or daily_change_pct <= -8.0):
            status = "BROKEN"
            top_reasons = [
                _clean_headline(a.title)
                for a in (intel.scandal_articles[:2] + intel.political_articles[:2])
            ]
            reason_detail = f" Erkannte Risikotreiber: {' | '.join(top_reasons)}." if top_reasons else ""
            reasoning = (
                f"Deutlicher Kursrückgang von {daily_change_pct:+.2f}% bei {company_name} ({ticker}).{reason_detail} "
                f"Prüfe anhand der verlinkten 24h-Quellen, ob die Kauf-These durch Ermittlungen, Spionage-Vorwürfe oder Restriktionen gebrochen ist."
                if is_de
                else f"Sharp drop of {daily_change_pct:+.2f}% in {company_name} ({ticker}).{reason_detail} "
                f"Verify via the linked 24h sources whether investigations, espionage affairs, or restrictions broke the core thesis."
            )
            action = (
                "Sofortige Fundamentalprüfung anhand der 24h-News; bei gebrochener These Verkauf vor Analysten-Downgrades erwägen."
                if is_de
                else "Immediate fundamental review via 24h news; consider exiting if core thesis is broken."
            )
        elif daily_change_pct >= 5.0 and not intel.scandal_articles:
            status = "CONFIRMED"
            reasoning = (
                f"Starker Kurssprung von {daily_change_pct:+.2f}% bei {company_name} ({ticker}). "
                f"Die Bewegung spricht für das Eintreten eines positiven Katalysators der gespeicherten Kauf-These."
                if is_de
                else f"Strong positive jump of {daily_change_pct:+.2f}% in {company_name} ({ticker}). "
                f"Price action indicates a positive catalyst from the saved buy thesis is materializing."
            )
            action = (
                "Position halten / Gewinne laufen lassen, solange die fundamentale Dynamik anhält."
                if is_de
                else "Hold position and let winners run while fundamental momentum continues."
            )
        else:
            status = "UNTOUCHED"
            reasoning = (
                f"Tagesbewegung von {daily_change_pct:+.2f}% bei {company_name} ({ticker}). "
                f"Keine unmittelbaren Hinweise auf einen strukturellen Bruch der Kauf-These (Marktschwankung)."
                if is_de
                else f"Daily move of {daily_change_pct:+.2f}% in {company_name} ({ticker}). "
                f"No immediate evidence of a broken long-term thesis (market volatility)."
            )
            action = (
                "Kein Aktionismus erforderlich – ursprüngliche Kauf-These beobachten."
                if is_de
                else "No immediate action required – monitor original buy thesis."
            )

        return SentinelLLMOutput(
            status=status,  # type: ignore[arg-type]
            reasoning=reasoning,
            action_recommendation=action,
            cited_urls=verified_urls,
        )
