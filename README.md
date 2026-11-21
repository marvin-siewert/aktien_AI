# Modular Stock Analysis & Portfolio Monitoring System (`aktien_AI`)

A modular, local-first stock analysis, diversification, and portfolio monitoring system for retail investors built with Python, Streamlit, Plotly, `yfinance`, and Google Gemini (`google-genai`).

---

## Key Features

1. **Equal-Ranking Portfolio Management (No Broker Lock-In):**
   - **Manual Entry & Live Table Editor:** Add positions via Quick-Add (auto-completes name, live price, currency, sector, and country via `yfinance`) or edit inline in an Excel-like data table.
   - **Save & Restore Portfolio Snapshots:** Save any portfolio state under a custom name (`data/portfolio_saved/`) and restore or compare states anytime.
   - **Direct Broker & Bank Imports:** Import holdings via the official **Scalable Capital CLI** (`sc broker holdings --json` in read-only mode), **Universal Bank/Broker CSV upload** (Scalable, Trade Republic, ING, Comdirect, Portfolio Performance, Parqet), or load the curated **Demo Portfolio**.
2. **Customizable Sector & Country Taxonomy with Version History:**
   - Automatic mapping of `yfinance` sector/industry/country metadata to a clean 13-sector and 12-country taxonomy (separating *Technology & Software* from *Semiconductors & Hardware*).
   - Manual per-stock overrides for sector and country.
   - Full editor in the Settings tab with timestamped version snapshots (`data/taxonomy_history/`) to save and restore historical lists.
3. **Monthly Deep Dive (Sunk-Cost-Free Re-Evaluation & Screener):**
   - Re-evaluates existing holdings objectively without buy-in price anchoring.
   - Screens DAX 40, S&P 500, and custom watchlists in **Quick-Scan** (< 30s) or **Full-Scan** (~540 stocks with 24h local cache) mode.
   - Enforces anti-cluster-risk rules: max. 5% position size (20–25 stocks target) and max. 3 stocks / 15–20% weight per sector.
   - Retrieves 30-day news with real URLs (Tavily API or DuckDuckGo fallback) and uses Google Gemini Structured Outputs to distinguish temporary market overreactions from structural problems.
   - One-click saving of AI buy theses into `data/portfolio_thesis.json`.
4. **Daily Sentinel (`daily_sentinel.py` & UI Tab):**
   - Monitors portfolio holdings for unusual daily moves (default: `> +5%` or `< -5%`).
   - Fetches 24-hour news only for triggered positions and verifies the stored buy thesis via LLM (`CONFIRMED`, `BROKEN`, or `UNTOUCHED`).
5. **Bilingual UI (DE / EN) & Switchable Themes:**
   - Instant language switch between **German** and **English** (extensible via `locales/<lang>.json`).
   - Instant theme switch between **Clean Blue & White** and **Pink Unicorn 🦄** (extensible in `src/ui/theme_manager.py`).

---

## Environment Setup (`aktien_ai_env`)

### Option 1: Using Conda (`requirements.yml`)
```bash
conda env create -f requirements.yml
conda activate aktien_ai_env
```

### Option 2: Using `venv` and `pip` (`requirements.txt`)
```bash
python -m venv aktien_ai_env
# Windows PowerShell:
.\aktien_ai_env\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Configuration (`.env`)
Copy `.env.example` to `.env` and add your API keys:
```bash
cp .env.example .env
```
*(Note: The app works out-of-the-box even without API keys using rule-based AI fallback and DuckDuckGo news fallback.)*

---

## Running the Application & Tests

### Start the Interactive Streamlit Dashboard
```bash
streamlit run app.py
```

### Run the Standalone Daily Sentinel CLI
```bash
python daily_sentinel.py --threshold 5.0
```

### Run the Unit Test Suite
```bash
pytest -v
```
