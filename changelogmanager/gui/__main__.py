# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Allow ``python -m changelogmanager.gui`` for ad-hoc launches."""

import sys

from changelogmanager.gui import run_gui

if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_gui())
