# Project Plan

**Autonomous Self-Learning System for Optimizing Renewable Energy**

Temporal Fusion Transformer + Genetic Algorithm + Particle Swarm Optimization

---

## 1. Overview

The system manages a grid-connected microgrid comprising a PV array, a wind turbine, battery storage, a local load, and a bidirectional grid connection. The objective is to minimise total operating cost while respecting physical and operational constraints.

This is a software project. Everything is simulated — no hardware. The deliverables are a Python repository, a React dashboard, a set of result tables and figures, and a report.

Three algorithms operate at separate timescales:

- **TFT** forecasts generation and demand 24 hours ahead.
- **GA** uses that forecast to construct a day-ahead dispatch schedule.
- **PSO** refines setpoints every 15 minutes to correct for forecast error, searching only within a narrow band around the GA schedule.

---

## 2. Architecture

| Component | Cadence | Function |
|---|---|---|
| TFT forecaster | Once daily | 24-hour-ahead forecasts of PV, wind, and load from a 168-hour lookback window |
| GA scheduler | Once daily | Day-ahead dispatch schedule across mixed integer and continuous variables |
| PSO refiner | Every 15 min | Re-tunes setpoints for the next four intervals within bounds derived from the GA solution |
| Feedback loop | Continuous | Logs actuals, monitors forecast drift, triggers retraining, warm-starts the next GA run |
| React dashboard | On demand | Reads exported JSON; visualises forecasts, schedules, and results |

### A day in operation

- **18:00 previous day** — TFT takes the last 168 hours and outputs a 24-hour forecast.
- **18:30** — GA searches for tomorrow's schedule. Population 100, 200 generations.
- **10:00 next morning** — actual PV falls below forecast. PSO searches the next four 15-minute intervals within ±10% of the GA setpoints, converging in roughly two seconds.
- **Every 15 minutes** — PSO repeats, 96 times per day.
- **End of day** — actuals logged, forecast error computed, drift-triggered retraining and GA warm-starting applied.

---

## 3. Why the components do not overlap

The most likely objection is that GA and PSO are both global optimisers and therefore duplicate one another. The design answers this two ways, and both belong in the report.

**Timescale separation.** GA runs once daily on the day-ahead schedule; PSO runs 96 times daily against realised forecast error.

**Bounded search.** PSO's bounds are set to approximately ±10% of the GA setpoint rather than the full variable range. This makes local refinement a property of the implementation rather than an assertion about algorithm behaviour.

This construction is a **memetic algorithm** — an established class combining population-based global search with local refinement. Cite it as such rather than presenting it as novel.

---

## 4. Objective function

```
J = Σ [ import cost − export revenue ] + degradation cost + constraint penalties
```

Degradation is computed by extracting charge/discharge cycles from the SOC trajectory using rainflow counting, then applying a power-law relationship between cycle depth and cycles-to-failure:

```
N_fail(d) = a · d^(−b)
C_deg = Σᵢ C_capital / (2 · N_fail(dᵢ))
```

Take `a` and `b` from a published fit for the relevant battery chemistry and cite the source.

This term is nonconvex and non-differentiable. It is the technical justification for using metaheuristics rather than a MILP solver.

### Constraints

- SOC held between 20% and 90%
- Battery power magnitude bounded by rated charge/discharge power
- Power balance enforced at every interval
- Grid connection capacity limits on import and export
- **Terminal SOC condition** — without it the optimiser drains the battery on the final interval and reports savings that are not real. Most common bug in this class of project.

---

## 5. Technology stack

### Backend (Python)

| Library | Purpose |
|---|---|
| Python 3.10+ | Core language |
| Pandas / NumPy | Data handling |
| Darts or pytorch-forecasting | TFT implementation |
| PyTorch | Backend |
| LightGBM, statsmodels | Baselines |
| DEAP | Genetic algorithm |
| PySwarms | Particle swarm |
| **PuLP + CBC** | MILP oracle — CBC bundled, no commercial solver |
| rainflow | Cycle extraction for degradation |
| river | Concept drift detection |
| Matplotlib / Seaborn | Report figures |

### Frontend (React)

| Library | Purpose |
|---|---|
| Vite | Build tool and dev server |
| React 18 | UI framework |
| Recharts | Time series and bar charts |
| Tailwind CSS | Styling |
| lucide-react | Icons |

**No backend server for Phases 1–7.** Python writes JSON to `frontend/public/data/`; React fetches it. This avoids FastAPI, CORS, and deployment complexity entirely for the core thesis. The dashboard is a static site — deployable free to GitHub Pages, Netlify, or Vercel.

FastAPI (Phase 6.5) is now a **committed dependency of Phase 8a** (the what-if panel), not merely an optional upgrade — see Phase 8's note. If Phase 8 gets cut for time, Phase 6.5 is cut with it and the static-JSON approach still demonstrates everything the core thesis needs.

---

## 6. Datasets

All primary sources are free, no account, no API key.

### 6.1 Energy data — Open Power System Data

```
https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv
```
124 MB. Start with the 60-minute file. 15-minute version available at the same path if needed later.

Load with `usecols` — the file has 150+ columns for all of Europe:

```python
cols = ['utc_timestamp',
        'DE_solar_generation_actual', 'DE_wind_generation_actual',
        'DE_load_actual_entsoe_transparency',
        'DE_load_forecast_entsoe_transparency',
        'DE_LU_price_day_ahead',
        'DE_solar_capacity', 'DE_wind_capacity']
df = pd.read_csv(path, usecols=cols, parse_dates=['utc_timestamp'])
```

Verify the column names with `df.columns` after download — names shift between package versions.

| Column | Contents |
|---|---|
| `DE_solar_generation_actual` | Actual solar generation, MW |
| `DE_wind_generation_actual` | Actual wind generation, MW |
| `DE_load_actual_entsoe_transparency` | Actual total load, MW |
| `DE_load_forecast_entsoe_transparency` | The TSO's own day-ahead forecast — a professional-grade baseline |
| `DE_LU_price_day_ahead` | Day-ahead spot price, EUR — use for the cost objective |

Note in the report that OPSD funding ended in 2020 and the latest package is dated 2020-10-06. Historical and valid for research, but not current.

### 6.2 Weather covariates — Open-Meteo

```
https://archive-api.open-meteo.com/v1/archive?latitude=52.52&longitude=13.41&start_date=2016-01-01&end_date=2020-06-30&hourly=shortwave_radiation,direct_radiation,temperature_2m,cloudcover,windspeed_100m,winddirection_100m&format=csv
```

Free, no key. Coordinates are Berlin, paired with the German OPSD columns. Use `windspeed_100m`, not `10m` — turbine hubs sit at 80–120 m.

Join to OPSD on timestamp. Weather columns are inputs; generation and load are targets.

### 6.3 Alternatives (not selected — do not drift toward these mid-project)

| Source | Friction |
|---|---|
| NREL Solar / WIND Toolkit | Large, US-specific |
| Renewables.ninja | Registration required, ~20 downloads/hour |
| Elia (Belgium TSO) | Different schema |
| ENTSO-E Transparency | Free account required |

---

## 7. Repository structure

```
renewable-opt/
  configs/
    default.yaml
  data/
    raw/                      downloaded, never edited
    processed/                cleaned, feature-engineered
  src/
    data/
      loader.py               download and load OPSD + Open-Meteo
      features.py             calendar encodings, lags
      splits.py               chronological train/val/test
    forecasting/
      baselines.py            persistence, naive, ARIMA, LightGBM
      tft.py                  Temporal Fusion Transformer
      metrics.py              RMSE, MAE, nRMSE, pinball
    env/
      battery.py              SOC dynamics + rainflow degradation
      objective.py            cost function, weighted
      simulator.py            plant model
    optimization/
      ga_scheduler.py         DEAP day-ahead scheduler
      pso_refiner.py          PySwarms trust-region refiner
      milp_oracle.py          PuLP + CBC perfect-foresight bound
      rule_based.py           heuristic floor
    eval/
      ablation.py             full comparison grid
      plots.py                report figures
    export/
      to_json.py              writes frontend/public/data/*.json
  frontend/
    public/data/              JSON written by Python — gitignored
    src/
      App.jsx
      components/
        ForecastChart.jsx
        DispatchChart.jsx
        SocChart.jsx
        MetricsTable.jsx
        ConvergenceChart.jsx
      lib/
        useData.js            fetch + loading/error states
    package.json
    vite.config.js
    tailwind.config.js
  tests/
  results/
    figures/  models/  logs/
  README.md
```

The `export/to_json.py` module is the contract between Python and React. Every phase adds one export function; the frontend adds one component that reads it.

---

## 8. Three-day sprint (immediate deadline)

Goal: real data loaded, a working forecast, and a React dashboard showing both. Do not attempt the TFT, GA, or PSO in this window.

### Day 1 — Data

1. `mkdir renewable-opt && cd renewable-opt && git init`
2. `conda create -n renew python=3.10 -y && conda activate renew`
3. `pip install pandas numpy matplotlib scikit-learn lightgbm statsmodels`
4. Download the OPSD 60-min CSV into `data/raw/`
5. Fetch the Open-Meteo CSV into `data/raw/`
6. Write `src/data/loader.py` — read both with `usecols`, join on timestamp, save to `data/processed/merged.parquet`
7. Plot every series. Check for gaps, sensor dropouts, DST discontinuities, implausible zeros. Write down every cleaning decision.

**End of day 1:** one clean DataFrame, plots inspected.

### Day 2 — Baselines

1. `src/data/splits.py` — chronological split with the assertion:
   ```python
   assert train.index.max() < val.index.min()
   assert val.index.max() < test.index.min()
   ```
2. `src/forecasting/metrics.py` — RMSE, MAE, nRMSE. Test against hand-computed values.
3. `src/forecasting/baselines.py` — persistence, seasonal naive, LightGBM. ARIMA if time permits.
4. Run all three, produce a results table.
5. `src/export/to_json.py` — write `forecast.json` and `metrics.json`.

**End of day 2:** working forecasts, a metrics table, JSON exported.

### Day 3 — Dashboard

1. `npm create vite@latest frontend -- --template react`
2. `cd frontend && npm install && npm install recharts lucide-react`
3. `npm install -D tailwindcss postcss autoprefixer && npx tailwindcss init -p`
4. Build three components:
   - `ForecastChart` — actual vs. predicted over a 24-hour window, line chart
   - `MetricsTable` — RMSE/MAE per model, best row highlighted
   - `DataOverview` — solar, wind, load, price over a selectable date range
5. `App.jsx` — header, date picker, the three components stacked
6. `npm run dev`

**End of day 3:** a dashboard showing real data, real forecasts, real error metrics.

### What to say in the demo

Be accurate about what it is: a working data pipeline and baseline forecasters, with the TFT, GA, and PSO to follow. A working baseline is a better signal than a polished shell with placeholder numbers.

---

## 9. Compute budget

Money is not the constraint. CPU time is, and it is untested until benchmarked.

### Mandatory benchmark — Phase 4, day 1

**Before committing to any full-season simulation, time one complete GA run end to end** (population 100 × 200 generations, rainflow-counted fitness). Record the wall-clock figure.

Rough estimate is 5–30 seconds per run, making the full ablation grid a matter of hours. Do not trust that estimate. Measure it.

### Cost model

The ablation grid has 8 configurations; only 5 invoke the GA. Across a 90-day season that is roughly 450 GA runs.

PSO is not a concern — 4 dimensions, 25 particles, 50 iterations is trivially fast even at 96 runs/day.

TFT at `hidden_size=64` on ~35k hourly points runs comfortably on a consumer GPU (RTX 3050 class). Colab free tier exists as a contingency but has session/idle limits, and would not help with the CPU-bound GA anyway.

### If the benchmark comes back slow

Apply in order, and document the reduction in the report rather than quietly under-running:

1. Subsample the season — four representative weeks, one per season
2. Reduce GA to population 50 × 100 generations
3. Parallelise fitness evaluation across cores (DEAP supports `multiprocessing`)

### Cut first if behind schedule

- Renewables.ninja secondary evaluation
- NSGA-II multi-objective Pareto front
- The whole post-core UI bundle — restyle to the concept artifact (Phase 7.5), FastAPI (Phase 6.5), what-if panel + explanation layer (Phase 8) — cut before anything above; it's presentation polish on top of an already-complete thesis, not evaluation infrastructure. It's one bundle: 8a's live re-run needs 6.5, and both slot into 7.5's stage-rail shell, so cut or keep them together.

Everything else is load-bearing.

---

## 10. Phase plan

| Phase | Weeks | Backend | Frontend |
|---|---|---|---|
| 1 | 1–3 | Data pipeline, chronological splits, baselines | Dashboard scaffold, forecast + metrics views |
| 2 | 4–6 | TFT trained; LSTM comparison arm | Forecast view extended — quantile bands, model switcher |
| 3 | 6–8 | Simulator, degradation model, MILP oracle | SOC and dispatch charts |
| 4 | 8–10 | **Day 1: GA benchmark.** GA scheduler in DEAP | GA convergence chart, schedule view |
| 5 | 10–12 | PSO refiner with trust-region bounds | Plan vs. corrected dispatch overlay |
| 6 | 12–13 | Closed loop: drift detection, retraining, warm-starting | Drift recovery plot, season replay |
| 7 | 13–15 | Ablation grid, report | Ablation comparison view, deploy |
| 7.5 | Stretch, post-core | Export full per-day season data | Restyle to the concept artifact — stage-rail nav, theme, season scrubber |
| 8 | Stretch, post-core | What-if re-optimisation endpoint (FastAPI) | What-if panel, dispatch explanation layer |

---

## 11. Phase detail

### Phase 1 — Data and baselines (weeks 1–3)

**Backend**

- Split chronologically. Never shuffle a time series; random splits leak future information and inflate accuracy. Enforce with an assertion.
- Engineer cyclical time features — sine/cosine of hour-of-day and day-of-week.
- Plot every raw series and inspect it properly.
- Build all four baselines here. If LightGBM outperforms the TFT, that must surface in week three, not week fourteen.

**Frontend**

- Vite + React + Tailwind + Recharts scaffold
- `useData.js` hook with loading and error states — every component uses it
- `ForecastChart`, `MetricsTable`, `DataOverview`
- Dark-mode-friendly palette; keep the styling consistent from the start rather than retrofitting

**Export contract:** `forecast.json`, `metrics.json`, `overview.json`

### Phase 2 — TFT forecaster (weeks 4–6)

**Backend**

| Setting | Value |
|---|---|
| Implementation | Darts or pytorch-forecasting |
| Input window | 168 hours |
| Forecast horizon | 24 hours |
| Known-future covariates | Calendar features; weather variables |
| Past covariates | Historical PV, wind, load, price |
| Hidden size | 64 to start; tune on validation only |
| Attention heads | 4 |
| Loss | Quantile loss at 10th, 50th, 90th percentiles |
| Optimiser | Adam, early stopping on validation loss |

Retain variable-selection weights and attention outputs — free interpretability figures.

Include LSTM as a comparison arm under identical splits and equal tuning budget.

**Frontend**

- Quantile bands on `ForecastChart` (shaded 10–90 percentile region using Recharts `Area`)
- Model switcher — toggle between TFT, LSTM, LightGBM, persistence
- Variable-importance bar chart from the TFT's selection weights

**Export contract:** extend `forecast.json` with quantiles and per-model series; add `importance.json`

### Phase 3 — Simulator, objective, MILP oracle (weeks 6–8)

**Backend**

**Solver: PuLP with CBC.** CBC ships bundled and needs no configuration. Do not use Pyomo — many of its tutorials default toward Gurobi or CPLEX, which are commercial. Pin this now.

**Decide the oracle's degradation treatment in this phase.** It determines what the headline number means:

- *Without degradation* — solves an easier problem; understates your system.
- *With a piecewise-linear degradation proxy* — fair comparison. **Take this option.**

Report both the oracle's own cost and the *true nonlinear* cost of the oracle's solution. That gap quantifies what linearization loses, and is the strongest available defence of using metaheuristics.

**Frontend**

- `SocChart` — state of charge over 24 hours with the 20%/90% bounds drawn in
- `DispatchChart` — stacked area of generation, load, battery, grid import/export

**Export contract:** `dispatch.json`, `soc.json`, `oracle.json`

### Phase 4 — GA scheduler (weeks 8–10)

**Day 1: run the benchmark in section 9 before writing anything else.**

| Parameter | Setting |
|---|---|
| Chromosome | 24 real values (hourly battery power) + N binary commitment flags |
| Population | 100 |
| Generations | 200 |
| Selection | Tournament, k = 3 |
| Crossover | SBX on real segment, two-point on binary |
| Mutation | Polynomial, rate adapted to population diversity |
| Elitism | Top 5 carried forward unchanged |
| Multi-objective | NSGA-II if a Pareto front is wanted — **cut-first item** |
| Framework | DEAP |

**Frontend**

- `ConvergenceChart` — best and mean fitness per generation
- Schedule view — the 24-hour GA plan as a bar chart, charge below axis, discharge above

**Export contract:** `ga_convergence.json`, `schedule.json`

### Phase 5 — PSO refiner (weeks 10–12)

| Parameter | Setting |
|---|---|
| Dimension | 4 (next four 15-minute intervals) |
| Swarm size | 25 |
| Iterations | 50 |
| **Bounds** | **GA setpoint ± 10% — the defining constraint of the design** |
| Inertia weight | Linear decay 0.9 → 0.4 |
| Alternative | Constriction factor, c₁ = c₂ = 2.05 |
| Initialisation | Particles seeded around the GA solution |
| Runtime target | Under 2 seconds per invocation |
| Framework | PySwarms |

**Frontend**

- Overlay the PSO-corrected dispatch on the GA plan — the divergence between them is the clearest single visual in the project
- Shade the ±10% trust region so the bounding is visible

**Export contract:** `pso_corrections.json`

### Phase 6 — Closed loop (weeks 12–13)

Neither GA nor PSO retains anything between runs. The adaptive behaviour claimed in the title comes from three explicit mechanisms. Define them in chapter one.

**Drift-triggered retraining.** Monitor rolling forecast error; retrain the TFT incrementally when a threshold is breached. Page-Hinkley and ADWIN are in `river`. The figure is a plot of error rising across a season and recovering after each trigger.

**Warm-starting.** Seed the next day's GA population with today's elite chromosomes. Report the reduction in generations to convergence.

**Self-adaptive parameters.** Mutation rate scaled by population diversity; inertia weight by swarm convergence. Plot both.

Be precise: the *forecaster* learns from experience; the *optimisers* converge faster through solution reuse. Do not describe the decision-making as learning.

**Frontend**

- Drift recovery chart with retraining events marked as vertical lines
- Season replay — a date slider stepping through simulated days, updating all charts

**Export contract:** `drift.json`, `season.json`

### Phase 6.5 — FastAPI upgrade (stretch, required for Phase 8a)

Committed to once Phase 8a (the what-if panel) is in scope — clicking "re-run" in the browser and watching a real PSO call execute, not a canned response.

```
pip install fastapi uvicorn
```

Endpoints: `POST /forecast`, `POST /optimize`, `GET /results/{run_id}`. Frontend switches from `fetch('/data/x.json')` to `fetch('/api/x')`.

Adds real complexity — CORS, async job handling, error states, deployment. Not required for the core thesis (Phases 1–7 stay static-JSON); build it only when Phase 8a is actually being pursued.

### Phase 7 — Ablation and report (weeks 13–15)

**Frontend**

- Ablation comparison view — grouped bar chart of cost by configuration, with the oracle drawn as a reference line
- Deploy: `npm run build`, push `dist/` to GitHub Pages or Netlify. Free, and gives you a live link for the report.

### Phase 7.5 — UI restyle to match the concept artifact (stretch, after Phase 7)

By this point every chart in the plan exists (forecast, metrics, importance, dispatch, SOC, GA convergence, schedule, PSO overlay, drift/season-replay, ablation). Restyle **once**, now that the full chart set is known, rather than building a container earlier and reworking it every phase.

Reference: the "Renewable Microgrid Optimizer — End-State Concept" artifact. Adopt its **design**, not its implementation — it renders static mock data with hand-rolled SVGs; the real dashboard keeps Recharts, since it already gives real tooltips, legends, and accessibility the mockup's illustrative SVGs don't have.

What to carry over:

- **Stage-rail navigation** — four tabs (Forecast / Day-ahead schedule / Live ops / Season results) replacing today's single scrolling page of stacked cards. Tabs group charts by their natural cadence, matching the architecture table in section 2 (once-daily forecast/schedule, every-15-min live ops, end-of-season results).
- **Light/dark theme** using the artifact's CSS custom properties (accent green, live/amber, critical red, surface tokens).
- **Season scrubber + play button** on the Live-ops tab. This needs the full season exported **per day**, not the one representative week Phase 3 currently exports — the scrubber has nothing real to step through otherwise.
- **Headline stat treatment** (large number + caption) for the "% of oracle captured" metric on the Season-results tab.

**Frontend**

- Restructure `App.jsx` around the 4-tab stage rail
- Apply the artifact's color tokens app-wide, light and dark

**Backend**

- Extend the export layer to write full per-day season data (SOC, dispatch) instead of a single window, for the scrubber

**Export contract:** `dispatch.json`/`soc.json` extended to full-season granularity (or a new `season.json`)

### Phase 8 — Stretch enhancements (optional, after Phase 7.5)

Two additions that turn the dashboard from a static report into something interactive and defensible in a viva. Neither is load-bearing for the core thesis — cut both without weakening chapters 1–13 if time runs out. **8a firmly requires Phase 6.5 (FastAPI)** — a genuinely live what-if needs a real backend to re-run PSO; faking the re-optimisation client-side, the way the concept artifact's own mockup did with a `setTimeout` and a made-up formula, would be dishonest to present as real in a final year project. Both features are also visual residents of Phase 7.5's "Live ops" tab (that's where the artifact placed them), so build 7.5 first.

**8a — What-if scenario re-optimisation.** Let the user perturb an input — solar forecast (±20%), battery capacity (50–150 kWh) — and re-run PSO against the current GA plan, returning the new season cost in a couple of seconds. Demonstrates the pipeline responds to changed inputs rather than only replaying canned results; a strong live-demo moment.

| Setting | Value |
|---|---|
| Endpoint | `POST /whatif` — takes `{solar_pct, battery_kwh}`, returns `{new_cost, delta_pct}` |
| Compute | Re-run PSO only (not GA) against the scaled forecast/capacity — this is why it completes in ~2s |
| Frontend | Two sliders + "re-run" button, disabled while in flight; result shown as `€cost (Δ ±x%)` |

**8b — "Why this decision" explanation layer.** A short plain-language paragraph generated from the schedule, forecast, and price data explaining a dispatch decision — e.g. *"Charging 11:00–14:00: forecast shows a solar surplus over load and price troughs mid-day."* Generate it with a template filled from the actual numbers (charge/discharge windows, forecast surplus, price extrema), not a hand-written string, and not a full LLM call unless one is already in the stack for another reason. This is also the component referenced in section 14: if the project title keeps any reference to generative AI, this is what justifies it.

**Export/API contract:** `whatif.json` or `POST /whatif` response schema; `explanation.json` (or generated client-side from `schedule.json` + `forecast.json` + price data already exported).

---

## 12. Evaluation

| Configuration | What it isolates | Uses GA? |
|---|---|---|
| Rule-based controller | Performance floor | No |
| MILP + perfect foresight | Theoretical ceiling | No |
| GA only | Standalone GA | Yes |
| PSO only | Standalone PSO | No |
| GA → PSO, unbounded | Naive hybridisation | Yes |
| GA → PSO, trust region | The proposed design | Yes |
| GA → PSO, persistence forecast | Contribution of the TFT | Yes |
| GA → PSO, LSTM forecast | Value of the transformer | Yes |

**Metrics:** total operating cost; percentage of oracle optimum; constraint violations; degradation cost; generations to convergence; wall-clock runtime.

The percentage-of-oracle figure is the headline result. "Captured 87% of the theoretical optimum with no foresight" is far stronger than a bare cost reduction, and few comparable studies report it.

### 12.1 Actual results (`src/eval/ablation.py`, 28 representative days, 4 seasonal weeks)

| Configuration | Cost (€) | % of oracle's saving | Degradation (€) | Violations |
|---|---:|---:|---:|---:|
| MILP oracle (ceiling) | 320.16 | 100.0% | 61.7 | 0 |
| GA→PSO, LSTM forecast | 355.91 | 88.1% | 38.8 | 0 |
| **GA→PSO, trust region (proposed)** | **377.39** | **81.0%** | 35.9 | 0 |
| Rule-based (naive floor) | 380.54 | 79.9% | 39.1 | 0 |
| GA→PSO, persistence forecast | 389.45 | 77.0% | 31.2 | 0 |
| GA→PSO, unbounded | 389.33 | 77.0% | 36.5 | 0 |
| GA only (no PSO) | 468.69 | 50.7% | 41.0 | 0 |
| PSO only (standalone) | 1028.83 | −135.4% | 60.7 | 0 |

Idle (no battery) €621.27 → oracle €320.16 over these 28 days. Zero constraint violations across every configuration; the oracle-is-a-valid-ceiling invariant held.

**Read it like this:**
- **PSO adds real value**: GA-only (50.7%) → GA+PSO trust-region (81.0%), +30 points from intraday correction.
- **The proposed design beats the naive floor** (81.0% vs 79.9%) — but only after recalibrating the trust-region width. The plan's literal "±10%" under-corrects (68.2% in an earlier sweep); unbounded (100%) over-corrects and loses the GA's structural anchor (77.0%); **±50% of max power is the calibrated sweet spot** (81.0%) — see `pso_refiner.py`'s docstring for the full sweep. Report the sweep itself as a finding, not just the final number: it shows the bound width is a real, non-obvious hyperparameter.
- **Standalone PSO is bad** (−135.4%, worse than doing nothing) — direct empirical support for section 3's argument that PSO alone can't replace GA's structured day-ahead search.
- **Honest surprise**: LSTM's forecast (88.1%) outperformed TFT's (81.0%) here, despite TFT having better raw RMSE (Phase 2). Forecast accuracy and downstream operational value aren't the same thing; flag this in the report as a genuine finding with a small-sample caveat (28 days), not a result to suppress.
- **Two real bugs were caught by the ablation's own correctness invariants** during development (a rule-based charge/discharge sign error; a terminal-SOC settlement that could be gamed by ending with a lucky surplus, credited at the wrong price) — worth a sentence in the methodology section as evidence the results were validated, not just computed.

**Run the unbounded vs. trust-region comparison early.** It is the only evidence answering what PSO adds over GA alone.

---

## 13. Questions to be prepared for

| Question | Prepared answer |
|---|---|
| Why not use a MILP solver? | The degradation term is nonconvex and non-differentiable. The MILP oracle is a benchmark, not the solution — and the gap between its linearized and true nonlinear cost quantifies what linearization loses. |
| What does PSO add over GA alone? | Answered empirically by the unbounded vs. trust-region ablation rows. |
| Why TFT rather than LSTM? | TFT consumes known-future covariates natively. Both are benchmarked and the result reported either way. |
| Where is the self-learning? | Drift-triggered retraining, GA warm-starting, self-adaptive operator parameters — each with a figure. The forecaster learns; the optimisers reuse solutions. |
| What is novel here? | Not the algorithm combination, which appears in the literature. The contributions are the degradation-aware objective, the trust-region formulation of the GA→PSO handoff, and oracle-benchmarked evaluation. |

---

## 14. Scope boundaries

- Control operates at 15-minute dispatch resolution. Remove any claim of real-time inverter setpoint control or millisecond power factor correction.
- The GA runs offline, once daily. Not a real-time component.
- The dashboard visualises pre-computed results. Do not describe it as a live control interface unless Phase 6.5 is built.
- If the title retains a reference to generative AI, add a component that justifies it — e.g. a language model layer producing plain-language explanations of dispatch decisions. Otherwise remove the reference.

---

## 15. Milestone checklist

| When | Checkpoint | Done |
|---|---|---|
| Day 1 | Data downloaded, joined, plotted, inspected | ☑ |
| Day 2 | Chronological split asserted; baselines running; JSON exported | ☑ |
| Day 3 | React dashboard showing real forecasts and metrics | ☑ |
| Week 3 | Four baselines complete; results table | ☑ |
| Week 6 | TFT trained and benchmarked against LSTM; quantile bands in UI | ☑ |
| Week 8 | Simulator, degradation model, MILP oracle (PuLP+CBC); oracle degradation treatment decided | ☑ |
| Week 8, day 1 | **GA run timed end-to-end; season scope confirmed or reduced** | ☑ (2.6s for pop 100 × gen 200 — well under the 5–30s estimate, no reduction needed) |
| Week 10 | GA producing feasible schedules; convergence chart live | ☑ |
| Week 12 | PSO integrated with trust-region bounds; unbounded comparison run | ☑ Superseded by the Phase 7 sweep below — ±10% (the plan's literal default) under-corrects; the calibrated default is now ±50% of max power, see Phase 7 note |
| Week 13 | Season simulated; drift retraining demonstrated | ☑ (partial — warm-starting reaches converged quality in ~45% fewer generations; self-adaptive mutation traces diversity↔rate; drift detector implemented but the test season's forecast error is stationary (0 robust triggers), so incremental retraining is an honest negative — detection-only shipped, retrain action deferred to when genuinely drifting/live data exists) |
| Week 15 | Ablation grid complete; dashboard deployed; report drafted | ☑ ablation (28 representative days, 4 seasonal weeks) + dashboard done; report not started |
| Stretch | Dashboard restyled to the concept artifact — stage rail, theme, season scrubber (Phase 7.5) | ☑ |
| Stretch | FastAPI live endpoint (Phase 6.5) ☑ + what-if re-run panel (Phase 8a) ☑ — sliders re-run the real GA live and show new cost; dispatch explanation layer (8b) still ☐ |

---

## 16. Execution order — start to finish

**Now**
1. Create repo, git init, conda env
2. Install Python deps
3. Download OPSD CSV + Open-Meteo CSV
4. `loader.py` — join on timestamp, save parquet
5. Plot and inspect every series

**Day 2**
6. `splits.py` with the leakage assertion
7. `metrics.py`, tested against hand-computed values
8. `baselines.py` — persistence, seasonal naive, LightGBM
9. `to_json.py` — first export

**Day 3**
10. Vite + React + Tailwind + Recharts scaffold
11. `useData.js` hook
12. `ForecastChart`, `MetricsTable`, `DataOverview`
13. `npm run dev` — demo ready

**Weeks 2–3**
14. ARIMA baseline; finish the baseline results table
15. Feature engineering — cyclical encodings, lags
16. `battery.py` — SOC dynamics + rainflow degradation, tested in isolation

**Weeks 4–6**
17. TFT in Darts; train, tune on validation only
18. LSTM comparison arm
19. UI: quantile bands, model switcher, variable importance

**Weeks 6–8**
20. `objective.py`, `simulator.py`
21. `milp_oracle.py` in PuLP+CBC — decide the degradation treatment
22. UI: SOC chart, dispatch chart

**Weeks 8–10**
23. **Benchmark one GA run before anything else**
24. `ga_scheduler.py` in DEAP
25. UI: convergence chart, schedule view

**Weeks 10–12**
26. `pso_refiner.py` in PySwarms, trust-region bounded
27. Run the unbounded comparison immediately
28. UI: plan vs. corrected overlay with the trust region shaded

**Weeks 12–13**
29. Drift detection + retraining; warm-starting; self-adaptive parameters
30. Full season simulation
31. UI: drift recovery chart, season replay slider

**Weeks 13–15**
32. `ablation.py` — the full grid
33. Report figures
34. UI: ablation comparison view; build and deploy
35. Write the report
