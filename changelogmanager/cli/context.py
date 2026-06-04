# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""CLI presentation primitives: the shared context object and output helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger

logger = get_logger(__name__)


@dataclass
class CliContext:
    """CLI context shared across commands."""

    changelog: Changelog
    quiet: bool = False
    json_output: bool = False
    json_payload: dict[str, Any] = field(default_factory=dict)


def emit(
    ctx: CliContext,
    *,
    text: str | None = None,
    json_key: str | None = None,
    json_value: Any = None,
) -> None:
    """Prints text unless --quiet, and accumulates JSON payload."""

    if json_key is not None:
        ctx.json_payload[json_key] = json_value
    if ctx.quiet or ctx.json_output:
        if text is not None:
            logger.log(VERBOSE, "Suppressing human-readable output: %s", text)
        return
    if text is not None:
        print(text)


def print_dry_run(ctx: CliContext, message: str) -> None:
    """Reports that a command ran in dry-run mode."""

    logger.info("Dry-run: %s", message)
    emit(ctx, text=f"Dry run: {message}", json_key="dry_run", json_value=message)
