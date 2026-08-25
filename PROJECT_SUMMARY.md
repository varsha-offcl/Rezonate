# Project Summary — Autonomous Self-Learning System for Optimizing Renewable Energy

_Last updated: 2026-08-13_

---

## 1. Project Overview

This is a full-stack capstone project that builds an **autonomous self-learning system for optimizing renewable energy** in a simulated grid-connected microgrid. The system combines machine learning forecasting, metaheuristic optimization (Genetic Algorithm + Particle Swarm Optimization), and a live interactive React dashboard.

The microgrid comprises:
- **PV solar array** (450 kW nameplate)
- **Wind turbine** (250 kW nameplate)
- **Battery storage** (300 kWh LFP, 100 kW max power, 90% round-trip efficiency)
- **Local load** (120 kW peak)
- **Bidirectional grid connection** (import/export)

The objective is to **minimise total daily operating cost** (import cost − export revenue + battery degradation) while respecting physical constraints (SOC 20–90%, power limits, energy balance).

---

## 2. System Architecture

| Component | Cadence | Function |
|---|---|---|
| TFT Forecaster | Once daily (18:00) | 24h-ahead forecasts of solar, wind, and load from 168h lookback |
| GA Scheduler | Once daily (18:30) | Day-ahead battery dispatch schedule (pop=100, 200 generations) |
| PSO Refiner | Every 15 min | Re-tunes setpoints within ±50% trust region of GA solution |
| Feedback Loop | Continuous | Logs actuals, monitors forecast drift, warm-starts next GA run |
| React Dashboard | On demand | Visualises forecasts, schedules, results, and interactive tools |
| FastAPI Backend | On demand | Live weather forecasts, what-if scenarios, chat-based optimizer |

This is a **memetic algorithm** — combining population-based global search (GA) with local refinement (PSO), operating at different timescales.

---

## 3. Technology Stack

### Backend (Python 3.11)
| Library | Purpose |
|---|---|
| FastAPI + uvicorn | REST API backend |
| DEAP | Genetic Algorithm implementation |
| PyTorch + Lightning | TFT and LSTM neural networks |
| LightGBM, statsmodels | Baseline forecasters |
| PuLP + CBC | MILP oracle (optimal ceiling benchmark) |
| rainflow | Battery cycle degradation counting |
| NumPy, Pandas, SciPy | Data handling and computation |
| Groq API (LLaMA 3.3 70B) | LLM-powered chat responses (optional) |
| Open-Meteo API | Free weather forecasts (no key needed) |

### Frontend
| Library | Purpose |
|---|---|
| React 19 + Vite 8 | UI framework and build tool |
| Tailwind CSS 3 | Styling with custom design tokens (light/dark themes) |
| Recharts | All charts (dispatch, SOC, convergence, weather, etc.) |
| Lucide | Icon set |

---

## 4. Project Phases (All Complete)

### Phase 1–2: Data Pipeline & Forecasting
- **Data source**: Open Power System Data (Germany) — national solar/wind/load/price, rescaled to microgrid scale
- **Baselines**: Persistence, LightGBM, statsmodels
- **Advanced**: Temporal Fusion Transformer (TFT) with quantile bands (P10/P50/P90) + LSTM comparison
- **Data cleaning**: DST handling, gap filling, bidding-zone-split gap fix (see `data/NOTES.md`)

### Phase 3: Battery & Environment Model
- **Battery physics** (`src/env/battery.py`): SOC trajectory, rainflow degradation cost, LFP cycle-life fit (a=3059, b=1.197)
- **Objective function** (`src/env/objective.py`): import cost − export revenue + degradation + constraint penalties
- **Simulator** (`src/env/simulator.py`): Scenario dataclass, national data rescaled to microgrid nameplate
- **Rule-based baseline** (`src/optimization/rule_based.py`): Simple charge-when-surplus, discharge-when-deficit
- **MILP oracle** (`src/optimization/milp_oracle.py`): Perfect-foresight optimal solution (ceiling benchmark)

### Phase 4: Genetic Algorithm
- **File**: `src/optimization/ga_scheduler.py`
- **Chromosome**: 24 magnitudes (kW) + 24 direction flags (charge/discharge)
- **Operators**: SBX crossover (η=15), polynomial mutation (η=20), elitist selection (top 5 preserved)
- **Config**: Population 100, 200 generations, tournament size 3

### Phase 5: PSO Refiner
- **File**: `src/optimization/pso_refiner.py`
- **Trust region**: ±50% of max power around GA setpoints (calibrated via sweep — ±10% under-corrects, unbounded over-corrects)
- **Runs**: Every 15 minutes, 96 times per day

### Phase 6: Self-Learning Loop
- **Closed loop** (`src/optimization/closed_loop.py`): Warm-starting + self-adaptive mutation
- **Drift detection** (`src/forecasting/drift.py`): Monitors forecast error stationarity (honest negative — 0 triggers in test season)

### Phase 7: Ablation & Results
- **Ablation grid** (`src/eval/ablation.py`): Every configuration benchmarked against MILP oracle
- **Headline result**: GA→PSO (TFT forecast) captures **81.0%** of achievable saving vs oracle
  - Rule-based floor: 79.9%
  - GA alone: 50.7%
  - PSO alone: −135.4% (confirms PSO needs GA's starting point)
- **Key finding**: PSO trust-region width recalibrated from ±10% to ±50% of max power

### Phase 7.5: Dashboard Redesign
- CSS custom-property tokens (light/dark themes)
- 5-tab stage rail: Today → Forecast → Day-ahead Schedule → Live Ops → Results
- Season replay scrubber, headline stat treatment, chart palette alignment

### Phase 8a: Interactive What-If Panel
- **Solar slider**: ±50% solar output adjustment
- **Battery slider**: 50–1000 kWh capacity
- Re-runs actual GA on slider change, not a lookup

### Phase 8b: Explanation Layer
- **File**: `src/explain/decision_facts.py`
- Extracts charge/discharge windows from schedule, computes verified facts (surplus/deficit, price context)
- `render_template()`: Deterministic plain-language explanation
- **Future-tense aware**: Detects future dates and uses "will store", "is predicted to", etc.
- Optional LLM rephrasing via Groq (same facts, natural prose)

---

## 5. API Endpoints (`src/api.py`)

| Endpoint | Method | Description |
|---|---|---|
| `/today` | GET | Live weather forecast → GA optimization → predicted battery schedule. **Supports date picker** — any date up to 14 days ahead via `?date=YYYY-MM-DD` parameter. Uses Open-Meteo multi-day forecasts. |
| `/whatif` | POST | Re-runs GA with adjusted solar % and battery capacity from slider inputs |
| `/explain` | POST | Plain-language explanation of optimizer decisions (LLM or template fallback) |
| `/chat` | POST | **Structured optimizer** — accepts exact numeric inputs (solar_kw, wind_kw, load_kw, price_per_kwh, battery_kwh, soc_pct). Uses **flat 24h profiles** (no bell curves, no TOU shaping, no hidden import adder). Custom evaluator bypasses `IMPORT_ADDER_EUR_MWH`. |
| `/ask` | POST | Follow-up questions about optimization results. Sends question + last optimization context to Groq LLM, or uses deterministic keyword-matched fallback. |
| `/health` | GET | Server status check |

### Key Design Decision: Flat vs Shaped Profiles
The `/chat` endpoint uses `_build_flat_scenario()` and `_evaluate_flat()` — when a user says "solar 520 kW", every hour gets exactly 520 kW. No TOU_SHAPE multiplication on prices, no solar bell curve, no wind variation. The user's price is the actual import price with no hidden `IMPORT_ADDER_EUR_MWH` (+€150/MWh) added on top. This was a deliberate fix after the user identified that shaped profiles were corrupting their inputs.

The `/today` endpoint still uses realistic daily shapes (TOU pricing, weather-driven solar/wind curves, temperature-adjusted load) because it's working with real forecast data, not user-specified constants.

---

## 6. Frontend Components (`frontend/src/`)

### Main App (`App.jsx`)
- 5-tab navigation: Today, Forecast, Day-ahead Schedule, Live Ops, Results
- Location picker (defaults to Berlin, Germany)
- Light/dark theme toggle
- Floating ChatBox overlay

### Tab: Today (`TodayTab.jsx`)
- **Date picker**: Select any date from today to 14 days ahead
- Fetches Open-Meteo weather forecast for selected date
- Runs GA optimizer on forecast data
- Shows: cost comparison (no battery vs rule-based vs GA), weather charts, dispatch chart, SOC chart, GA convergence, plain-language explanation
- Past/forecast visual split (solid = elapsed hours, faded = forecast) — for future dates everything is forecast

### Tab: Forecast (`ForecastChart.jsx`, `MetricsTable.jsx`, `VariableImportance.jsx`)
- TFT forecast visualization with P10/P50/P90 uncertainty bands
- Forecast accuracy metrics table
- Variable importance from TFT attention weights

### Tab: Day-ahead Schedule (`ConvergenceChart.jsx`, `ScheduleChart.jsx`)
- GA convergence curve (cost vs generation)
- Resulting battery dispatch schedule

### Tab: Live Ops
- `DispatchChart.jsx` — Battery dispatch over the season
- `SocChart.jsx` — State of charge trajectory
- `PsoOverlayChart.jsx` — PSO corrections overlaid on GA schedule
- `SeasonReplay.jsx` — Week-by-week season scrubber
- `SelfLearningChart.jsx` — Warm-start and adaptive mutation metrics
- `DriftChart.jsx` — Forecast drift detection results
- `ExplanationCard.jsx` — Why-this-decision explanation
- `WhatIfPanel.jsx` — Interactive solar/battery sliders
- `WeekPicker.jsx` — Navigate season weeks

### Tab: Results (`HeadlineStat.jsx`, `AblationTable.jsx`, `DataOverview.jsx`)
- Headline: 81.0% oracle capture
- Full ablation grid comparing all configurations
- Data overview and quality stats

### Floating Overlay: ChatBox (`ChatBox.jsx`)
- **Structured input form**: Solar kW, Wind kW, Demand kW, Price $/kWh, Battery kWh, SOC %
- **Quick presets**: Sunny Day, Windy Night, High Demand
- **Results card**: Daily cost, savings vs no battery, cost breakdown (import/export/degradation), battery schedule with charge/discharge windows
- **Follow-up chat**: After optimization, users can ask text questions about results (e.g., "why did the battery charge at 2am?", "how much does it save?")
- **Suggestion chips**: Pre-written common questions

---

## 7. Data & Configuration

### Data Files
- `data/processed/merged.parquet` — Cleaned, merged national grid data
- `frontend/public/data/*.json` — Static exports for dashboard (generated by `src/export/to_json.py`)
- `results/models/tft.ckpt`, `lstm.ckpt` — Trained model checkpoints

### Configuration
- `.env` (project root): `GROQ_API_KEY=<key>` — for LLM chat responses. Without it, chat works with deterministic fallbacks.
- `frontend/src/index.css` — CSS custom property tokens for theming
- `frontend/tailwind.config.js` — Custom color tokens, font families

### Microgrid Parameters (Defaults)
| Parameter | Value |
|---|---|
| Solar capacity | 450 kW |
| Wind capacity | 250 kW |
| Load peak | 120 kW |
| Battery capacity | 300 kWh |
| Battery max power | 100 kW (0.33C) |
| Round-trip efficiency | 90% (√0.9 each way) |
| SOC bounds | 20%–90% |
| Initial SOC | 55% |
| Capital cost | €75,000 (€250/kWh) |
| Import price adder | €150/MWh (over wholesale, for `/today` endpoint only) |

---

## 8. How to Run

```bash
# 1. Backend (from project root)
cd "C:\work\capstone upd\capstone_handoff"
.venv\Scripts\activate
python -m uvicorn src.api:app --port 8000

# 2. Frontend (separate terminal)
cd frontend
npm install    # first time only
npm run dev    # http://localhost:5173 (or 5174/5175 if port taken)

# 3. Regenerate dashboard data (if backend models change)
python -m src.export.to_json

# 4. Re-run ablation (takes ~8 min)
python -m src.eval.ablation
```

### Windows Notes
- Python packages pinned to specific versions due to Windows Application Control policy (see README.md)
- `.venv/` is machine-specific — always recreate locally, never copy
- To kill a stuck server: `Get-NetTCPConnection -LocalPort 8000 | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }`

---

## 9. Known Bugs Fixed

1. **Rule-based sign error** — was charging/discharging backwards (fixed in `rule_based.py`)
2. **Terminal SOC exploit** — ending surplus credited at import price instead of export (fixed in `objective.py`)
3. **Battery value misparse** — regex matched wrong number from message (fixed with label prefix requirement)
4. **Solar parsed as percentage** — regex matched "50%" from pasted output (fixed with output stripping)
5. **Price unit not recognized** — added $/kWh → €/MWh conversion
6. **Input values corrupted by shaping** — TOU_SHAPE, bell curves, import adder applied to user inputs (fixed with flat scenario builder)
7. **Future date NaN crash** — Open-Meteo returns NaN at forecast boundary (fixed with safe float handling)
8. **Past tense for future predictions** — explanation used "the battery made" for future dates (fixed with future-tense detection)

---

## 10. Other Documentation

| File | Contents |
|---|---|
| `README.md` | Setup instructions, repo layout |
| `HANDOFF.md` | Session handoff notes, what's done/not done, how to run |
| `Project_Plan_1.md` | Master plan with phase specs, §12.1 has real results |
| `CHARTS.md` | What each dashboard chart shows and how to read it |
| `TODO_PHASE2.md` | GPU training instructions for TFT/LSTM |
| `data/NOTES.md` | Data cleaning decisions (gaps, DST, bidding-zone split) |
