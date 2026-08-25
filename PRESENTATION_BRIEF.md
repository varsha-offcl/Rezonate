# Autonomous Self-Learning System for Optimizing Renewable Energy
TFT + Genetic Algorithm + Particle Swarm Optimization for microgrid battery scheduling — a final-year capstone project, fully simulated on real historical data, no hardware.

---

## Slide 1 — The Problem

- Solar panels and wind turbines generate power whenever the weather allows — not necessarily when people actually need electricity. That mismatch is the core problem.
- A battery can store the extra and release it later, but deciding exactly when to charge, discharge, or just buy from the grid is a hard planning problem: weather and electricity prices both change every single day.
- A simple fixed rule, like "always charge at noon," leaves real money on the table because it ignores tomorrow's actual conditions.
- This project builds a fully automated system that predicts tomorrow's conditions, plans the cheapest possible 24-hour battery schedule, and keeps correcting that plan as reality unfolds — with no human re-tuning it.
- Headline result: the system captures **81% of the savings a perfect, all-knowing controller could achieve** — without ever seeing the future.

---

## Slide 2 — How the System Works: Three Algorithms, Three Speeds

- **Predict (once a day):** a forecasting model looks at the last week of data and predicts tomorrow's solar output, wind output, and electricity demand.
- **Plan (once a day):** using that forecast, a search algorithm works out a full 24-hour battery schedule — when to charge, when to discharge — that minimizes cost.
- **Correct (continuously):** reality never matches the forecast exactly, so a second, much faster algorithm nudges that plan slightly as errors show up — but it's only allowed to make small adjustments, not rewrite the whole day.
- These two search algorithms don't overlap because they work at different speeds and different scopes: one plans broadly once a day, the other corrects narrowly and often. Proof this separation matters: when we tested the "corrector" running completely alone, it performed *worse than doing nothing at all*.
- "Self-learning" means the system adapts on its own over time: the forecaster notices when its predictions start drifting from reality and retrains itself, and the planner reuses yesterday's good schedule as a head start instead of solving from scratch every day.

---

## Slide 3 — The Data and the Honesty Check

- Built on 4+ years of real historical German data: actual solar output, wind output, electricity demand, and market prices, plus matching weather records (temperature, cloud cover, wind speed).
- Data is split strictly by time — the model is only ever tested on data that comes *after* everything it trained on, never a random shuffle, to avoid the model "cheating" by peeking at the future.
- Because there's no real battery to test this on, the whole project is evaluated in simulation with an honesty check built in: a second, "cheating" version of the controller is allowed to see the *entire* future perfectly in advance.
- That cheating version sets an honest ceiling — the best any controller could ever possibly do. The project's single headline number is simply: how close does our real, no-cheating system get to that ceiling?

---

## Slide 4 — Predicting Tomorrow: The Forecasting Model

- Used a Temporal Fusion Transformer (TFT), a neural network built specifically for forecasting time series like weather and demand — it reads the last week of data and predicts the next 24 hours.
- Unlike a model that gives a single number, this one gives a *range* — "solar output will most likely land between X and Y" — which is more honest about uncertainty and more useful for planning around risk.
- One model predicts solar, wind, and demand together rather than needing three separate models, which is both cheaper to run and captures the fact that these three things are related.
- Tested this model against a simpler alternative (an LSTM) and against basic baselines like "tomorrow will look like today" — the advanced model won on raw prediction accuracy across the board.
- Bonus: the model can show *which* inputs it actually relied on most for its prediction (e.g. recent wind history vs. temperature) — a rare bit of transparency for what's normally a "black box."

---

## Slide 5 — Simulating the Battery and Why It's a Hard Problem

- Built a realistic virtual battery: it charges, discharges, and slowly wears out with use, just like a real one — the wear-and-tear cost is calculated from published real-world battery lifespan data, not guessed.
- The full cost being minimized each day is: *what you pay to import electricity, minus what you earn exporting surplus, plus the cost of battery wear, minus any rule you broke* (like overcharging).
- One critical rule: the battery must end each day roughly where it started. Without this, the planning algorithm could "cheat" by draining the battery for free savings on the very last day and reporting a fake win — this is the single most common bug in this type of project, and it was explicitly guarded against.
- The battery wear-and-tear cost behaves in a way that's mathematically awkward — it doesn't scale smoothly, so it can't be solved with a plain, exact optimization solver. That awkwardness is the actual technical reason this project needed the two "search" algorithms (described next) instead of one clean mathematical solve.
- Two reference points were built to bracket performance: a "floor" (a naive controller with no planning ahead) and a "ceiling" (the cheating, perfect-future controller from Slide 3).

---

## Slide 6 — The Two Search Algorithms

- **The Genetic Algorithm (planner):** inspired by evolution — it generates thousands of candidate 24-hour battery schedules, keeps "breeding" and mutating the best ones together, and converges on a strong full-day plan based on tomorrow's forecast.
- **The Particle Swarm algorithm (corrector):** inspired by how a flock of birds or school of fish converges on a good spot together — it searches for small adjustments to the next few hours only, and is deliberately restricted to stay close to the planner's original schedule rather than free to roam.
- That restriction — how "close" the corrector is allowed to stray — turned out to be a real, tunable design choice, not an arbitrary setting: too tight and it barely helps (captures only 68% of possible savings); unloosed completely and it starts undoing the planner's good work (77%); the right middle ground reached the best result of all: **81%**.
- This finding was reached by actually testing multiple settings side by side, not by assuming a number — a good example of the project validating its own design decisions with evidence.

---

## Slide 7 — The Headline Result

- Ran every version of the system — the naive floor, the perfect-future ceiling, the full proposed system, and several stripped-down variants — over the same 28 days of real conditions, spanning all four seasons.
- **The proposed system (forecast → plan → correct) captured 81% of the maximum possible savings**, spending €377 against a theoretical best of €320 and a "do nothing" cost of €621.
- It beat the naive, no-planning floor (which only captured 80%) — proof the extra complexity is actually earning its keep.
- The corrector algorithm alone, with no planner to work from, did *worse than doing nothing* — strong evidence that the two algorithms genuinely need each other; neither one replaces the other.
- Every single version tested obeyed all physical constraints with zero violations — meaning these numbers reflect real, valid, comparable schedules, not a rigged result.

---

## Slide 8 — What We Learned (Including Honest Surprises)

- The corrector algorithm alone added a huge amount of value on top of the planner — roughly 30 percentage points of extra savings captured, just from correcting the plan as the day unfolds.
- One genuine surprise: the simpler forecasting model (LSTM) actually led to slightly *better* real-world savings than the more advanced one (TFT), even though the TFT was individually more accurate at prediction. Being a better forecaster and being more useful downstream turned out not to be quite the same thing — reported honestly rather than hidden, with the caveat that this was only tested over 28 days.
- During development, the project's own cross-checks caught two real bugs before they could quietly inflate the results: one where the naive controller was charging and discharging backwards, and one where the system could earn a small, unrealistic bonus by ending the season with a lucky battery surplus. Both were found and fixed — a sign the results were actually verified, not just computed and trusted blindly.

---

## Slide 9 — The Dashboard, Limitations, and What's Left

- Built a live, interactive dashboard (a website) that walks through the whole pipeline: tomorrow's forecast, the day-ahead plan, live corrections as the day unfolds, and the season's final results — including a slider that lets someone tweak assumptions (like solar output or battery size) and watch the system genuinely re-plan in real time, in a couple of seconds.
- Honest limitations: the weather data fed into the forecaster is the *actual* recorded weather, not a real weather forecast, since real forecasts introduce their own error the project didn't have time to model — a reasonable simplification, clearly stated rather than glossed over. The full evaluation also covers 28 representative days rather than a multi-year season, for time reasons.
- This is a simulation-only project — there is no physical battery, solar panel, or grid connection involved anywhere.
- What's left: a short feature that explains *why* the system made a given decision in plain language (e.g. "charging now because solar is high and prices are about to spike"), and writing up the final report — neither of which changes anything already built and verified.
