# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Manager module."""

import sys

from changelogmanager import cli


def main() -> None:
    """Entrypoint."""

    sys.exit(cli.main())


if __name__ == "__main__":
    main()
