# HANDOFF — continue Phase 7.5 / 8b / report

**Read this first.** Phases 1–7 (forecast, simulator, GA, PSO, self-learning
loop, ablation) plus the 6.5/8a interactive layer are all done, verified, and
have real results. This file is for **the next Claude Code session** picking
up from here. Fuller detail lives in `Project_Plan_1.md` (the master plan —
§12.1 has the actual results table; the milestone checklist in §15 shows
what's ☑ vs ☐).

_Handoff prepared 2026-08-04._

---

## State: what's done

- **Phase 1–2** — data pipeline, TFT + LSTM trained (`results/models/{tft,lstm}.ckpt`).
- **Phase 3** — battery/objective/simulator, rule-based floor, MILP oracle.
- **Phase 4** — GA scheduler (`src/optimization/ga_scheduler.py`).
- **Phase 5** — PSO refiner (`src/optimization/pso_refiner.py`).
- **Phase 6** — closed loop: warm-starting + self-adaptive mutation
  (`src/optimization/closed_loop.py`), drift detection (`src/forecasting/drift.py`,
  honest negative — this test season's forecast error is stationary, 0 triggers).
- **Phase 6.5 + 8a** — FastAPI backend (`src/api.py`) + a live "what-if" panel
  on the dashboard (real sliders, re-runs the actual GA, not a lookup).
- **Phase 7.5** — dashboard restyled to match the "Renewable Microgrid
  Optimizer — End-State Concept" artifact: CSS custom-property tokens
  (light/dark, `frontend/src/index.css` + `tailwind.config.js`), a 4-tab
  stage rail in `App.jsx` (Forecast / Day-ahead schedule / Live ops /
  Results) replacing the old single scrolling page, a season replay
  scrubber (`SeasonReplay.jsx`, backed by a new full-season `season.json`
  export from `src/export/to_json.py`), and a headline-stat treatment
  (`HeadlineStat.jsx`) for the oracle-capture % on the Results tab. All
  chart accent/live/critical colors realigned to the token palette.
- **Phase 7** — the ablation grid (`src/eval/ablation.py`), the project's
  headline result. **Read `Project_Plan_1.md` §12.1 before touching anything
  optimization-related** — it has the real numbers and two important findings:
  1. The proposed design (GA→PSO trust-region, TFT forecast) captures **81.0%**
     of the achievable saving vs the oracle, beating the naive rule-based floor
     (79.9%) and clearly beating GA-alone (50.7%) or PSO-alone (−135.4%).
  2. **The PSO trust-region width was recalibrated from the plan's literal ±10%
     to ±50% of max power** (`pso_refiner.TRUST_FRAC`) — ±10% under-corrects
     (68.2%), unbounded over-corrects (77.0%), ±50% is the sweet spot (81.0%).
     This is documented in `pso_refiner.py`'s module docstring with the full
     sweep. If you change the battery spec, price model, or microgrid scale,
     **re-sweep this constant** — don't assume ±50% still holds.

## Two real bugs fixed this session (know these before trusting old numbers)

1. **Rule-based was charging/discharging backwards** (`src/optimization/rule_based.py`)
   — a sign error present since Phase 3, fixed to `p = -net` not `p = net`.
2. **Terminal-SOC settlement exploit** (`src/env/objective.py`) — ending the
   battery with a lucky surplus was credited at the (higher) import price
   instead of the (lower) export price, letting policies bank a fictitious
   credit. Caught by the ablation's own correctness invariant (oracle must be
   a valid ceiling) — now fixed to price deficit at import, surplus at export.

**If you see any dispatch/cost numbers that don't match `Project_Plan_1.md`
§12.1, they're stale — regenerate, don't trust old `results/*.json` blindly.**

## Also fixed: the economics were broken before this session

The battery used to be nearly worthless (idle ≈ oracle) because of three
compounding issues, all fixed:
- Placeholder degradation constants → real fit to published LFP datasheet
  cycle-life points (`src/env/battery.py`'s docstring has the citation).
- Microgrid was import-dominated (little solar surplus) → rescaled to
  oversized renewables vs load (`src/env/simulator.py`).
- **No import/export price asymmetry** → added a realistic retail import
  adder over wholesale (`simulator.IMPORT_ADDER_EUR_MWH`). This was the fix
  that mattered most — it's the actual reason self-consumption batteries pay off.

## What's NOT done

- **Phase 8b** — "why this decision" plain-language explanation layer. Not started.
- **The report** — this is the actual next priority. You have a real,
  evidenced, honestly-caveated result (§12.1) to write up. Nothing else
  blocks this — it can start immediately.

## How to run things

```bash
# Backend (from repo root, venv already set up):
.venv/Scripts/python -m src.export.to_json        # regenerate all dashboard JSON
.venv/Scripts/python -m src.eval.ablation          # re-run the ablation (~8 min, 28 days)
.venv/Scripts/python -m uvicorn src.api:app --port 8000   # what-if backend

# Frontend:
cd frontend && npm run dev                          # dashboard at localhost:5173
```

**Playwright note**: this repo has no persistent Playwright install. When
verifying UI changes, `npm install -D playwright && npx playwright install
chromium`, drive it, then `npm uninstall playwright` afterward — don't leave
it in `package.json`.

**Windows note**: this shell has no `lsof`. To find/kill a process on a port,
use `netstat -ano | grep ":<port>"` then `powershell -Command "Stop-Process
-Id <pid> -Force"` — a plain `kill <pid>` in Git Bash often silently no-ops
on a process it doesn't own, leaving a stale server responding to requests
without you realizing your restart didn't happen.

## Other docs

- `Project_Plan_1.md` — the master plan, phase-by-phase spec, §12.1 has the results.
- `SUMMARY.md` — a plain-language, non-technical summary (was written for
  friends/family — **now stale**, still has old Phase 1–3 numbers, needs a
  refresh once the report direction is set).
- `CHARTS.md` — what each dashboard chart shows and how to read it.
