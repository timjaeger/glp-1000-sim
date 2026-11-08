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

<!-- step:3:begin -->
## Step 3 · 2032 · axis of worst: culture_and_body

- Selected 2026-11-08T07:09:56Z from 50 run(s) of parent lineage(s) L1, L2, L3; seed 20261107
- Generator claude-opus-5-5 · judge claude-sonnet-5-5
- Weights: flourishing ×1, autonomy ×2, inequality ×1, public_health ×1, cohesion ×2, epistemic ×1, `body_and_culture` severity ×2
- Magnitude floor (hard): 5 · composite plausibility = 0.2×driver_fidelity + 0.3×mechanism + 0.5×magnitude
- Plausibility floor used: 6
- Excluded before ranking: none; below floor: 0; eligible and ranked: 50

| Lineage | Parent | Run | Rank | Axis badness | Plausibility | Generativity | Overall | price_path / cultural_response / personality_layer |
|---|---|---|---|---|---|---|---|---|
| **L1** | L1 | `s3-L1-r05` | 1 | 5.95 | 8.08 | 8.33 | 6.2 | managed_decline / backlash_body_politics / mainstream_complaint |
| **L2** | L3 | `s3-L3-r41` | 2 | 5.88 | 8.3 | 7.83 | 6.27 | managed_decline / class_stratification / marketed_feature |
| **L3** | L2 | `s3-L2-r17` | 3 | 5.82 | 6.92 | 7.67 | 6.17 | stalled / normalisation / marketed_feature |

- **L1** — Lighter, Cheaper, Conditional: 75 Million Americans on the Pen, and Their Bones Are Starting to Show the Bill
- **L2** — Calm, Sold Monthly: America Buys a Quieter Mind as Its Medicated Children Start Coming Up Short
- **L3** — Off It? Explain Yourself. Medicare Now Pays for the Pen, and Wants to See Your Bones First

Runner-up: `s3-L1-r16` (parent L1; axis badness 5.82, plausibility 8.05, generativity 8) — ranked 4. One in Four, With Strings: The Pill Caught the Needle, Coverage Got a Scale, and Tulsa Set the Table
<!-- step:3:end -->

<!-- step:4:begin -->
## Step 4 · 2034 · axis of worst: politics_and_state

- Selected 2026-11-08T17:44:48Z from 50 run(s) of parent lineage(s) L1, L2, L3; seed 20261107
- Generator claude-opus-5-5 · judge claude-sonnet-5-5
- Weights: flourishing ×1, autonomy ×2, inequality ×1, public_health ×1, cohesion ×1, epistemic ×2, `state` severity ×2
- Magnitude floor (hard): 5 · composite plausibility = 0.2×driver_fidelity + 0.3×mechanism + 0.5×magnitude
- Plausibility floor used: 6
- Excluded before ranking: 2 status=invalid; below floor: 0; eligible and ranked: 48

| Lineage | Parent | Run | Rank | Axis badness | Plausibility | Generativity | Overall | price_path / cultural_response / personality_layer |
|---|---|---|---|---|---|---|---|---|
| **L1** | L2 | `s4-L2-r28` | 1 | 6.25 | 6.95 | 8 | 6.5 | managed_decline / class_stratification / employer_encouraged |
| **L2** | L3 | `s4-L3-r49` | 2 | 6.22 | 7.8 | 8 | 6.43 | shock_up / class_stratification / marketed_feature |
| **L3** | L2 | `s4-L2-r23` | 3 | 6.22 | 6.8 | 7.83 | 6.77 | shock_up / backlash_body_politics / marketed_feature |

- **L1** — Twenty-Eight Percent and Steady: America Medicates Its Cravings, Its Bets and Its Bloodwork, and the Boss Prefers It That Way
- **L2** — The Pill Caught Up, the Pen Got Pricier, and Your Shoulders Now Tell Everyone What You Earn
- **L3** — The Pill Caught Up. The Vials Got Expensive. And Now Your Nine-Year-Old Qualifies.

Runner-up: `s4-L3-r43` (parent L3; axis badness 6.18, plausibility 7.97, generativity 8) — ranked 4. The Pill Came. The Generic Didn't. Your Boss Stopped Paying. Thirty-Eight Percent of America Is On It Anyway.
<!-- step:4:end -->

<!-- step:5:begin -->
## Step 5 · 2036 · axis of worst: interior_life

- Selected 2026-11-08T18:20:24Z from 50 run(s) of parent lineage(s) L1, L2, L3; seed 20261107
- Generator claude-opus-5-5 · judge claude-sonnet-5-5 · rubric v3 (badness absolute against the 2026 baseline)
- Weights: flourishing ×2, autonomy ×1, inequality ×1, public_health ×1, cohesion ×1, epistemic ×2, `interior_life` severity ×2
- Magnitude floor (hard): 5 · composite plausibility = 0.2×driver_fidelity + 0.3×mechanism + 0.5×magnitude
- Plausibility floor used: 6
- Excluded before ranking: none; below floor: 0; eligible and ranked: 50

| Lineage | Parent | Run | Rank | Axis badness | Plausibility | Generativity | Overall | price_path / cultural_response / personality_layer |
|---|---|---|---|---|---|---|---|---|
| **L1** | L1 | `s5-L1-r09` | 1 | 6.68 | 6.88 | 8 | 7 | managed_decline / natural_movement / marketed_feature |
| **L2** | L1 | `s5-L1-r10` | 2 | 6.65 | 7.43 | 8.33 | 7.17 | stalled / normalisation / marketed_feature |
| **L3** | L2 | `s5-L2-r21` | 6 | 6.43 | 8.1 | 8 | 7 | stalled / class_stratification / mainstream_complaint |

- **L1** — Label-Confirmed Calm: The Side Effect Became the Product, and Your Premium Depends on Taking It
- **L2** — The Question Now Is Why You're Not: 98 million Americans are on it, prices are frozen, and the coverage comes with a weigh-in
- **L3** — Show Me Your Grip: In 2036, Everyone's Thin and Your Muscle Says What You Earn

Runner-up: `s5-L1-r07` (parent L1; axis badness 6.62, plausibility 7.03, generativity 8) — skipped by diversity guard: parent L1 already has 2 survivors. Less Pull, More Cost: 100 million Americans now take the drug that quiets wanting, and in 2035 the bill went up

Diversity guard skips:
- `s5-L1-r07`: parent L1 already has 2 survivors
- `s5-L1-r08`: parent L1 already has 2 survivors
- `s5-L1-r02`: parent L1 already has 2 survivors
<!-- step:5:end -->
