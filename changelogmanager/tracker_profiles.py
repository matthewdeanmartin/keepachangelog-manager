# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Map task fragments to/from issue-tracker objects (GitHub, GitLab).

The on-disk fragment format is identical regardless of tracker; a *profile*
only governs how head fields map onto an issue payload and back. Fields a
profile does not map fall through to / come from the fragment's ``custom`` bag,
so a GitLab-only field like ``Weight`` survives under the GitHub profile without
the app barfing.

See ``spec/TASK_FRAGMENTS_AND_UI.md`` ("Issue-tracker fields, out of the box").
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from changelogmanager.task_fragments import TaskFragment

PROFILES = ("github", "gitlab")


def _state_from_status(status: str) -> tuple[str, str | None]:
    """GitHub-style (state, state_reason) from a fragment status."""

    lowered = status.strip().lower()
    if lowered == "done":
        return "closed", "completed"
    if lowered == "wontfix":
        return "closed", "not_planned"
    return "open", None


def _status_from_state(state: str, reason: str | None) -> str:
    if state == "closed":
        return "wontfix" if reason == "not_planned" else "done"
    return "in-progress"


def fragment_to_issue(
    fragment: TaskFragment, profile: str = "github"
) -> dict[str, Any]:
    """Serialize a fragment to an issue payload for the given tracker."""

    if profile not in PROFILES:
        raise ValueError(f"unknown tracker profile {profile!r}")

    if profile == "github":
        state, reason = _state_from_status(fragment.status)
        payload: dict[str, Any] = {
            "title": fragment.title,
            "body": fragment.body_md.strip("\n"),
            "state": state,
            "labels": list(fragment.labels),
            "assignees": list(fragment.assignees),
        }
        if reason is not None:
            payload["state_reason"] = reason
        if fragment.milestone:
            payload["milestone"] = fragment.milestone
        return payload

    # gitlab
    gitlab_payload: dict[str, Any] = {
        "title": fragment.title,
        "description": fragment.body_md.strip("\n"),
        "state": (
            "closed" if fragment.checked or fragment.status == "wontfix" else "opened"
        ),
        "labels": ",".join(fragment.labels),
        "assignees": list(fragment.assignees),
    }
    if fragment.milestone:
        gitlab_payload["milestone"] = fragment.milestone
    # GitLab-specific fields are stored in custom; promote the ones we know.
    weight = fragment.custom.get("Weight")
    if weight is not None:
        gitlab_payload["weight"] = _maybe_int(weight)
    due = fragment.custom.get("Due Date")
    if due is not None:
        gitlab_payload["due_date"] = due
    confidential = fragment.custom.get("Confidential")
    if confidential is not None:
        gitlab_payload["confidential"] = confidential.strip().lower() in {
            "true",
            "yes",
            "1",
        }
    return gitlab_payload


def issue_to_fragment(
    issue: Mapping[str, Any], *, task_id: str, profile: str = "github"
) -> TaskFragment:
    """Build a fragment from an issue object. Unmapped fields go to ``custom``."""

    if profile not in PROFILES:
        raise ValueError(f"unknown tracker profile {profile!r}")

    if profile == "github":
        status = _status_from_state(
            str(issue.get("state", "open")), issue.get("state_reason")
        )
        labels = [_label_name(item) for item in issue.get("labels", [])]
        assignees = [_user_login(item) for item in issue.get("assignees", [])]
        milestone = _milestone_title(issue.get("milestone"))
        body = str(issue.get("body") or "")
        number = issue.get("number")
        tracker = f"github#{number}" if number is not None else None
    else:  # gitlab
        state = str(issue.get("state", "opened"))
        status = "done" if state == "closed" else "in-progress"
        raw_labels = issue.get("labels", [])
        labels = (
            _split_labels(raw_labels)
            if isinstance(raw_labels, str)
            else [str(item) for item in raw_labels]
        )
        assignees = [_user_username(item) for item in issue.get("assignees", [])]
        milestone = _milestone_title(issue.get("milestone"))
        body = str(issue.get("description") or "")
        iid = issue.get("iid")
        tracker = f"gitlab#{iid}" if iid is not None else None

    fragment = TaskFragment(
        task_id=task_id,
        title=str(issue.get("title", task_id)),
        category="added",
        status=status,
        tracker=tracker,
        labels=[item for item in labels if item],
        assignees=[item for item in assignees if item],
        milestone=milestone,
        body_md=body,
    )

    if profile == "gitlab":
        if "weight" in issue and issue["weight"] is not None:
            fragment.custom["Weight"] = str(issue["weight"])
        if issue.get("due_date"):
            fragment.custom["Due Date"] = str(issue["due_date"])
        if "confidential" in issue:
            fragment.custom["Confidential"] = str(bool(issue["confidential"])).lower()
    return fragment


def _maybe_int(value: str) -> int | str:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _split_labels(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _label_name(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("name", ""))
    return str(item)


def _user_login(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("login", ""))
    return str(item)


def _user_username(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("username", ""))
    return str(item)


def _milestone_title(item: Any) -> str | None:
    if isinstance(item, Mapping):
        return item.get("title")
    if item:
        return str(item)
    return None
