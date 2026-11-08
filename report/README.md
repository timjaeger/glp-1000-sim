# GLP-1000 — final report

The world of GLP-1000 was selected, not written. Starting from the researched state of the GLP-1 era in November 2026, a five-step, beam-pruned Monte Carlo sampled 250 candidate futures, two years per step, and at each step kept the three worst plausible worlds and sampled forward from them. The method is in `METHOD.md`; every run, score and selection is in `runs/`, `world/` and `lineage.md`, and this report is re-rendered from them by `python sim.py report`, which first checks that the selection rule reproduces every recorded selection.

## The finalists

| Lineage | Headline | Axis badness | Plausibility | Ancestry |
|---|---|---|---|---|
| [L1](L1.md) | Label-Confirmed Calm: The Side Effect Became the Product, and Your Premium Depends on Taking It | 6.68 | 6.88 | `s1-L0-r09` → `s2-L2-r20` → `s3-L3-r41` → `s4-L2-r28` → `s5-L1-r09` |
| [L2](L2.md) | The Question Now Is Why You're Not: 98 million Americans are on it, prices are frozen, and the coverage comes with a weigh-in | 6.65 | 7.43 | `s1-L0-r09` → `s2-L2-r20` → `s3-L3-r41` → `s4-L2-r28` → `s5-L1-r10` |
| [L3](L3.md) | Show Me Your Grip: In 2036, Everyone's Thin and Your Muscle Says What You Earn | 6.43 | 8.1 | `s1-L0-r41` → `s2-L1-r01` → `s3-L2-r17` → `s4-L3-r49` → `s5-L2-r21` |

## The run, step by step

| Step | Year | Axis of worst | Runs | Valid | Floor | Survivors | Runner-up | Rubric |
|---|---|---|---|---|---|---|---|---|
| 1 | 2028 | health | 50 | 50 | 6 | L1 `s1-L0-r41`, L2 `s1-L0-r09`, L3 `s1-L0-r48` | `s1-L0-r24` | v2 |
| 2 | 2030 | economy | 50 | 48 | 6 | L1 `s2-L1-r15`, L2 `s2-L1-r01`, L3 `s2-L2-r20` | `s2-L2-r31` | v2 |
| 3 | 2032 | culture_and_body | 50 | 50 | 6 | L1 `s3-L1-r05`, L2 `s3-L3-r41`, L3 `s3-L2-r17` | `s3-L1-r16` | v2 |
| 4 | 2034 | politics_and_state | 50 | 48 | 6 | L1 `s4-L2-r28`, L2 `s4-L3-r49`, L3 `s4-L2-r23` | `s4-L3-r43` | v2 |
| 5 | 2036 | interior_life | 50 | 50 | 6 | L1 `s5-L1-r09`, L2 `s5-L1-r10`, L3 `s5-L2-r21` | `s5-L1-r07` | v3 |

## How it was run

- Generator claude-opus-5-5; judge claude-sonnet-5-5 (a different model), 3 judge samples per run, averaged.
- Seed 20261107: every driver draw is `random.Random(seed + step*1000 + run_index)`, recorded in each run file.
- Selection: hard magnitude floor 5, plausibility floor 6 (never below 4), composite plausibility = 0.2 × driver_fidelity + 0.3 × mechanism + 0.5 × magnitude; beam 3, at most 2 survivors per parent.
- Badness scale: rubric v2 (steps 1–4) scores badness relative to each step's parent world; rubric v3 (step 5) scores it as an absolute state against the 2026 baseline, so the final selection picks the worst 2036 rather than the sharpest last two years. Selection only compares runs within a step.
- Pilot and repeated attempts at step 1 (to fix the output schema, token budget, prompt rules and judge rubric) were cleared before the final runs; their run files are in git history and their cost is in `runs/spend_ledger.json`.

## Spend

34 Message Batches, $128.68 recorded in `runs/spend_ledger.json` (actual cost from API-reported usage at batch prices), pilots included:

| Step | Recorded spend |
|---|---|
| 1 | $31.31 |
| 2 | $22.54 |
| 3 | $24.43 |
| 4 | $24.84 |
| 5 | $25.57 |
