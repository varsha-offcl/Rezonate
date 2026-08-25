# How's the microgrid project going?

The idea: solar panels, a wind turbine, a battery, and a connection to the
regular grid, all managed automatically — predicting tomorrow's weather and
usage, then deciding when to charge, discharge, or just buy from the grid,
to keep the electricity bill as low as possible. Everything's simulated on
real historical data — no actual hardware.

**All 8 phases complete. Headline result: 81% oracle-capture.**

---

## The whole idea, in one go

Solar and wind don't produce power when you want it — they produce it when
the weather says so. A battery can bridge that gap, but figuring out
exactly when to charge it, when to drain it, and when to just buy from the
grid instead is a genuinely hard planning problem, especially since
electricity prices and weather both change every single day. Doing that by
hand (or with a fixed "always charge at noon" rule) leaves real money on
the table.

So the plan is software that runs the whole decision loop automatically, in
three stages that hand off to each other:

1. **Predict** — a forecasting model looks at the last week and guesses
   tomorrow's solar, wind, and electricity demand.
2. **Plan** — once a day, using that forecast, a search algorithm works out
   a full 24-hour battery schedule (charge here, discharge there) that
   minimises cost. This is a big, slow search done once a day.
3. **Correct** — reality never matches the forecast exactly, so every 15
   minutes a second, much faster algorithm nudges that plan slightly to
   account for the error — but only *nudges*, it's not allowed to rewrite
   the whole day. That restraint is deliberate: it stops the two algorithms
   from just duplicating each other.

The **"self-learning"** part is what stops this from being a fixed,
one-time script: the forecaster notices when its own predictions start
drifting from reality and retrains itself; the planner reuses yesterday's
good schedule as a head start instead of solving from scratch every day;
and the mutation rate self-adapts based on population diversity. It
adapts without a human re-tuning it.

---

## ✅ Phase 1 — Data pipeline + baselines

Plugged in four-plus years of real hourly data — actual solar output, wind
output, electricity demand, and prices from Germany — and built the first
dashboard with baseline forecasting models (persistence, seasonal naive,
LightGBM).

---

## ✅ Phase 2 — TFT + LSTM forecasters

Trained a Temporal Fusion Transformer and LSTM that read the last 168 hours
and predict the next 24 hours of solar, wind, and load — with P10–P90
uncertainty bands the scheduler hedges against. Both outperform the Phase 1
baselines on solar and wind.

---

## ✅ Phase 3 — Battery simulator + MILP oracle

Built a simulated 300 kWh LFP battery (with rainflow cycle degradation) and
a cost calculator. Established two benchmarks:

- **Rule-based floor** — reactive: charge surplus, discharge deficit.
- **MILP oracle ceiling** — perfect foresight, solves the LP exactly.

---

## ✅ Phase 4 — GA day-ahead scheduler

A genetic algorithm (population 100, 200 generations) that searches 24h
of battery setpoints using SBX crossover and two-point binary crossover.
Lands close to the MILP oracle on single-day problems.

---

## ✅ Phase 5 — PSO real-time refiner

Particle swarm optimizer with a ±50% trust region that re-tunes the
dispatch every 15 minutes as actuals diverge from forecast. Improves
realized cost without overwriting the GA's plan.

---

## ✅ Phase 6 — Closed-loop self-learning

- **Warm-starting** — seeds each day's GA with the previous day's elite
  chromosomes, converging faster.
- **Self-adaptive mutation** — mutation rate rises automatically when
  population diversity drops.
- **Drift detection** — Page-Hinkley monitor on forecast error triggers
  TFT retraining when concept drift is detected (0 triggers in test
  season — honest negative).

---

## ✅ Phase 7 — Ablation evaluation

Full ablation grid over the test season. Headline: the complete system
(GA + PSO + warm-start + adaptive mutation) captures **81.0% of the MILP
oracle ceiling** — the gap between "no battery" and "perfect foresight."

---

## ✅ Phase 8 — Interactive dashboard

A 5-tab React dashboard (Vite + Tailwind + Recharts) with a FastAPI backend:

### Today tab (live)
- **Location picker** — search any city worldwide (Open-Meteo geocoding),
  autocomplete dropdown with presets (Berlin, Mumbai, Delhi, London, etc.).
- **Live weather forecast** — real solar irradiance, wind speed, and
  temperature from Open-Meteo for the selected location.
- **Location-aware inputs** — electricity prices adapt to the country
  (50+ country lookup with time-of-use shaping), load profile adjusts
  based on today's temperature (cooling/heating load).
- **GA-optimised battery schedule** — runs the real GA live (~3-5s) against
  today's weather for the selected city.
- **Past vs forecast split** — solid fills for elapsed hours, faded for
  predicted hours, with a "Now" reference line.
- **Cost comparison cards** — no battery vs rule-based vs GA-optimised,
  with savings percentages. All three recalculated per location.
- **GA convergence chart** — shows the optimizer searching for the best
  schedule in real time.
- **Plain-language explanation** — why the optimizer made its decisions.

### Forecast tab
- TFT forecast with P10–P90 uncertainty band and model switcher.
- Metrics table and variable importance from the TFT's attention weights.

### Day-ahead schedule tab
- GA convergence chart (cost over 200 generations).
- The resulting 24h battery schedule.

### Live ops tab
- **Week picker** — navigate all 35 weeks of the test season.
- Dispatch chart, SOC chart, PSO correction overlay.
- Season replay scrubber (play/pause through days).
- Self-learning charts (warm-start convergence, adaptive mutation).
- Drift detection monitor.
- Explanation card.
- What-if panel — sliders for solar % and battery size, re-runs the real
  GA live, with optional AI rephrasing via Groq.

### Results tab
- Headline stat (81% oracle-capture).
- Full ablation table.
- Dataset overview.

### Other features
- Dark/light mode toggle.
- Responsive layout.

---

*Renewable microgrid project — self-learning forecast + optimization,
real weather data for any location worldwide, all simulated on a
hypothetical microgrid. No hardware.*
