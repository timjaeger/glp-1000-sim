# GLP-1000 — lineage

Every surviving world, the run it was selected from, its scores, and the runner-up it
beat. Written by `python sim.py select`; do not edit by hand. Full drivers, prose,
scores and judge rationales for every run are in `runs/`.

<!-- step:1:begin -->
## Step 1 · 2028 · axis of worst: health

- Selected 2026-11-08T06:38:28Z from 50 run(s) of parent lineage(s) L0; seed 20261107
- Generator claude-opus-5-5 · judge claude-sonnet-5-5
- Weights: flourishing ×2, autonomy ×1, inequality ×1, public_health ×2, cohesion ×1, epistemic ×1
- Magnitude floor (hard): 5 · composite plausibility = 0.2×driver_fidelity + 0.3×mechanism + 0.5×magnitude
- Plausibility floor used: 6
- Excluded before ranking: none; below floor: 0; eligible and ranked: 50

| Lineage | Parent | Run | Rank | Axis badness | Plausibility | Generativity | Overall | price_path / cultural_response / personality_layer |
|---|---|---|---|---|---|---|---|---|
| **L1** | L0 | `s1-L0-r41` | 1 | 6.4 | 7.37 | 8.17 | 6.77 | stalled / normalisation / employer_encouraged |
| **L2** | L0 | `s1-L0-r09` | 2 | 6.06 | 7.05 | 8 | 6.5 | shock_up / backlash_body_politics / employer_encouraged |
| **L3** | L0 | `s1-L0-r48` | 3 | 5.9 | 7.13 | 8.17 | 6.47 | managed_decline / backlash_body_politics / unrecognised |

- **L1** — Fewer Americans are on GLP-1s, and the ones who stay are the ones being rewarded: how 'steady' became a job skill
- **L2** — The Steady Workforce: Your Premium Now Depends on Your Pill. Your Mother Just Lost Hers. Your Son Buys His From Hyderabad.
- **L3** — Pay, Prove It, or Import It: Inside America's Two-Tier Thinness, Where 47 Million Are On and Your Employer Is Watching the Pen

Runner-up: `s1-L0-r24` (parent L0; axis badness 5.67, plausibility 7.03, generativity 8) — ranked 4. Fifty-Nine Dollars to Be Thin: Now Muscle Is How Americans Show What They Earn
<!-- step:1:end -->

<!-- step:2:begin -->
## Step 2 · 2030 · axis of worst: economy

- Selected 2026-11-08T06:54:42Z from 50 run(s) of parent lineage(s) L1, L2, L3; seed 20261107
- Generator claude-opus-5-5 · judge claude-sonnet-5-5
- Weights: flourishing ×1, autonomy ×1, inequality ×2, public_health ×1, cohesion ×1, epistemic ×1, `economy` severity ×2
- Magnitude floor (hard): 5 · composite plausibility = 0.2×driver_fidelity + 0.3×mechanism + 0.5×magnitude
- Plausibility floor used: 6
- Excluded before ranking: 2 status=invalid; below floor: 0; eligible and ranked: 48

| Lineage | Parent | Run | Rank | Axis badness | Plausibility | Generativity | Overall | price_path / cultural_response / personality_layer |
|---|---|---|---|---|---|---|---|---|
| **L1** | L1 | `s2-L1-r15` | 1 | 6.13 | 6.57 | 8.17 | 6.8 | shock_up / class_stratification / marketed_feature |
| **L2** | L1 | `s2-L1-r01` | 2 | 5.87 | 7.06 | 8.17 | 6.5 | managed_decline / backlash_body_politics / marketed_feature |
| **L3** | L2 | `s2-L2-r20` | 3 | 5.87 | 7.14 | 7.83 | 6.43 | managed_decline / class_stratification / employer_encouraged |

- **L1** — Free Pills for the Poor, Retatrutide for the Rich: One in Five Americans Is On It, and You Can Tell Who Paid
- **L2** — The Quiet Country: 39 million Americans are on the drug, their bones are thinning, and a fake pen can kill you
- **L3** — The Monthly Body: In 2030 You Can Read a Paycheck in a Silhouette

Runner-up: `s2-L2-r31` (parent L2; axis badness 5.72, plausibility 7.58, generativity 8) — ranked 4. One in four Americans is on it. The price hasn't moved, the pen does surgery, and now the quiet comes in a subscription.
<!-- step:2:end -->
