# Gojira Investment System - Design Spec

## Context

Based on a comprehensive Chinese value investing theory framework (resource.txt), this system provides a personal desktop tool to systematically apply the theory's analytical methods, valuation tools, portfolio rules, and psychological discipline to real-world stock investing decisions. The goal is to turn a rich but informal body of investment knowledge into a structured, repeatable workflow.

**Target user**: Personal use (single user, local deployment)
**Tech stack**: FastAPI (Python) + React + SQLite
**Data sources**: AKShare/Tushare APIs + manual CSV import

## Architecture

```
gojira/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── db/                  # SQLAlchemy models + SQLite
│   │   ├── services/            # Business logic (analysis, valuation, portfolio, discipline)
│   │   ├── routers/             # API endpoints per module
│   │   └── schemas/             # Pydantic request/response models
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # One page per module
│   │   ├── components/          # Reusable charts, tables, forms
│   │   └── api/                 # Typed API client
│   └── package.json
└── data/
    ├── gojira.db                # SQLite database file
    └── imports/                 # CSV import staging directory
```

**Key decisions:**
- SQLite for zero-config local storage; no database server needed
- SQLAlchemy ORM for type-safe database access
- Pydantic for API validation and serialization
- React with a lightweight UI library (Ant Design or MUI) for rapid UI development
- Charting via Recharts or ECharts

## Data Model (Core Entities)

### Stock
- `code` (str, PK) — e.g., "600519"
- `name` (str)
- `industry` (str) — mapped to industry framework template
- `qiu_score` (int 0-3) — "求" business model score
- `notes` (text)

### AnalysisReport
- `id` (int, PK)
- `stock_code` (FK → Stock)
- `created_at` (datetime)
- `top_design_notes` (text) — 顶层设计 analysis
- `top_design_theme` (str) — e.g., "能源安全→煤制烯烃"
- `first_principle_variable` (str) — key variable identified
- `business_model_notes` (text) — 商业模式 analysis
- `qiu_upstream` (bool) — upstream seeks company?
- `qiu_downstream` (bool) — downstream seeks company?
- `qiu_government` (bool) — government seeks company?
- `financial_notes` (text) — 财务分析 notes
- `cash_flow_vs_profit` (text) — operating cash flow vs net profit observation
- `conclusion` (text)

### ValuationSnapshot
- `id` (int, PK)
- `stock_code` (FK → Stock)
- `date` (date)
- `pe_ttm` (float)
- `pb` (float)
- `pe_percentile_10y` (float) — where current PE sits in 10-year range
- `pb_percentile_10y` (float)
- `dividend_yield` (float)
- `eps` (float)
- `eps_calculated` (float) — manually calculated per theory formula
- `eps_discrepancy_reason` (text)
- `operating_cash_flow` (float)
- `net_profit` (float)
- `dividends_paid` (float)
- `payout_ratio` (float)
- `projected_eps_next` (float)
- `projected_dividend_next` (float)

### Holding
- `id` (int, PK)
- `stock_code` (FK → Stock)
- `buy_date` (date)
- `buy_price` (float)
- `quantity` (int)
- `sell_date` (date, nullable)
- `sell_price` (float, nullable)
- `stop_profit_price` (float) — 30% above buy price by default
- `trade_rationale` (text) — why bought
- `sell_thesis` (text) — what would trigger a sell

### DividendRecord
- `id` (int, PK)
- `stock_code` (FK → Stock)
- `ex_date` (date)
- `amount_per_share` (float)
- `quantity_held` (int)
- `total_received` (float)
- `reinvested` (bool)

### JournalEntry
- `id` (int, PK)
- `date` (date)
- `emotional_state` (str) — calm/anxious/fomo/greedy/fearful
- `research_notes` (text)
- `impulse_trades` (text) — trades I want to make but will decide tomorrow
- `reflection` (text)

### DisciplineCheck
- `id` (int, PK)
- `date` (date)
- `check_type` (str) — "pre_trade" / "illusion_test" / "pitfall_review"
- `stock_code` (str, nullable)
- `responses` (JSON) — structured answers to checklist questions
- `score` (int) — pass/fail or numeric score
- `action_taken` (str) — what the user decided to do

## Module 1: Stock Analysis Framework

### 1.1 "求" Business Model Scorer

Interactive form guiding the user through scoring a company's business model on a 0-3 scale:

- **上游 (Upstream)**: Do suppliers seek the company? (e.g., raw material providers compete to supply)
- **下游 (Downstream)**: Do customers seek the company's products? (e.g., consumers queue to buy)
- **政府 (Government)**: Does the local government want to keep the company? (tax revenue, employment)

Each dimension includes theory-derived examples:
- 3求: Maotai (upstream seeks, downstream seeks, government seeks)
- 2求: Non-ferrous metals (upstream weak miners, no downstream premium, government values tax)
- 1求: Most companies (market-rate relationships with all parties, government values tax)
- 0求: Real estate (upstream = government land sales controls you, downstream buyers have power, government regulates tightly)

Output: Score card with reasoning, saved to `AnalysisReport`.

### 1.2 Top-Down Analysis Workflow

Three-step guided workflow:

**Step 1 — 顶层设计 (Top-Level Design)**:
- Identify the national theme: 安全 → which security domain? → energy/food/financial/mineral
- Trace to industry and first-principle variable
- Free-text notes field + structured theme selector
- Key question: "What is the one variable that drives this stock's value?"

**Step 2 — 商业模式 (Business Model)**:
- Apply "求" scoring
- Describe stakeholder relationships and power dynamics
- Key question: "Who has pricing power, and why?"

**Step 3 — 财务分析 (Financial Verification)**:
- Not a deep accounting exercise — verify the business model hypothesis
- Focus metrics: operating cash flow vs net profit ratio, dividend sustainability
- Key question: "Does the financial data confirm or contradict my business model assessment?"

All three steps save into `AnalysisReport`. The workflow can be saved as draft and resumed.

### 1.3 Industry Framework Templates

Pre-built analysis templates with industry-specific key variables:

| Industry | First-Principle Variable | Key Metrics |
|----------|-------------------------|-------------|
| 煤化工 | Coal price → Olefin price, capacity | Tonnage, conversion ratio, coal cost per ton |
| 铝业 | Electricity cost, international expansion | Power cost per ton, overseas capacity |
| 磷化工 | Ore reserves, mining cost, self-sufficiency | Ore grade (%), reserves (tons), cost per ton |
| 银行 | Dividend yield, regional economy, PB vs cash flow | 经营现金流/归母净利润, PB, NPL coverage |
| 药品零售 | Store count (franchise), closure rate, customer loyalty | Franchise store growth, net closure rate, membership |
| 黄金 | Policy shifts, demand type transition | Investment gold vs jewelry mix, policy impact |

Templates are stored as JSON config files in `backend/app/templates/industries/`. Each template contains:
- `industry_name`: display name
- `top_design_guidance`: prompt text for 顶层设计 step
- `key_variables`: list of variable names to collect (e.g., ["coal_price", "olefin_price", "capacity_tons"])
- `business_model_hints`: guidance for "求" scoring in this industry
- `financial_focus`: which financial metrics matter most
- `example_stocks`: list of example stock codes referenced in the theory

## Module 2: Valuation Tools

### 2.1 PE/PB Historical Percentile Calculator

- Input: stock code + date range (default: 10 years)
- Fetch (API or manual) daily PE/PB values
- Calculate percentile bands: 10th, 30th, 50th, 70th, 90th
- Chart: time series with colored bands showing percentile zones
- "遛狗" interpretation:
  - Below 30th percentile = dog is close to owner (undervalued)
  - Above 70th percentile = dog has run far (overvalued)
  - Current position marker

### 2.2 Dividend Yield Analyzer

- Calculate trailing 12-month dividend yield
- Project next-year dividend based on payout ratio and EPS forecast
- Three-bar comparison (multi-year): operating cash flow / net profit / dividends paid
- Sustainability check: operating cash flow > net profit > dividends (ideal pattern)
- Alert logic:
  - If dividends > net profit: flag as "需验证" — check if cash flow supports it (the G公司 pattern)
  - If dividends > operating cash flow: flag as "不可持续" — genuinely at risk

### 2.3 EPS Calculator

- Precise calculation following the theory's formula:
  `EPS = (归母净利润 - 优先股股息 - 永续债利息) / 流通在外普通股加权平均股数`
- Input fields for each component
- Auto-calculate weighted average shares if multiple share events in the year
- Comparison: calculated EPS vs reported EPS, with discrepancy explanation
- Handles: 库存股 (treasury stock), 可转债 (convertible bonds), 增发 (rights issues)

### 2.4 Composite Valuation Dashboard

Single-page summary applying the theory's hierarchy:

1. **PE为主 (Primary)**: Current PE vs 10-year percentile, fair value estimate at 30th/50th percentile
2. **PB为辅 (Supplementary)**: PB vs historical, especially for banks/asset-heavy industries
3. **股息为先 (Floor)**: Dividend yield floor at 5% → implied minimum price
4. **增速为次 (Growth)**: Projected growth rate → PEG cross-check

Output: Buy/Sell/Hold signal based on where current price sits relative to:
- Floor: price where dividend yield = 5%
- Fair: 50th percentile PE * projected EPS
- Ceiling: 70th percentile PE * projected EPS or 30% above buy price

## Module 3: Portfolio Management

### 3.1 Holdings Tracker

- CRUD for stock holdings: buy date, price, quantity, sell date, price
- On-demand current price fetch (API)
- P&L per holding and total portfolio P&L
- Dividend income per stock and aggregate

### 3.2 Position Control & Alerts

Hard rules from the theory:
- Single stock ≤ 20% of total portfolio value (visual warning at 15%)
- Single sector ≤ 15% of total portfolio value
- Cash position always visible
- Visual: donut chart of holdings with weight labels, red border on over-concentrated positions

### 3.3 "人之道" Rebalancing Guide

- Holdings ranked by performance (best to worst)
- "Sell Weak / Buy Strong" guidance:
  - Green indicator: add to this position (performing well, fundamentals intact)
  - Yellow indicator: hold, no change
  - Red indicator: consider reducing (underperforming, thesis broken)
- Anti-pattern warning: "You're considering adding to your worst performer. The theory says: 损不足而奉有余"
- Add-position rules (from theory):
  - Minimum 10% price drop from current entry before adding
  - Fundamentals must be re-verified
  - Must not exceed 20% position limit

### 3.4 Stop-Profit & Trade Journal

- Default stop-profit at 30% gain (configurable per holding)
- Alert when stop-profit price is reached
- Trade journal attached to each holding:
  - Buy rationale (why did I buy?)
  - Sell thesis (what would make me sell?)
  - Updates over time as thesis evolves

### 3.5 Dividend Income Dashboard

- Calendar view: upcoming ex-dividend dates
- Income tracker: dividends received by month/quarter/year
- Projected annual income based on current holdings and historical payout
- "收息复投" (DRIP) tracking: reinvested dividends and resulting share counts

## Module 4: Discipline & Psychology

### 4.1 Three Illusions Self-Test

Interactive questionnaire from 地阶功法卷一:

**损失厌恶 (Loss Aversion)**:
- "Are you holding this stock only because selling would realize the loss?"
- "If you didn't already own this stock, would you buy it at today's price?"
- "Have you been holding this for over a year without reviewing the original thesis?"

**从众心理 (Herd Mentality)**:
- "Did you discover this stock through your own analysis, or did someone recommend it?"
- "Is the stock currently at a 52-week high with heavy retail buying?"
- "Can you articulate your thesis in 3 sentences without referencing what others say?"

**锚定效应 (Anchoring)**:
- "Are you evaluating this based on its previous high/low price?"
- "Can you state the stock's intrinsic value without looking at its price chart?"
- "If this stock had never traded at [previous price], would your assessment change?"

Scoring: 0-3 per illusion, saved to `DisciplineCheck` with timestamp for trend tracking.

### 4.2 Value Investing Pitfall Checker

Three traps from 地阶功法卷二, surfaced as contextual warnings:

1. **迷信财报**: Shown when user spends too long on financial detail pages without recording a business model analysis
2. **长期持有**: Shown when user hasn't reviewed a holding's thesis in >6 months, or when a holding exceeds stop-profit
3. **低估值**: Shown when user screens by low PE/PB without completing top-down analysis first

### 4.3 Investment Journal

Structured daily/weekly log:
- Research notes: what did I study today?
- Emotional state selector: calm / anxious / FOMO / greedy / fearful
- Impulse trade log: "I want to buy/sell X" — write it down, decide tomorrow
- Reflection prompt: "Does this action align with my investment principles?"

Entries saved to `JournalEntry`, browseable by date with emotional state filtering.

### 4.4 Pre-Trade Checklist

Mandatory before any buy order is recorded:

1. Top-down analysis complete (顶层设计→商业模式→财务)?
2. "求" score recorded?
3. Expected dividend yield ≥ 5%?
4. PE ≤ 20?
5. Can I hold this for 10 years? ("不打算持有十年的东西，就一秒也别持有")
6. Am I buying based on my own analysis, not FOMO?
7. Will this position stay under 20% of portfolio?
8. Have I acknowledged the specific risks for this stock?

All 8 must pass before the system allows recording the trade. If any fail, the user must provide a written justification.

## API Design (Key Endpoints)

```
# Stock Analysis
POST   /api/stocks                     # Create stock entry
GET    /api/stocks/{code}               # Get stock details
POST   /api/analysis                    # Create analysis report
GET    /api/analysis/{id}               # Get analysis report
PUT    /api/analysis/{id}               # Update (draft) analysis
GET    /api/analysis?stock_code=X       # List analyses for stock

# Valuation
GET    /api/valuation/{code}/percentile  # PE/PB percentile data
POST   /api/valuation/{code}/snapshot   # Save valuation snapshot
POST   /api/valuation/{code}/eps        # Calculate EPS
GET    /api/valuation/{code}/dashboard  # Composite valuation view

# Portfolio
POST   /api/holdings                    # Add holding
PUT    /api/holdings/{id}               # Update holding (sell, etc.)
GET    /api/holdings                    # List all holdings
GET    /api/portfolio/summary           # Portfolio summary + position alerts
GET    /api/portfolio/dividends         # Dividend income summary

# Discipline
POST   /api/discipline/check            # Save checklist/self-test result
GET    /api/discipline/checks           # List historical checks
POST   /api/journal                     # Create journal entry
GET    /api/journal                     # List journal entries

# Data
GET    /api/data/fetch/{code}           # Fetch stock data from API
POST   /api/data/import                 # Import CSV data
```

## UI Pages

1. **Dashboard** — portfolio overview, alerts, upcoming dividends
2. **Stock Analysis** — guided 3-step workflow, "求" scorer, industry templates
3. **Valuation** — percentile charts, EPS calculator, composite dashboard
4. **Portfolio** — holdings table, position chart, rebalancing guide
5. **Discipline** — pre-trade checklist, illusion self-test, journal

## Implementation Phases

### Phase 1 (Analysis + Valuation Core)
- Backend: data model, stock CRUD, analysis workflow, valuation calculations
- Frontend: analysis workflow pages, "求" scorer, PE/PB charts, EPS calculator
- Data: AKShare integration, CSV import

### Phase 2 (Portfolio + Discipline)
- Backend: holdings CRUD, position alerts, discipline checks, journal
- Frontend: portfolio dashboard, position control charts, pre-trade checklist, journal UI

## Verification

1. **Unit tests**: Each service function (valuation calculations, "求" scoring, position limit checks)
2. **Integration tests**: API endpoints with test database
3. **Manual E2E test**:
   - Create a stock, complete full top-down analysis, run valuation, record a buy with pre-trade checklist
   - Verify position alerts trigger at 20% threshold
   - Verify stop-profit alert at 30% gain
   - Run three illusions self-test, verify score saves and trends
4. **Data accuracy**: Cross-check EPS calculation and PE percentile against known values from public sources
