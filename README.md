# Autonomous Self-Learning System for Optimizing Renewable Energy

TFT + GA + PSO — see `Project_Plan_1.md` (in Downloads) for the full plan.

Status: **Phase 1 complete; Phase 2 (TFT + LSTM) code complete, awaiting a
GPU training run.** Phase 1: real data loaded and cleaned, three baseline
forecasters trained and evaluated, results exported and visualised in a React
dashboard. Phase 2: a multi-target Temporal Fusion Transformer (quantile
P10/P50/P90 bands) plus an LSTM comparison arm are implemented in
`src/forecasting/tft.py` on identical splits, with the export and dashboard
(model switcher, quantile band, variable-importance card) already wired — the
models just need to be trained on a GPU. See `TODO_PHASE2.md` (or `HANDOFF.md`
if you received this as a zip) for the exact resume steps. GA/PSO are the
later phases (see plan, weeks 8+).

## Backend

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m src.data.loader        # build data/processed/merged.parquet
.venv/Scripts/python -m src.data.data_quality  # plots + data-quality report -> results/figures/
.venv/Scripts/python -m src.data.splits        # sanity-check the chronological split
.venv/Scripts/python -m src.forecasting.metrics    # metric sanity checks
.venv/Scripts/python -m src.forecasting.baselines  # train + print results table
.venv/Scripts/python -m src.forecasting.tft --model both  # Phase 2: train TFT + LSTM (GPU; see TODO_PHASE2.md)
.venv/Scripts/python -m src.export.to_json         # write frontend/public/data/*.json
```

Phase 2 (`tft.py`) needs a CUDA build of PyTorch and is best run on a GPU
(`requirements.txt` installs the CPU build) — see `TODO_PHASE2.md` for the
one-line torch swap. Without the Phase-2 step, `to_json` cleanly exports the
baseline-only dashboard.

See `data/NOTES.md` for data-cleaning decisions (gaps, DST, the
`DE_LU_price_day_ahead` bidding-zone-split gap, etc).

Note: this machine's Windows Application Control policy blocks the newest
PyPI wheel builds of pandas (3.x) and matplotlib (3.10.x) from loading their
compiled DLLs ("Application Control policy has blocked this file"). Pinned
versions in this repo (pandas 2.2.3, matplotlib 3.9.2, scikit-learn 1.5.2,
lightgbm 4.5.0, statsmodels 0.14.4, pyarrow 17.0.0) are known-good on this
machine. If you `pip install --upgrade` any of these, re-verify with
`python -c "import pandas"` etc.

The `.venv/` is gitignored and machine-specific — its `pyvenv.cfg` hardcodes
an absolute path to the base Python, so a `.venv` copied from another machine
won't run (`No Python at '...'`). Always recreate it locally with the two
commands above rather than copying it.

## Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

The dashboard reads static JSON from `frontend/public/data/` — no backend
server. Re-run `src/export/to_json.py` after any backend change to refresh
the dashboard's data.

## Repo layout

See `Project_Plan_1.md` section 7 for the target structure; this repo
follows it.
