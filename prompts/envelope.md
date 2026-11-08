# Magnitude envelope — shared block

Rendered once per run by `glpsim/render.py: magnitude_envelope()` and inserted,
identically, into the generation prompt (`{{magnitude_envelope}}` in
`prompts/generate.md`) and the judge prompt (`prompts/judge.md`). It is derived
only from the starting world and the run's drawn drivers, both of which the
judge already sees, so judge independence (METHOD §6) is unchanged. The judge's
`magnitude` sub-axis is scored against it.

---

### Magnitude envelope ({{parent_year}} → {{target_year}})

Derived from the starting world and the drawn drivers. Movement inside this
envelope is stipulated; movement outside it is a flaw.

**Population.**

- `us_adults_on_drug_pct`: parent {{parent_on_drug_pct}} + `adoption_delta_pp`
  {{adoption_delta_pp}}, ±2: between **{{current_use_low}}** and
  **{{current_use_high}}**.
- `us_adults_ever_used_pct`: rises by at most `adoption_delta_pp` + 3
  ({{ever_rise_max}} points) and never falls: between
  **{{parent_ever_used_pct}}** and **{{ever_use_max}}**.
- `cycled_off_and_on_pct` (share of ever-users who stopped and restarted) is
  reconciled to the gap: ever − current is the share of adults who used and are
  off now. Together with the restarters among current users, it fits the
  starting world's persistence and restart figures. The arithmetic is one line
  of `population.note`.
- `by_income_third_pct`, where figures are given, brackets the national figure:
  the lowest third at or below `us_adults_on_drug_pct`, the highest at or above.

**Approvals**, from the starting world's `drugs.pipeline_note`, product by
product:

- Under FDA review at the start: may be approved in this window.
- In phase 3: approved no earlier than 12 months after its stated filing. If no
  filing is stated, the filing is itself an event in this window, and approval
  comes no earlier than 12 months after it.
- In phase 2 or earlier, or only "in development": not on the US market at the
  end of {{target_year}}.
- No US generic semaglutide or tirzepatide before 2031 (`access.generic_us`
  stays false), unless `price_path` is `generic_collapse` and the mechanism (the
  settlement, ruling or authorised generic) is one of the `events`.
- A driver that calls for a launch these rules forbid is realised with what they
  allow (the filing, a priority review, a launch outside the US, or an existing
  product in a new form), and `pipeline_note` says so. That counts as honouring
  the driver.

**Reconciliation.** Coverage shares, public spending and subscriber or user
counts are consistent with the population figures and with each other. A share
of fills paid publicly, the number of users that implies, the price and any
spending or budget-score figure must multiply out. A subscriber, member or
programme count must fit inside the user population it is drawn from. Where a
spending or budget figure is given, its arithmetic is shown in the relevant note.
