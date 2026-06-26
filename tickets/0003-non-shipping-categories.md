# 0003-non-shipping-categories — Non-shipping categories & shipping flag

- **Category:** added
- **Status:** proposed
- **Tracker:** github#3
- **Labels:** tasks, schema

---

## Goal

Extend `change_types.py` so categories carry a `ships_to_changelog` flag, reuse
the six KAC `CATEGORIES` as shipping, and add non-shipping types
(`internal`, `chore`, `docs`, `test`, `spike`).

## Acceptance criteria

- [ ] `Category` gains `ships_to_changelog: bool = True` (existing six default True).
- [ ] `NON_SHIPPING` table with the five non-shipping types; `ALL_CATEGORIES`
      merges both.
- [ ] `tasks assemble --changelog` and `fragments collect` skip any category whose
      `ships_to_changelog` is False.
- [ ] **Unknown category values are kept**, rendered under their own heading, and
      default to non-shipping (never silently reach `CHANGELOG.md`).

---

## Why default unknown → non-shipping

Safer failure mode: a typo'd or team-custom category must never leak into a
user-facing changelog by accident. Teams opt a custom category *in* by adding it
to the table with `ships_to_changelog=True`.
