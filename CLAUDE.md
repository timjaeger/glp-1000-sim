# GLP-1000 — worst-case world simulation

This repo builds the world for **GLP-1000**, a dystopian film by Tim Jaeger (FTRWRLDS).
The premise is not written by hand. It is *selected*: a five-step, beam-pruned
Monte Carlo over the GLP-1 craze, each step a two-year jump, each step keeping the
worst plausible futures and sampling forward from them. The film is set in the
end state (2036). The lineage — "this world was chosen from 250 candidate futures"
— is part of the film's marketing, so every run, score and selection must be logged
and reproducible.

Read `METHOD.md` before writing any code. It is the spec. `data/step0_baseline.json`
is the researched real-world starting state (Nov 2026) with sources in
`data/step0_sources.md`; do not edit its facts without a source.

## What to build

A small Python CLI (3.11+, stdlib + `anthropic` + `jsonschema`), no framework:

| Command | What it does |
|---|---|
| `python sim.py generate --step N [--n 50] [--seed S]` | Draws drivers per run from `config/drivers.json`, renders `prompts/generate.md`, submits ONE Anthropic **Message Batches** request for all runs in the step, polls, writes `runs/stepN/<lineage>/<run_id>.json` |
| `python sim.py judge --step N` | Renders `prompts/judge.md` per run, submits one batch, writes `scores` into each run file. Judge model ≠ generator model (see METHOD §6) |
| `python sim.py select --step N` | Applies the selection rule (METHOD §7) → `world/stepN.json` (one file per surviving lineage) and appends to `lineage.md` |
| `python sim.py report` | Renders `lineage.md` + a `report/` folder: one markdown per final lineage, full ancestry, drivers and scores at every step |
| `python sim.py validate` | Validates every JSON file in `world/` and `runs/` against `schema/` |

Step 0 is `world/step0.json` = `data/step0_baseline.json` (copy it there on first run).
Steps 1–5 → years 2028, 2030, 2032, 2034, 2036.

## Rules

- **Determinism.** Every random draw comes from `random.Random(seed + step*1000 + run_index)`. Record the seed and the drawn drivers in each run file. Rerunning `generate` with the same seed re-draws the same drivers (the LLM output will still vary; that is fine — the drivers are the experiment, the prose is the rendering).
- **Batch API only** for generation and judging. Never loop synchronous calls over 50 runs. One batch per command. Use `temperature: 1.0` for generation, `0.0` for judging.
- **Schema or it didn't happen.** Generator output must parse as `schema/world_state.schema.json` (plus the prose fields). Use a tool/JSON-schema-constrained response. A run that fails validation after one repair attempt is written with `"status": "invalid"` and excluded from selection; never silently dropped.
- **Never invent a baseline statistic.** Step 0 facts come only from `data/step0_sources.md`. Simulated steps are fiction and may contain invented figures — they must carry `"fictional": true` in the world state so nothing from a simulated step can be mistaken for research.
- **Judge independence.** The judge never sees other runs' scores, the step's "worst axis" weighting, or which lineage a run came from. It sees baseline + run and scores the rubric. The weighting is applied in `select`, in code.
- **Cost guardrail.** Print an estimated token count and USD before submitting any batch (main or repair). Abort unless `--yes` if the batch's worst-case estimate exceeds `config/sim.json: max_usd_per_submission`, or if the ledger's cumulative total plus that estimate exceeds `max_usd_total`. The ledger, `runs/spend_ledger.json`, records every batch ever submitted (every step, attempt and pilot, including ones whose run files were later cleared); keep it cumulative and complete, and never edit or prune it by hand.
- **The API key is `GLP_SIM_API_KEY`, and the client is pinned to `https://api.anthropic.com`.** The cloud runtime strips `ANTHROPIC_API_KEY` from the session and sets its own `ANTHROPIC_BASE_URL`, which the `anthropic` SDK would otherwise follow silently, sending the key somewhere other than the public API. So `glpsim/runner.py: get_client()` is the only place the client is built: `anthropic.Anthropic(api_key=os.environ["GLP_SIM_API_KEY"], base_url="https://api.anthropic.com")`. It fails with a clear error, and submits nothing, if `GLP_SIM_API_KEY` is absent. Never build a client any other way, and never rely on the SDK's own environment lookup.
- **No secrets in the repo, no secrets in the transcript.** `GLP_SIM_API_KEY` comes from the cloud environment's variables and is read only by `get_client()`, which hands it straight to the `anthropic` client. Never print, log, echo, `env`-dump or commit environment variables, never write the key to a file, and never paste it into a prompt or a batch request body. The key belongs to a dedicated, spend-capped workspace and is revoked when the run is complete. `.gitignore` already excludes `.env`.
- **Dry-run first.** `generate` and `judge` accept `--dry-run`, which renders every prompt and writes the batch as `runs/stepN/_batch.jsonl` without submitting, so the whole pipeline can be built and tested with no key present.
- **Commit after every completed step** (`runs/`, `world/`, `lineage.md`). The lineage is the product.

## Repo layout

```
CLAUDE.md               this file
METHOD.md               the simulation spec — read first
config/sim.json         N, beam, steps, axis rotation, plausibility floor, models, cost cap
config/drivers.json     the stochastic drivers and their distributions
schema/world_state.schema.json
schema/run.schema.json
prompts/generate.md     generation prompt template ({{placeholders}})
prompts/judge.md        judge prompt template + rubric
data/step0_baseline.json   researched Nov-2026 world state
data/step0_sources.md      sources for every step-0 fact
world/                  stepN.json per surviving lineage (written by select)
runs/                   stepN/<lineage>/<run_id>.json (written by generate + judge)
runs/spend_ledger.json  every batch submitted, ever, with estimate and actual cost
lineage.md              human-readable ancestry of every surviving world
report/                 final per-lineage dossiers (written by report)
```

## Working style

Build `validate` and `select` first (pure, testable, no API). Then `generate` and
`judge` against a `--dry-run` that renders prompts to `runs/_dry/` without submitting.
Run step 1 with `--n 5` before `--n 50`. Keep functions small; one module per command
is fine. Tests in `tests/` with pytest for: driver drawing determinism, schema
validation, the selection rule (including the plausibility floor and tie-breaks),
and prompt rendering.
