"""GA day-ahead dispatch scheduler (project plan section 11, Phase 4; DEAP).

Scenario: optimizes against the *actual* solar/wind/load/price for a single
24-hour day -- the same "perfect information" framing Phase 3's MILP oracle
uses (`milp_oracle.py`), rather than the TFT's forecast. This keeps Phase 4
directly comparable to Phase 3: the GA is solving the same problem the
oracle solves for one day, via a metaheuristic instead of an LP, which gives
an immediate sanity check -- the GA should land close to, but not beat, the
oracle for that single day. Wiring in the day-ahead TFT *forecast* (planning
under uncertainty, then scoring against what actually happened) is what
Phase 5 (PSO, correcting for forecast error) and Phase 6 (the closed loop)
are for -- see project plan section 1's "day in operation".

Chromosome: 24 real-valued magnitudes (0..max_power_kw) + 24 binary
direction flags (1=discharge, 0=charge) -- together decode to a full
24-hour battery_power_kw schedule. This is the "mixed integer and
continuous variables" chromosome the plan's architecture (section 2) calls
for; SBX crosses the real segment, two-point crosses the binary segment.

Mutation rate is fixed here, not self-adaptive -- that's Phase 6
("self-adaptive parameters" per the plan's closed-loop mechanisms).

Run:
  .venv/Scripts/python -m src.optimization.ga_scheduler --hours 24
  .venv/Scripts/python -m src.optimization.ga_scheduler --fast   # quick smoke test
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
from deap import base, creator, tools

from src.env.battery import BatterySpec
from src.env.objective import evaluate
from src.env.simulator import test_window

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"

HOURS = 24
POP_SIZE = 100
N_GEN = 200
TOURNAMENT_K = 3
ELITE_N = 5
CX_ETA = 15.0  # SBX distribution index -- higher = offspring closer to parents
MUT_ETA = 20.0
GENE_MUT_PROB = 1.0 / HOURS  # expected ~1 gene flipped/perturbed per individual
CX_PROB = 0.9
SEED = 42

creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
creator.create("Individual", list, fitness=creator.FitnessMin)


# --------------------------------------------------------------------------- #
# Chromosome: [0:HOURS) magnitude (kW) + [HOURS:2*HOURS) direction flag
# --------------------------------------------------------------------------- #
def init_individual(spec: BatterySpec):
    mags = [random.uniform(0, spec.max_power_kw) for _ in range(HOURS)]
    flags = [float(random.randint(0, 1)) for _ in range(HOURS)]
    return creator.Individual(mags + flags)


def decode(individual, spec: BatterySpec) -> np.ndarray:
    """-> battery_power_kw (+discharge/-charge), matching objective.evaluate's convention."""
    mags = np.clip(np.array(individual[:HOURS], dtype=float), 0, spec.max_power_kw)
    discharging = np.array(individual[HOURS:], dtype=float) >= 0.5
    return np.where(discharging, mags, -mags)


def mate(ind1, ind2, spec: BatterySpec):
    r1, b1 = ind1[:HOURS], ind1[HOURS:]
    r2, b2 = ind2[:HOURS], ind2[HOURS:]
    tools.cxSimulatedBinaryBounded(r1, r2, eta=CX_ETA, low=0.0, up=spec.max_power_kw)
    tools.cxTwoPoint(b1, b2)
    ind1[:] = r1 + b1
    ind2[:] = r2 + b2
    return ind1, ind2


def mutate(individual, spec: BatterySpec, indpb: float = GENE_MUT_PROB, flag_prob: float = GENE_MUT_PROB):
    r, b = individual[:HOURS], individual[HOURS:]
    tools.mutPolynomialBounded(r, eta=MUT_ETA, low=0.0, up=spec.max_power_kw, indpb=indpb)
    for i in range(len(b)):
        if random.random() < flag_prob:
            b[i] = 1.0 - b[i]
    individual[:] = r + b
    return (individual,)


# --------------------------------------------------------------------------- #
# Phase 6 self-learning helpers: population diversity drives self-adaptive
# mutation, and generations-to-converge quantifies warm-starting's payoff.
# --------------------------------------------------------------------------- #
ADAPT_GAIN = 4.0  # mutation rises up to (1+gain)x its base as the population converges
MAX_INDPB = 0.5

# std of a uniform(0, max_power) real gene is max_power/sqrt(12); dividing the
# observed per-gene std by this normalises a fully-random population to ~1.0.
_UNIFORM_STD_FRAC = 1.0 / (12 ** 0.5)


def population_diversity(pop, spec: BatterySpec) -> float:
    """Normalised mean per-gene spread of the real (power-magnitude) segment,
    ~1.0 for a fresh random population and ->0 as it converges."""
    reals = np.array([ind[:HOURS] for ind in pop], dtype=float)
    per_gene_std = reals.std(axis=0).mean()
    return float(per_gene_std / (spec.max_power_kw * _UNIFORM_STD_FRAC))


def adaptive_indpb(diversity: float) -> float:
    """Self-adaptive per-gene mutation probability: crank mutation up when the
    population has collapsed (low diversity), ease off when it's still exploring."""
    factor = 1.0 + ADAPT_GAIN * (1.0 - min(max(diversity, 0.0), 1.0))
    return min(GENE_MUT_PROB * factor, MAX_INDPB)


def generations_to_converge(history: list, tol: float = 0.01) -> int:
    """First generation whose best fitness has closed (1-tol) of the total
    improvement from gen 0 to the final best -- a scale/sign-robust measure
    of how fast the run effectively converged."""
    initial, final = history[0]["best"], history[-1]["best"]
    gap = initial - final
    if gap <= 0:
        return 0
    threshold = final + tol * gap
    for row in history:
        if row["best"] <= threshold:
            return row["generation"]
    return history[-1]["generation"]


def generations_to_reach(history: list, target: float) -> int:
    """First generation whose best fitness is at or below `target`. Used to
    compare cold vs warm runs against a *shared* quality bar -- the fair way
    to measure warm-starting, which by design begins already near-optimal
    (so measuring it against its own tiny internal gap is misleading)."""
    for row in history:
        if row["best"] <= target:
            return row["generation"]
    return history[-1]["generation"]


def make_toolbox(spec: BatterySpec, sc):
    toolbox = base.Toolbox()
    toolbox.register("individual", init_individual, spec)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def fitness(individual):
        power = decode(individual, spec)
        result = evaluate(power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
        return (result["total_cost"],)

    toolbox.register("evaluate", fitness)
    toolbox.register("mate", mate, spec=spec)
    toolbox.register("mutate", mutate, spec=spec)
    toolbox.register("select", tools.selTournament, tournsize=TOURNAMENT_K)
    return toolbox


# --------------------------------------------------------------------------- #
# Elitist GA loop: top ELITE_N carried forward unchanged (plan section 11)
# --------------------------------------------------------------------------- #
def run_ga(spec: BatterySpec, sc, pop_size: int, n_gen: int, seed: int = SEED,
           warm_start: list | None = None, adaptive: bool = False, return_elites: int = 0):
    """Elitist GA. Phase-6 additions (both off by default, so Phase-4's runs
    are byte-identical):
      * warm_start -- a list of chromosomes (plain lists) seeding the initial
        population; the rest is random. Solution reuse across days (plan
        section 11: "seed the next day's GA population with today's elites").
      * adaptive -- self-adaptive mutation rate driven by population diversity.
    With return_elites>0, also returns that many best chromosomes as plain
    lists, for warm-starting the next day.
    """
    random.seed(seed)
    toolbox = make_toolbox(spec, sc)

    pop = toolbox.population(n=pop_size)
    if warm_start:
        seed_n = min(len(warm_start), pop_size)
        for i in range(seed_n):
            pop[i] = creator.Individual(list(warm_start[i]))
    for ind in pop:
        ind.fitness.values = toolbox.evaluate(ind)

    history = []
    for gen in range(n_gen):
        fits = [ind.fitness.values[0] for ind in pop]
        diversity = population_diversity(pop, spec)
        indpb = adaptive_indpb(diversity) if adaptive else GENE_MUT_PROB
        history.append({"generation": gen, "best": min(fits), "mean": float(np.mean(fits)),
                        "diversity": round(diversity, 4), "mut_prob": round(indpb, 4)})

        elites = tools.selBest(pop, ELITE_N)
        offspring = list(map(toolbox.clone, toolbox.select(pop, pop_size - ELITE_N)))

        for c1, c2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < CX_PROB:
                toolbox.mate(c1, c2)
                del c1.fitness.values
                del c2.fitness.values

        # mutate() applies its own per-gene probability, so it's safe to call
        # on every offspring -- most genes pass through unchanged. Under
        # `adaptive`, that probability rises as the population collapses.
        for ind in offspring:
            toolbox.mutate(ind, indpb=indpb, flag_prob=indpb)
            del ind.fitness.values

        for ind in offspring:
            ind.fitness.values = toolbox.evaluate(ind)

        pop = elites + offspring

    fits = [ind.fitness.values[0] for ind in pop]
    diversity = population_diversity(pop, spec)
    history.append({"generation": n_gen, "best": min(fits), "mean": float(np.mean(fits)),
                    "diversity": round(diversity, 4),
                    "mut_prob": round(adaptive_indpb(diversity) if adaptive else GENE_MUT_PROB, 4)})

    best = tools.selBest(pop, 1)[0]
    if return_elites:
        elite_chromos = [list(ind) for ind in tools.selBest(pop, return_elites)]
        return best, history, elite_chromos
    return best, history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=HOURS, help="must be 24 -- one day-ahead schedule")
    ap.add_argument("--pop-size", type=int, default=POP_SIZE)
    ap.add_argument("--n-gen", type=int, default=N_GEN)
    ap.add_argument("--offset-hours", type=int, default=0, help="which day of the test season to plan for")
    ap.add_argument("--fast", action="store_true", help="tiny pop/gen for a quick smoke test")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    if args.fast:
        args.pop_size, args.n_gen = 10, 5

    spec = BatterySpec()
    sc = test_window(HOURS, offset_hours=args.offset_hours)

    print(f"GA benchmark: pop={args.pop_size} gen={args.n_gen} "
          f"day={sc.timestamps[0].date()} (plan section 9's mandatory Day-1 benchmark)")
    t0 = time.time()
    best, history = run_ga(spec, sc, args.pop_size, args.n_gen, seed=args.seed)
    elapsed = time.time() - t0

    power = decode(best, spec)
    result = evaluate(power, sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)

    print(f"wall-clock: {elapsed:.2f}s ({elapsed / max(args.n_gen, 1):.3f}s/generation)")
    print(f"GA best cost: EUR {result['total_cost']:.2f} "
          f"(import={result['import_cost']:.2f} export=-{result['export_revenue']:.2f} "
          f"deg={result['degradation_cost']:.2f} penalties={result['penalties']:.2f})")

    # Sanity check against the same single day's MILP oracle (Phase 3) -- GA
    # should land close to, but not beat, the true optimum for this day.
    from src.optimization import milp_oracle
    oracle_solution = milp_oracle.solve(sc.solar_kw, sc.wind_kw, sc.load_kw, sc.price_eur_mwh, spec)
    oracle_result = evaluate(oracle_solution["battery_power_kw"], sc.solar_kw, sc.wind_kw,
                              sc.load_kw, sc.price_eur_mwh, spec)
    print(f"same-day oracle cost: EUR {oracle_result['total_cost']:.2f}  "
          f"(GA is {result['total_cost'] / oracle_result['total_cost'] * 100:.1f}% of oracle cost)")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "ga_convergence.json").write_text(json.dumps(history))
    schedule = [{"timestamp": ts.isoformat(), "battery_kw": round(float(p), 2)}
                for ts, p in zip(sc.timestamps, power)]
    (RESULTS / "ga_schedule.json").write_text(json.dumps(schedule))
    print(f"Wrote {RESULTS / 'ga_convergence.json'} and {RESULTS / 'ga_schedule.json'}")


if __name__ == "__main__":
    main()
