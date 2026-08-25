# Dashboard charts — what each one is and how to read it

Six charts exist right now (`frontend/src/components/`). All of them read
pre-computed JSON from `frontend/public/data/` (see `src/export/to_json.py`)
— nothing in the browser re-runs a model live. This file explains each one
in plain terms: what it's showing, where the numbers come from, and what
the controls do.

---

## 1. Forecast: actual vs. model (`ForecastChart.jsx`)

**What it shows:** for a chosen target (solar, wind, or load) and a chosen
model, a line for what actually happened next to a line for what the model
predicted, over a 5-day window of data the model never trained on.

**Reading it:** if the predicted line hugs the actual line closely, the
model is good. When "TFT" is selected, you also get a shaded band around its
line — that's its 10th-to-90th-percentile confidence range, i.e. "it thinks
the real value has a 80% chance of landing inside this shaded area."

**Controls:** two dropdowns — pick the target (solar/wind/load) and the
model (TFT, LSTM, LightGBM, seasonal-naive, persistence). Persistence is the
dumbest baseline ("tomorrow = today"); everything else is trying to beat it.

**Data source:** `forecast.json`.

---

## 2. Forecast accuracy (`MetricsTable.jsx`)

**What it shows:** a table of error scores (RMSE, MAE, nRMSE — all "how far
off was the prediction, on average," just computed slightly differently) for
every model, for every target. The best (lowest-error) model per target is
highlighted green with a "best" badge.

**Reading it:** lower numbers are better. nRMSE is the most comparable
column across targets since it's normalised — a good rule of thumb is
"under ~0.10 is a strong forecast for this kind of data."

**Data source:** `metrics.json`.

---

## 3. TFT variable importance (`VariableImportance.jsx`)

**What it shows:** a horizontal bar chart of which inputs the TFT model
actually pays attention to when making its forecast — e.g. "wind history"
or "temperature" — ranked by how much weight the model gives each one.

**Reading it:** longer bars = the model leans on that input more. This is
one of the few genuinely interpretable outputs a "black box" neural network
like this can give you — it's the model grading its own inputs, not a
guess.

**Controls:** a toggle between "past inputs" (things that already happened,
like historical solar) and "known-future inputs" (things you know in
advance, like tomorrow's calendar date or weather forecast).

**Data source:** `importance.json`.

---

## 4. Dispatch: generation, load, battery, grid (`DispatchChart.jsx`)

**What it shows:** one representative week, stacked so you can see at a
glance how the load (black line) got met every hour: solar (amber) + wind
(blue) + battery discharge (violet) + grid import (teal) stack up from zero;
below zero, battery charging and grid export show where any surplus went.

**Reading it:** the black "Load" line is the target — everything below it
needs to add up to meet it. A tall amber/blue stack means renewables covered
most of the hour on their own; a big teal chunk means the grid had to fill
in the gap.

**Controls:** a dropdown to switch between two policies:
- **Rule-based (floor)** — a naive controller with no planning: charges on
  surplus, discharges on deficit, nothing smarter.
- **MILP oracle (ceiling)** — the mathematically optimal schedule *if the
  whole week's weather and prices were known in advance*. Not realistic to
  achieve, but it's the target GA/PSO (upcoming phases) are trying to
  approach.

The text under the chart gives the full-season cost for both policies and
what percentage of the oracle's optimum the floor currently captures.

**Data source:** `dispatch.json` (the week shown) + `oracle.json` (the
season-level summary line).

---

## 5. Battery state of charge (`SocChart.jsx`)

**What it shows:** the battery's charge level (0–100%) over the same week
as the dispatch chart, for both policies at once, with dashed red lines
marking the 20%–90% band it's not allowed to leave.

**Reading it:** the oracle (green, solid) is disciplined — it always
returns to roughly where it started, because it's required to (otherwise
it could "cheat" by draining the battery for free savings on the last
day and never paying it back). The rule-based floor (black, dashed) has no
such constraint and can be seen swinging to the limits unpredictably —
that's the naive controller's blind spot.

**Data source:** `soc.json`.

---

## 6. Data overview (`DataOverview.jsx`)

**What it shows:** the raw solar, wind, load, and price data across the
*entire* dataset (2016–2020), not just the test period — this is the
"ground truth" everything else in the dashboard is built from.

**Reading it:** solar and wind clearly track seasons (more solar in summer,
generally more wind in winter); load has a weekly/daily rhythm; price is
volatile and only exists from late 2018 onward (see the note in
`data/NOTES.md` about the German/Austrian/Luxembourg market split).

**Controls:** a date-range picker. Anything over 30 days automatically
switches to daily averages instead of hourly points, so the chart doesn't
choke on tens of thousands of points.

**Data source:** `overview.json`.

---

## What's coming (not built yet)

Per `Project_Plan_1.md`, later phases add: a GA convergence chart + a
day-ahead schedule bar chart (Phase 4), a GA-plan-vs-PSO-corrected overlay
(Phase 5), a drift/retraining recovery chart + season replay (Phase 6), and
an ablation comparison bar chart (Phase 7). Phase 7.5 restyles all of the
above into a tabbed, artifact-styled dashboard instead of today's single
scrolling page.
