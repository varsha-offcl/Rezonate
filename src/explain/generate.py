"""Generate the static explanation.json for the "why this decision" layer
(project plan Phase 8b), and backfill per-hour price into dispatch.json.

Why this exists as a standalone script rather than only inside to_json.py: the
full export re-runs the MILP oracle over the entire test season (slow). The
explanation only needs the one representative week the dispatch chart already
displays, so this runs the oracle on just that window (fast) and writes:

  - frontend/public/data/explanation.json  -- the deterministic facts + template
    text for the most active full day in that week (the day is one the user can
    see on the dispatch chart, so every claim is visually verifiable).
  - price backfilled into frontend/public/data/dispatch.json -- the plan's
    "price extrema" claims need it and it was previously unexported.

to_json.py also builds explanation.json (via build_explanation_json) during a
full regen, using the same src.explain.decision_facts helpers, so the two paths
stay consistent. Run this after a data change when you don't want a full export:

  .venv/Scripts/python -m src.explain.generate
"""

from __future__ import annotations

import json
from pathlib import Path

from src.env.battery import BatterySpec
from src.env.simulator import test_window
from src.explain.decision_facts import facts_for_best_day, render_template
from src.optimization import milp_oracle

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "data"
DISPATCH_DISPLAY_HOURS = 24 * 7  # must match to_json.DISPATCH_DISPLAY_HOURS


def build_explanation(sc, oracle_power) -> dict:
    facts = facts_for_best_day(
        sc.timestamps, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh,
        oracle_power, within=DISPATCH_DISPLAY_HOURS,
    )
    return {
        "policy": "oracle",
        "date": facts["date"],
        "facts": facts,
        "template_text": render_template(facts),
    }


def backfill_dispatch_price(sc) -> None:
    """Add per-hour price to the existing dispatch.json (non-destructive: only
    adds the field, leaves everything else the export wrote in place)."""
    path = OUT_DIR / "dispatch.json"
    if not path.exists():
        print("dispatch.json not found — skipping price backfill (run to_json first).")
        return
    dispatch = json.loads(path.read_text())
    n = len(dispatch["timestamps"])
    dispatch["price_eur_mwh"] = [round(float(v), 2) for v in sc.price_eur_mwh[:n]]
    path.write_text(json.dumps(dispatch))
    print(f"Backfilled price into dispatch.json ({n} hours).")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spec = BatterySpec()

    print(f"Building the {DISPATCH_DISPLAY_HOURS // 24}-day display window (test split)...")
    sc = test_window(DISPATCH_DISPLAY_HOURS)

    print("Running the MILP oracle on the display window...")
    oracle_power = milp_oracle.solve(
        sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec
    )["battery_power_kw"]

    explanation = build_explanation(sc, oracle_power)
    (OUT_DIR / "explanation.json").write_text(json.dumps(explanation))
    print(f"Wrote explanation.json — explaining {explanation['date']} "
          f"({explanation['facts']['n_active_windows']} windows).")
    print("\n--- deterministic template ---")
    print(explanation["template_text"])

    backfill_dispatch_price(sc)


if __name__ == "__main__":
    main()
