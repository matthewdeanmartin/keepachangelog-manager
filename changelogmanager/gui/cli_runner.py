# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Run the changelogmanager CLI in-process and capture its output.

Screens that drive batch/remote commands (backfill, releases, components) reuse
this rather than re-implementing argument plumbing. The interactive editor talks
to the :class:`~changelogmanager.changelog.Changelog` model directly instead.
"""

from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout

from changelogmanager.cli import main as cli_main
from changelogmanager.runtime_logging import get_logger

logger = get_logger(__name__)


def run_cli(argv: list[str]) -> tuple[int, str]:
    """Invoke the CLI in-process, capturing stdout+stderr.

    Returns ``(exit_code, combined_output)``.
    """

    logger.info("Running embedded CLI command: %s", " ".join(argv))
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        try:
            code = cli_main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Embedded CLI command crashed")
            traceback.print_exc()
            code = 1
    return code, buffer.getvalue()
