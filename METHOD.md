# METHOD — a beam-pruned worst-case Monte Carlo for GLP-1000

## 1. Purpose

Produce the premise for GLP-1000 by *selection* rather than invention. Starting
from the real state of the GLP-1 era in November 2026, sample many plausible
two-year futures, keep the worst ones that a well-informed skeptic could not
dismiss, and sample forward from those. Five steps, ten years, ending in 2036.
The surviving world (or worlds) is the film's setting; the record of how it was
selected is a marketing asset and a credibility device.

## 2. Shape of the run

```
step 0  (2026)  1 baseline  ─ real, researched
step 1  (2028)  50 runs from 1 baseline        → keep 3
step 2  (2030)  50 runs split across 3 parents → keep 3
step 3  (2032)  50 runs split across 3 parents → keep 3
step 4  (2034)  50 runs split across 3 parents → keep 3
step 5  (2036)  50 runs split across 3 parents → keep 3 finalists
```

250 generations, 250 judgments. Final output: three fully-documented lineages
to 2036. Tim chooses the premise from those three by reading, not by score.

**Why beam-of-3 instead of greedy worst-of-50.** Greedy selection five times
compounds toward the single most extreme sample (a 1-in-50⁵ future), which
reads as monotone catastrophe and tends to reward the most lurid prose. A beam
keeps three independent routes alive, so the end has texture and the final
choice is a creative decision among documented options rather than whatever the
dice produced.

## 3. World state

Every step produces a **world state** (JSON, `schema/world_state.schema.json`)
plus a prose rendering. The world state is the thing being simulated; prose is
how it is shown. Fields, in summary:

- `year`, `fictional` (false only at step 0)
- `population`: share of US adults on an incretin drug, by class (top / middle / bottom third), by age band, pediatric share; ever-used; share who cycled off and back on
- `access`: cash price band, public coverage status, employer coverage share, generic status in US / rest of world, gray-market size, dominant route (injectable / oral / monthly)
- `drugs`: on-market classes and best efficacy (% body weight), approved indications beyond weight and diabetes (list), "lifestyle" or off-label mainstream uses
- `safety_ledger`: list of {effect, status: established | suspected | emerging | debunked, prevalence note, regulatory response}
- `economy`: food & beverage, alcohol, restaurants, apparel, fitness, insurance, pharma concentration — each a one-line state plus a direction (collapsing / contracting / adapted / growing)
- `body_and_culture`: what the body signals socially; thinness as class marker or its inversion; eating as ritual; dating and sexuality norms; what "appetite" means
- `interior_life`: the personality layer — prevalence of reward-blunting, how it is framed (side effect / feature / treatment), effect on work, art, intimacy, consumption, politics
- `state`: regulatory posture, subsidy or mandate, surveillance or conditioning of benefits, military / workforce programs, geopolitics of supply
- `events`: the 3–6 discrete things that happened in this two-year window, each dated
- `open_tensions`: 2–4 unresolved pressures the next step must inherit

## 4. Drivers (the stochastic part)

A "Monte Carlo" where each run is just "write a two-year outcome" samples the
model's mode fifty times. Instead, each run gets **explicit driver values drawn
in code** from `config/drivers.json`, and the generator must make the world
follow from them. The drivers are the experiment; the prose is the rendering.

Drivers (full distributions in config):

| Driver | Type | Note |
|---|---|---|
| `adoption_delta_pp` | numeric | change in share of US adults on-drug over the step; drawn around the recent trend, wide tails |
| `price_path` | categorical | generic_collapse / managed_decline / stalled / shock_up |
| `coverage_shift` | categorical | public_expansion / employer_retreat / status_quo / mandate_or_conditioning |
| `new_indications` | 0–2 draws | alcohol use disorder / nicotine / gambling & compulsive behaviour / cognition & dementia / pediatric under 12 / longevity-wellness mainstreaming / mood & motivation as on-label |
| `safety_signal` | categorical | none / muscle-bone wave / vision class label / GI-pancreatic litigation / anhedonia labelled / pediatric developmental signal / novel long-horizon signal |
| `next_gen_launch` | categorical | none / 30%-class triple agonist / oral parity with injectables / monthly or implant / combo with muscle-preserver |
| `market_shock` | categorical | none / generic flood & counterfeits / tariff-geopolitics / manufacturer scandal / gray-market resurgence |
| `cultural_response` | categorical | normalisation / backlash & body politics / visible class stratification / "natural" movement / aesthetic inversion |
| `state_action` | categorical | none / subsidy / restriction / benefits conditioning & surveillance / workforce-military programme |
| `personality_layer` | ordinal | reward-blunting is: unrecognised / niche side effect / mainstream complaint / marketed feature / employer-encouraged |

Drivers are **conditioned loosely on the parent world**: `config/drivers.json`
allows a parent-state modifier (e.g. if generics already collapsed US prices,
`price_path=generic_collapse` is re-weighted toward `stalled`). Keep this
simple — a few `if parent.access.generic_us == true` style rules — not a model.

The generator is told the drivers as *facts that have become true by the end
of the step* and must build a coherent world in which all of them hold. Where
two drivers pull against each other, that friction is the story.

## 5. Two-axis scoring

Every run is scored by an independent judge on **badness** and **plausibility**
separately. This is the fix for the LLM-judge problem: asked only for "worst",
a model picks the most lurid; asked for plausibility alongside, the lurid run
pays for it.

**Badness (1–10, 10 = worst)** is scored on six dimensions and as an overall:

1. Human flourishing — health, lifespan, lived wellbeing of the median person
2. Autonomy & consent — who chooses the drug, who is pressured, who is conditioned
3. Inequality — stratification by access, body, class, age
4. Public health — the aggregate ledger including people off-drug and children
5. Social cohesion — trust, family, eating as ritual, solidarity
6. Epistemic health — can people tell what is happening to them; is the harm nameable

Worst means worse *for people*, not more spectacular. The rubric instructs the
judge to penalise melodrama: mass death, collapse and cartoon villains lower
plausibility and do not raise badness unless the mechanism is shown.

**Plausibility (1–10, 10 = most plausible)**: does every change follow from the
drivers and the parent state with a visible mechanism; are magnitudes in range
for two years; would an informed skeptic (an endocrinologist, a health economist,
a food-industry analyst) accept it as a live possibility rather than dismiss it.

**Generativity (1–10)**: how much film is in this world — characters implied,
scenes implied, a visible texture of daily life. Used only as a tie-break.

## 6. Judge independence

- Judge model is a different model from the generator (e.g. generator
  `claude-opus-4-5`, judge `claude-sonnet-4-5` — set in `config/sim.json`;
  check current model IDs before running).
- The judge sees the parent world, the drawn drivers and the run. It does not
  see other runs, scores, the step's axis weighting or lineage identity.
- Judging runs at temperature 0. Optionally `judge_samples: 3` averages three
  judge calls per run for stability; default 1 to save cost.
- The judge must return a short `rationale` per dimension. These are kept; they
  are part of the dossier and catch judge drift.

## 7. Selection rule (code, not model)

Each step has an **axis of worst**, rotated so the end state is textured rather
than one note struck five times:

| Step | Year | Axis | Badness dimensions weighted 2× |
|---|---|---|---|
| 1 | 2028 | Health | flourishing, public health |
| 2 | 2030 | Economy | inequality, plus the `economy` section's severity |
| 3 | 2032 | Culture & body | cohesion, autonomy |
| 4 | 2034 | Politics & state | autonomy, epistemic health |
| 5 | 2036 | Interior life | flourishing, epistemic health, plus `interior_life` severity |

Procedure per step:

1. Discard runs with `status != "ok"`.
2. **Plausibility floor:** discard runs with `plausibility < 6`. If fewer than 3
   runs survive, lower the floor by 1 and repeat (log it). Never below 4.
3. Compute `axis_badness` = weighted mean of the six badness dimensions with the
   step's weights.
4. Rank by `axis_badness` desc, tie-break by `plausibility` desc, then
   `generativity` desc.
5. **Diversity guard:** the 3 survivors must not all share the same parent
   lineage unless only one lineage has survivors; and no two survivors may have
   identical `price_path` + `cultural_response` + `personality_layer`. Walk down
   the ranking until the constraint is satisfied.
6. Write each survivor's world state to `world/stepN.json` keyed by a new
   lineage id (`L1`, `L2`, `L3`, with parent recorded) and append the selection,
   with scores and the runner-up, to `lineage.md`.

Distribution of next step's 50 runs across the 3 parents: 17 / 17 / 16.

## 8. The two notes the generator must hold

**The personality layer is the pivot.** GLP-1-class drugs dampen reward-seeking
broadly, not just for food; by 2026 this is an observed complaint ("Ozempic
personality") and an active clinical lead (alcohol use disorder trials). The
film's horror lives at the point where compulsion-blunting becomes an on-label
lifestyle or productivity indication and the interior life of a population is
priced like a utility. Drivers can get there; they must not be forced there.

**Off-drug is a population too.** Roughly two-thirds of starters stop within a
year; many restart. Every step must account for the people cycling off and on,
the people who never could afford it, and the children who grew up inside it.

## 9. Cost

Rough per-step budget at 50 runs: generation ~50 × (6k in + 3k out) tokens;
judging ~50 × (8k in + 1k out). On the Batch API with current pricing that is
single-digit dollars per step, well under $50 for the whole run. The cost
guardrail in `config/sim.json` is a ceiling, not a target.

## 10. Output

`report/` holds one dossier per finalist: the 2036 world state and prose, the
full ancestry 2028→2036 with drivers and scores at every step, the runner-ups
it beat, and the judge rationales. Tim reads the three dossiers and chooses.
The chosen lineage's `lineage.md` excerpt becomes the "selected from 250
futures" artifact for the film's site.
