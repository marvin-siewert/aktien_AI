"""
Extensible Color Theme Manager for Streamlit CSS and Plotly Charts.

Includes two built-in themes out of the box (as specified in GEMINI.md):
1. 'clean_blue': Clean professional design with white background and crisp blue accents.
2. 'pink_unicorn': Playful pink unicorn theme with pastel gradients, rounded cards, and unicorn flair.

New themes can be added simply by registering another `ThemeConfig` in `THEMES`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ThemeConfig:
    """Visual styling tokens for both Streamlit HTML/CSS and Plotly chart templates."""

    key: str
    display_name: str
    icon: str
    bg_color: str
    secondary_bg_color: str
    card_bg_color: str
    text_color: str
    primary_color: str
    accent_color: str
    border_color: str
    border_radius: str
    font_family: str
    plotly_template: str
    color_sequence: List[str] = field(default_factory=list)
    positive_color: str = "#16A34A"
    warning_color: str = "#D97706"
    danger_color: str = "#DC2626"
    header_banner_gradient: str = ""


THEMES: Dict[str, ThemeConfig] = {
    "clean_blue": ThemeConfig(
        key="clean_blue",
        display_name="Clean Blue & White",
        icon="💠",
        bg_color="#FFFFFF",
        secondary_bg_color="#F4F8FD",
        card_bg_color="#F8FBFF",
        text_color="#0F2942",
        primary_color="#0052CC",
        accent_color="#2684FF",
        border_color="#D0E1F9",
        border_radius="8px",
        font_family="'Inter', 'Segoe UI', sans-serif",
        plotly_template="plotly_white",
        color_sequence=[
            "#0052CC",  # 1. Royal Blue
            "#E65100",  # 2. Deep Orange
            "#2E7D32",  # 3. Forest Green
            "#8E24AA",  # 4. Rich Purple
            "#C62828",  # 5. Crimson Red
            "#00838F",  # 6. Dark Cyan / Teal
            "#F9A825",  # 7. Golden Amber
            "#AD1457",  # 8. Magenta / Berry
            "#558B2F",  # 9. Olive / Lime Green
            "#283593",  # 10. Indigo Navy
            "#6D4C41",  # 11. Warm Brown / Terracotta
            "#00ACC1",  # 12. Bright Turquoise
            "#546E7A",  # 13. Slate Grey (Sonstige)
            "#D84315",  # 14. Rust Coral
            "#4527A0",  # 15. Deep Violet
            "#00695C",  # 16. Pine Teal
        ],
        positive_color="#15803D",
        warning_color="#B45309",
        danger_color="#B91C1C",
        header_banner_gradient="linear-gradient(135deg, #0052CC 0%, #2684FF 100%)",
    ),
    "pink_unicorn": ThemeConfig(
        key="pink_unicorn",
        display_name="Pink Unicorn 🦄",
        icon="🦄",
        bg_color="#FFF5FA",
        secondary_bg_color="#FFE8F5",
        card_bg_color="#FFF0F8",
        text_color="#5A1846",
        primary_color="#FF3399",
        accent_color="#B565F7",
        border_color="#FFB3D9",
        border_radius="20px",
        font_family="'Comic Sans MS', 'Quicksand', 'Trebuchet MS', cursive, sans-serif",
        plotly_template="plotly_white",
        color_sequence=[
            "#FF1493",  # 1. Deep Pink
            "#7C3AED",  # 2. Vibrant Violet
            "#0EA5E9",  # 3. Sky Cyan
            "#10B981",  # 4. Mint Emerald
            "#F59E0B",  # 5. Sunny Amber
            "#EF4444",  # 6. Coral Red
            "#3B82F6",  # 7. Electric Blue
            "#84CC16",  # 8. Bright Lime
            "#D946EF",  # 9. Orchid Magenta
            "#14B8A6",  # 10. Aqua Teal
            "#F97316",  # 11. Tangerine Orange
            "#6366F1",  # 12. Periwinkle Indigo
            "#8B5CF6",  # 13. Lavender Purple
            "#EC4899",  # 14. Rose Pink
            "#06B6D4",  # 15. Turquoise
            "#64748B",  # 16. Cool Slate
        ],
        positive_color="#10B981",
        warning_color="#F59E0B",
        danger_color="#F43F5E",
        header_banner_gradient="linear-gradient(135deg, #FF66B2 0%, #B565F7 50%, #66D9E8 100%)",
    ),
}


def get_theme(theme_key: str) -> ThemeConfig:
    """Return the requested ThemeConfig or fall back to 'clean_blue'."""
    return THEMES.get(theme_key, THEMES["clean_blue"])


def build_theme_css(theme: ThemeConfig) -> str:
    """Generate dynamic CSS string to style the Streamlit app according to the selected theme."""
    return f"""
    <style>
        .stApp {{
            background-color: {theme.bg_color};
            color: {theme.text_color};
            font-family: {theme.font_family};
        }}
        [data-testid="stSidebar"] {{
            background-color: {theme.secondary_bg_color};
            border-right: 1px solid {theme.border_color};
        }}
        .theme-banner {{
            background: {theme.header_banner_gradient};
            color: #FFFFFF;
            padding: 1.1rem 1.5rem;
            border-radius: {theme.border_radius};
            margin-bottom: 1.2rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }}
        .theme-banner h1 {{
            color: #FFFFFF !important;
            margin: 0;
            font-size: 1.75rem;
            font-weight: 700;
        }}
        .theme-banner p {{
            color: rgba(255, 255, 255, 0.92) !important;
            margin: 0.3rem 0 0 0;
            font-size: 0.98rem;
        }}
        .theme-card {{
            background-color: {theme.card_bg_color};
            border: 2px solid {theme.border_color};
            border-radius: {theme.border_radius};
            padding: 1rem 1.25rem;
            margin-bottom: 0.9rem;
        }}
        div[data-testid="stMetric"] {{
            background-color: {theme.card_bg_color};
            border: 1.5px solid {theme.border_color};
            border-radius: {theme.border_radius};
            padding: 0.8rem 1rem;
        }}
        div.stButton > button {{
            border-radius: {theme.border_radius};
            border: 1.5px solid {theme.primary_color};
            font-weight: 600;
        }}
    </style>
    """
