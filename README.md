# GLP-1000 — selecting a dystopia

**GLP-1000** is a film in development at [FTRWRLDS](https://ftrwrlds.com): a near future
in which the side effects of weight-loss and personality drugs have quietly remade
society. This repository builds its world.

The premise is not written by hand. It is *selected*. Starting from the real state
of the GLP-1 era in November 2026 — one in nine American adults on the drug,
generics at $8 a month in India and $1,349 list in the US, a Lancet trial showing
the same molecule cuts heavy drinking, a population already describing "Ozempic
personality" — the simulation samples fifty plausible two-year futures, keeps the
three worst that an informed skeptic can't dismiss, and samples forward from those.
Five steps. Ten years. The film is set in 2036, in whichever of the three surviving
worlds reads best on the page.

```
2026 ─┬─ 50 futures ─▶ keep 3 ─┬─ 50 ─▶ 3 ─┬─ 50 ─▶ 3 ─┬─ 50 ─▶ 3 ─┬─ 50 ─▶ 3 finalists
      │   (health)             │ (economy)  │ (culture)  │ (state)    │ (interior life)
     2028                     2030         2032        2034        2036
```

## How "worst" is decided

Three rules keep this from degenerating into the single most lurid sample:

1. **Two axes, scored independently.** Every candidate world is judged on
   *badness* (harm to people, six dimensions) and *plausibility* (does every change
   follow from the drivers and the parent state with a visible mechanism). Only
   worlds above a plausibility floor are eligible to be "worst".
2. **The axis of worst rotates.** Step 1 is worst for health, step 2 for the
   economy, step 3 for culture and the body, step 4 for the state, step 5 for the
   interior life. The end state is textured rather than one note struck five times.
3. **Beam, not greedy.** Three lineages survive each step instead of one. The
   final choice among three documented worlds is a creative decision, not a dice roll.

Each run is driven by explicit random draws — adoption, price path, coverage,
new indications, safety signals, next-generation launches, market shocks, cultural
response, state action, and how society frames reward-blunting — so the simulation
samples the space of futures rather than a language model's single most likely
story fifty times.

Full method: [`METHOD.md`](METHOD.md). Researched starting state with sources:
[`data/step0_baseline.json`](data/step0_baseline.json) and
[`data/step0_sources.md`](data/step0_sources.md).

## Status

Spec, schema, prompts and baseline are complete. The runner (`sim.py`) is being
built with Claude Code — see [`CLAUDE.md`](CLAUDE.md). Runs, scores and the
lineage of every surviving world will be committed here as they happen.

## Layout

```
CLAUDE.md        build instructions for the agent
METHOD.md        the simulation method
config/          sim parameters and stochastic drivers
schema/          JSON Schema for world states and runs
prompts/         generation and judge prompt templates
data/            step-0 baseline (Nov 2026) and its sources
world/           surviving world states per step      (generated)
runs/            every sampled future with its scores  (generated)
lineage.md       ancestry of the surviving worlds      (generated)
report/          final dossiers                        (generated)
```

A project of [FTRWRLDS](https://ftrwrlds.com) · Tim Jaeger
