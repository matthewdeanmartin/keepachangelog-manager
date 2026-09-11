"""Changelog-owned release intent and PEP 440 prerelease progression."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, UNRELEASED_ENTRY, VersionCore
from changelogmanager.versioning import VersionValue, bump_version, parse_version

PHASES = {"alpha": "a", "beta": "b", "rc": "rc", "dev": ".dev", "final": ""}
PLAN_KEY = "release_plan"


def validate_plan(plan: Mapping[str, str], scheme: str) -> dict[str, str]:
    if scheme != "pep440":
        raise logging.Error(
            message='Release metadata requires versioning.scheme = "pep440"; existing SemVer and CalVer workflows are unchanged'
        )
    if set(plan) - {"phase", "target"}:
        raise logging.Error(message="Release metadata supports only Phase and Target")
    phase = plan.get("phase", "").strip().lower()
    if phase not in PHASES:
        raise logging.Error(
            message="Release Phase must be alpha, beta, rc, dev, or final"
        )
    normalized = {"phase": phase}
    if "target" in plan:
        try:
            target = parse_version(plan["target"], "pep440")
        except ValueError as exc:
            raise logging.Error(
                message=f"Invalid PEP 440 Release Target: {plan['target']}"
            ) from exc
        if (
            target.parsed.is_prerelease
            or target.parsed.is_postrelease
            or target.parsed.local
        ):
            raise logging.Error(
                message="Release Target must be the final numeric version (for example 1.4.0); Phase supplies the suffix"
            )
        normalized["target"] = str(target)
    return normalized


def extract_plan(
    text: str, scheme: str, file_path: str
) -> tuple[str, dict[str, str] | None, list[logging.Error]]:
    """Remove a Release block for the base KACL parser, retaining line numbers.

    Accept top-level ## Release before history, or ### Release in Unreleased.
    Only fields in this one block are interpreted as release instructions.
    """
    lines = text.splitlines(keepends=True)
    clean = list(lines)
    errors: list[logging.Error] = []
    fields: dict[str, str] = {}
    block_line: int | None = None
    active = False
    current: str | None = None
    seen_history = False
    seen_unreleased = False

    def error(index: int, message: str) -> None:
        errors.append(
            logging.Error(
                file_path=file_path,
                line_number=logging.Range(start=index + 1),
                line=lines[index],
                message=message,
            )
        )

    for index, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            depth, label = len(heading[1]), heading[2]
            active = False
            if label.lower() == "release" and depth in {2, 3}:
                if block_line is not None:
                    error(index, "Only one Release section is allowed")
                block_line = index if block_line is None else block_line
                if seen_history or (depth == 3 and current != UNRELEASED_ENTRY):
                    error(
                        index,
                        "Release metadata belongs before released history, with [Unreleased]",
                    )
                active = True
                clean[index] = "\n"
                continue
            if depth == 2:
                current = (
                    UNRELEASED_ENTRY
                    if re.match(r"^\[unreleased\]", label, re.I)
                    else label
                )
                if current == UNRELEASED_ENTRY:
                    seen_unreleased = True
                else:
                    seen_history = True
        if active:
            clean[index] = "\n"
            if not line.strip():
                continue
            field = re.fullmatch(
                r"[-*+]\s+(Phase|Target):\s*(\S.*?)\s*", line.strip(), re.I
            )
            if not field:
                error(
                    index,
                    "Use '- Phase: alpha' and an optional '- Target: 1.4.0' in Release metadata",
                )
                continue
            key = field[1].lower()
            if key in fields:
                error(index, f"Duplicate Release field: {field[1]}")
            fields[key] = field[2]
    if block_line is None:
        return text, None, errors
    if not seen_unreleased:
        error(block_line, "Release metadata requires an [Unreleased] section")
    try:
        plan = validate_plan(fields, scheme)
    except logging.Error as exc:
        error(block_line, exc.message)
        plan = None
    return "".join(clean), plan, errors


def get_plan(data: Mapping[str, Any]) -> dict[str, str] | None:
    return cast(
        dict[str, str] | None,
        data.get(UNRELEASED_ENTRY, {}).get("metadata", {}).get(PLAN_KEY),
    )


def render_plan(text: str, plan: Mapping[str, str] | None) -> str:
    if plan is None:
        return text
    block = f"## Release\n- Phase: {plan['phase']}\n"
    if "target" in plan:
        block += f"- Target: {plan['target']}\n"
    return text.replace("## [Unreleased]", block + "\n## [Unreleased]", 1)


def phase_of(version: VersionValue) -> str:
    parsed = version.parsed
    if parsed.dev is not None:
        return "dev"
    if parsed.pre:
        return {"a": "alpha", "b": "beta", "rc": "rc"}[parsed.pre[0]]
    return "final"


def change_bump(entries: Mapping[str, Any]) -> VersionCore | None:
    bumps = [
        category.bump for name, category in CATEGORIES.items() if entries.get(name)
    ]
    return max(bumps, key=lambda bump: bump.value) if bumps else None


def suggest_pep440(data: Mapping[str, Any], initial: VersionValue) -> VersionValue:
    """Choose a target and counter exclusively from recorded changelog history."""
    raw_plan = get_plan(data)
    plan = validate_plan(raw_plan, "pep440") if raw_plan is not None else {}
    history = [
        parse_version(version, "pep440")
        for version in data
        if version != UNRELEASED_ENTRY
    ]
    latest = history[0] if history else None
    active = latest is not None and latest.parsed.is_prerelease
    bump = change_bump(data.get(UNRELEASED_ENTRY, {}))
    if not latest and not plan:
        return initial
    phase = plan.get("phase", phase_of(latest) if active and latest else "final")
    if "target" in plan:
        target = parse_version(plan["target"], "pep440")
    elif active and latest:
        target = parse_version(latest.parsed.base_version, "pep440")
    elif latest:
        target = bump_version(latest, bump or VersionCore.PATCH)
    else:
        target = parse_version(initial.parsed.base_version, "pep440")

    # New changes in an active series do not repeatedly increment its target.
    # Check required magnitude against the stable baseline when it is known.
    baseline = next(
        (item for item in history if not item.parsed.is_prerelease and item < target),
        None,
    )
    if bump and baseline and bump_version(baseline, bump) > target:
        needed = bump_version(baseline, bump)
        raise logging.Error(
            message=f"Changes require at least {needed}, beyond the active target {target}; set Release Target explicitly to {needed} or later"
        )

    if phase == "final":
        if (
            active
            and latest
            and bump is None
            and target != parse_version(latest.parsed.base_version, "pep440")
        ):
            raise logging.Error(
                message="Finalization without change entries must use the active prerelease Target"
            )
        candidate = target
    else:
        same_phase = [
            item
            for item in history
            if parse_version(item.parsed.base_version, "pep440") == target
            and phase_of(item) == phase
        ]
        if phase == "dev":
            # Combined rcN.devN histories cannot be advanced as plain .devN.
            if any(item.parsed.pre or item.parsed.post for item in same_phase):
                raise logging.Error(
                    message="Combined development versions require an explicit version override; Phase: dev produces Target.devN"
                )
            numbers = [item.parsed.dev for item in same_phase]
        else:
            numbers = [item.parsed.pre[1] for item in same_phase]
        number = max(numbers, default=0) + 1
        candidate = parse_version(f"{target}{PHASES[phase]}{number}", "pep440")
    if latest and candidate <= latest:
        raise logging.Error(
            message=f"Release plan produces {candidate}, which does not advance {latest}; choose a later Phase or Target"
        )
    return candidate


def validate_override(plan: Mapping[str, str] | None, version: VersionValue) -> None:
    if plan is None:
        return
    normalized = validate_plan(plan, version.scheme)
    if phase_of(version) != normalized["phase"]:
        raise logging.Error(
            message=f"Version {version} conflicts with Release Phase: {normalized['phase']}"
        )
    if "target" in normalized and parse_version(
        normalized["target"], "pep440"
    ) != parse_version(version.parsed.base_version, "pep440"):
        raise logging.Error(
            message=f"Version {version} conflicts with Release Target: {normalized['target']}"
        )


def is_finalization(version: str, history: Sequence[str], scheme: str) -> bool:
    if scheme != "pep440":
        return False
    current = parse_version(version, scheme)
    return (
        not current.parsed.is_prerelease
        and not current.parsed.is_postrelease
        and any(
            previous.parsed.is_prerelease
            and parse_version(previous.parsed.base_version, scheme) == current
            for previous in (parse_version(item, scheme) for item in history)
        )
    )
