"""
Unit tests for AIAnalyzer anti-hallucination URL validation, forensic & political risk
detection (espionage/scandals + election/export restrictions), i18n, and theme switching.
"""

from __future__ import annotations

from typing import List

from src.models.entities import NewsArticle, StockMetrics
from src.services.ai_analyzer import AIAnalyzer, extract_news_intelligence, filter_verified_urls
from src.ui.i18n import I18nManager
from src.ui.theme_manager import THEMES, build_theme_css, get_theme


def test_anti_hallucination_url_filter_strips_invented_urls(
    sample_news_articles: List[NewsArticle],
) -> None:
    """Verify filter_verified_urls removes any URL not present in the input NewsArticle list."""
    llm_cited = [
        "https://www.reuters.com/technology/asml-euv-orders-2026",
        "https://hallucinated-fake-domain.example/fake-article-123",
    ]
    verified = filter_verified_urls(llm_cited, sample_news_articles)
    assert verified == ["https://www.reuters.com/technology/asml-euv-orders-2026"]
    assert "https://hallucinated-fake-domain.example/fake-article-123" not in verified


def test_ai_analyzer_fallback_respects_language_and_urls(
    sample_candidate_metrics: StockMetrics,
    sample_news_articles: List[NewsArticle],
) -> None:
    """Verify AIAnalyzer produces valid GREEN output when news contains no scandal or restriction risks."""
    analyzer = AIAnalyzer(api_key="")  # Force deterministic local intelligence mode

    res_de = analyzer.analyze_monthly_deep_dive(
        metrics=sample_candidate_metrics,
        articles=sample_news_articles,
        language="de",
    )
    assert res_de.traffic_light == "GREEN"
    assert res_de.movement_cause == "TEMPORARY_OVERREACTION"
    assert len(res_de.cited_urls) == 2
    assert "Kurspotenzial" in res_de.summary

    res_en = analyzer.analyze_monthly_deep_dive(
        metrics=sample_candidate_metrics,
        articles=sample_news_articles,
        language="en",
    )
    assert res_en.traffic_light == "GREEN"
    assert "upside" in res_en.summary.lower()


def test_forensic_risk_detector_downgrades_nvidia_on_espionage_and_restrictions() -> None:
    """
    Verify that even when a stock (e.g. NVDA) has Strong Buy + >25% analyst upside,
    news about an espionage affair and post-election export restrictions downgrades
    the traffic light to RED/YELLOW and surfaces the exact risks.
    """
    nvda_metrics = StockMetrics(
        ticker="NVDA",
        name="NVIDIA Corp.",
        current_price=138.2,
        target_mean_price=175.0,
        upside_pct=26.6,
        recommendation_key="strong_buy",
        number_of_analyst_opinions=54,
        currency="USD",
        assigned_sector="Halbleiter & Hardware",
        assigned_country="USA",
    )
    risk_articles = [
        NewsArticle(
            title="[RISIKO/SKANDAL] Nvidia in Spionageaffäre und Chip-Schmuggel-Ermittlung verwickelt",
            url="https://news.example.com/nvidia-espionage-probe",
            source="Handelsblatt",
            published_at="2026-11-20",
            snippet="US-Behörden untersuchen mögliche Spionageaffäre und SEC-Bilanzprüfung bei Nvidia.",
        ),
        NewsArticle(
            title="[POLITIK/RESTRIKTION] Schärfere Export-Restriktionen für KI-Chips nach Wahlsieg der Demokraten erwartet",
            url="https://news.example.com/nvidia-export-restrictions-election",
            source="Reuters",
            published_at="2026-11-19",
            snippet="Nach dem Wahlsieg der Demokraten drohen strengere China-Exportkontrollen für Halbleiter.",
        ),
    ]

    intel = extract_news_intelligence(risk_articles)
    assert len(intel.scandal_articles) == 1
    assert len(intel.political_articles) == 1

    analyzer = AIAnalyzer(api_key="")
    result = analyzer.analyze_monthly_deep_dive(nvda_metrics, risk_articles, language="de")

    assert result.traffic_light == "RED"
    assert result.movement_cause == "STRUCTURAL_PROBLEM"
    assert "Spionageaffäre" in result.summary
    assert "Restriktionen" in result.summary
    assert any("Spionageaffäre" in r for r in result.risks)
    assert any("Wahlsieg der Demokraten" in r for r in result.risks)
    assert "https://news.example.com/nvidia-espionage-probe" in result.cited_urls
    assert "https://news.example.com/nvidia-export-restrictions-election" in result.cited_urls


def test_i18n_and_theme_switching() -> None:
    """Verify German/English language switching and Clean Blue / Pink Unicorn theme configs."""
    i18n = I18nManager(lang="de")
    assert "de" in i18n.available_languages()
    assert "en" in i18n.available_languages()
    de_title = i18n.t("tab_portfolio")

    i18n.set_language("en")
    en_title = i18n.t("tab_portfolio")
    assert de_title != en_title

    blue_theme = get_theme("clean_blue")
    unicorn_theme = get_theme("pink_unicorn")
    assert "clean_blue" in THEMES and "pink_unicorn" in THEMES
    assert blue_theme.primary_color != unicorn_theme.primary_color
    css = build_theme_css(unicorn_theme)
    assert unicorn_theme.bg_color in css
