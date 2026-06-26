# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Manager module."""

import sys

from changelogmanager import cli


def main() -> None:
    """Entrypoint."""

    sys.exit(cli.main())


def gui_main() -> None:
    """Entrypoint for the ``kacl-gui`` console script: launch the GUI directly.

    ``kacl-gui gui`` was an awkward command (the script name implied the GUI yet
    still required the ``gui`` subcommand). This entrypoint skips argparse and
    opens the Tkinter GUI straight away.
    """

    from changelogmanager.gui import run_gui  # noqa: PLC0415

    sys.exit(run_gui())


if __name__ == "__main__":
    main()
