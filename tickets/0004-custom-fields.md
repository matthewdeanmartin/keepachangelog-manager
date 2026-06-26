# 0004-custom-fields — Custom head fields without barfing

- **Category:** added
- **Status:** proposed
- **Tracker:** github#4
- **Labels:** tasks, schema, interop
- **Story Points:** 3
- **Epic:** EP-tasks

---

## Goal

Guarantee any head key the parser doesn't recognize is captured, not rejected.
"No two teams are alike."

This fragment carries two custom fields (`Story Points`, `Epic`) so the
round-trip test has real data to chew on.

## Acceptance criteria

- [ ] Unknown `- **Key:** value` pairs land in `TaskFragment.custom`.
- [ ] Original key casing preserved; insertion order preserved.
- [ ] `render(parse(text))` round-trips custom fields losslessly.
- [ ] No unknown key, however weird, raises.

## Notes

Depends on [[0001-fragment-parser]]. Hypothesis property: random `Key: value`
heads survive a parse → render → parse cycle unchanged.
