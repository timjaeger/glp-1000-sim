# Repair prompt — one attempt per failed response

Sent by `sim.py generate` / `sim.py judge` when a response fails local
validation against `schema/`. It follows the original user message and the
model's previous (invalid) response as a third turn. At most one repair per
run; a run that still fails is written with `"status": "invalid"`.

---

## System

(unused — the original request's system prompt is reused)

## User

Your previous response did not pass validation against the required schema.
The problems, as `json/path: message`:

{{errors}}

Return the complete corrected JSON object — every field, not only the ones
that changed. Keep everything that was already valid as it was; change only
what is needed to fix the problems listed.
