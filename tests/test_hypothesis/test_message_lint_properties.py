"""Property tests pinning message-lint and backfill classification in lockstep.

The whole feature rests on one invariant: a subject the linter calls
``UNCLASSIFIED`` is exactly a subject ``backfill.classify_commit_subject``
cannot classify (returns ``None``) -- modulo the ``SKIP`` refinement (recognized
non-changelog types) and the ``allow_unknown_conventional_types`` escalation. If
backfill's parsers ever change, this test fails before the hook can start
accepting commits backfill can't actually use.
"""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from changelogmanager import backfill
from changelogmanager.message_lint import (
    LintOptions,
    LintOutcome,
    classify_subject,
    is_exempt,
)

SCHEMAS = ["auto", "conventional", "gitmoji", "keepachangelog"]

# A broad subject generator: random prose, conventional-ish prefixes, KAC
# prefixes, gitmoji, and known skip types, so the equivalence is exercised
# across all three outcomes.
kac_prefixes = st.sampled_from(
    ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
)
conventional_types = st.sampled_from(sorted(backfill.CONVENTIONAL_TO_KAC))
gitmoji = st.sampled_from(sorted(backfill.GITMOJI_TO_KAC))
prose = st.text(alphabet=string.ascii_letters + string.digits + " ._/-", max_size=40)

subjects = st.one_of(
    prose,
    st.builds(lambda p, b: f"{p}: {b}", kac_prefixes, prose),
    st.builds(lambda t, b: f"{t}: {b}", conventional_types, prose),
    st.builds(lambda e, b: f"{e} {b}", gitmoji, prose),
    st.builds(lambda w, b: f"{w}: {b}", st.text(string.ascii_lowercase, min_size=1, max_size=8), prose),
)


@given(subject=subjects, schema=st.sampled_from(SCHEMAS))
def test_lint_unclassified_iff_backfill_cannot_classify(subject, schema):
    # Escalate unknown conventional types so the linter's CHANGELOG outcomes line
    # up 1:1 with backfill's non-None classifications (no UNCLASSIFIED escalation
    # of subjects backfill would happily map to "changed").
    opts = LintOptions(schema=schema, allow_unknown_conventional_types=True)
    result = classify_subject(subject, options=opts)
    backfill_result = backfill.classify_commit_subject(subject, schema=schema)

    if result.outcome is LintOutcome.SKIP:
        # SKIP is the linter's refinement; backfill has no equivalent, so it is
        # exempt from the equivalence (it never becomes a changelog entry).
        return

    if result.outcome is LintOutcome.CHANGELOG:
        assert backfill_result is not None
        assert result.change_type == backfill_result[0]
    else:
        assert result.outcome is LintOutcome.UNCLASSIFIED
        assert backfill_result is None


@given(subject=subjects, schema=st.sampled_from(SCHEMAS))
def test_passing_subjects_never_crash_and_have_consistent_fields(subject, schema):
    result = classify_subject(subject, schema=schema)
    if result.outcome is LintOutcome.CHANGELOG:
        assert result.change_type is not None
    else:
        assert result.change_type is None
    # ok is precisely "not unclassified".
    assert result.ok == (result.outcome is not LintOutcome.UNCLASSIFIED)


@given(
    subject=st.builds(
        lambda kw, b: f"{kw} {b}",
        st.sampled_from(["Merge", "Revert", "fixup!", "squash!", "Bump version"]),
        # Real merge/revert/fixup subjects always carry trailing content; the
        # default exempt anchors include a trailing space, so generate non-empty.
        prose.filter(lambda value: value.strip()),
    )
)
def test_default_exempt_subjects_are_skipped(subject):
    opts = LintOptions()
    assert is_exempt(subject, opts)
    assert classify_subject(subject, options=opts).outcome is LintOutcome.SKIP
