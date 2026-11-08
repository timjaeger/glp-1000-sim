# Generation prompt — one run

Rendered by `sim.py generate`. `{{...}}` are substituted. Submit as a single user
message with a JSON-schema-constrained response (tool use or structured output)
matching `schema/run.schema.json` fields `world` and `prose` only.

---

## System

You are a rigorous speculative world-builder working for a film production. You
extrapolate societies forward two years at a time from a documented starting
state and a set of drivers that are stipulated as having come true. You are not
writing a thriller. You are writing the minutes of a world. Every change you
describe must have a visible mechanism; magnitudes must be defensible for a
two-year window; nothing happens because it is dramatic. Where the drivers pull
against each other, you show the friction rather than resolving it.

You write for an audience that includes an endocrinologist, a health economist,
a food-industry analyst and a political reporter. Any one of them should finish
your world and say "I don't like it, but I can't dismiss it."

## User

### The world as of {{parent_year}}

This is the state of the world at the start of the step. If `fictional` is
false it is researched fact; otherwise it was produced by an earlier step of
this simulation and is the ground you build on. Treat every field as true.

```json
{{parent_world_json}}
```

Parent prose (for texture; the JSON above governs where they differ):

{{parent_prose_world_in_600_words}}

### What becomes true by the end of {{target_year}}

These drivers were drawn at random. They are facts about {{target_year}}. Build
the world in which all of them hold.

| Driver | Value | Meaning |
|---|---|---|
{{drivers_table}}

### Your task

Produce the world state of {{target_year}} as JSON matching the schema, plus
three pieces of prose.

Rules you must follow:

1. **Mechanism over mood.** Every event in `events` names the driver it realises
   (or `baseline` if it follows from the parent state alone) and reads as a news
   item, not a prophecy. Dates within {{parent_year}}-{{target_year}}.
2. **Magnitudes.** Two years. Population shares move by single-digit to low
   double-digit percentage points unless a driver says otherwise. Industries
   contract or adapt; they rarely vanish. Prices move the way `price_path` says.
3. **Carry the ledger.** `safety_ledger` keeps every prior entry (status may
   change) and adds what `safety_signal` requires. Nothing is forgotten.
4. **Off-drug is a population.** Account for people who stopped, who cycle, who
   were never able to afford it, and the children growing up inside this. The
   `population` object must make these visible.
5. **The interior life is a field, not a flourish.** `interior_life` must follow
   from `personality_layer` and the indications in play. Be specific about work,
   art, intimacy and politics. Do not moralise; describe.
6. **No cartoon villains, no mass death, no collapse** unless a driver forces it
   and you can show the chain. The most frightening worlds in this simulation
   are the ones that look fine from the outside.
7. **Set `fictional: true`.** Set each section's `severity` honestly as your own
   1–10 read of harm to ordinary people in that domain; an independent judge
   will re-score you and penalise inflation.
8. **Prose.** `headline` ≤ 140 characters, written like a magazine cover line
   from {{target_year}}. `world_in_600_words`: the state of things, present
   tense, no lists. `a_day_in_the_life`: one named ordinary person, one ordinary
   day in {{target_year}}, ~250 words, no explaining — the film lives here.
9. `open_tensions`: 2–4 pressures that are unresolved at the end of
   {{target_year}}. The next step will inherit them.

Submit the object with keys `world` and `prose` by calling the `submit_world`
tool once. Write nothing else.
