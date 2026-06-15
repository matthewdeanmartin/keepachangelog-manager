"""Regression test: soft-wrapped (multi-line) entries must not be split.

A Keep a Changelog entry may be wrapped across several physical lines, with the
continuation lines indented under the bullet. The line-by-line parser used to
promote every continuation line into its own separate entry, which mangled the
rendered output (e.g. GitHub release bodies generated from the changelog).
"""

import io

from changelogmanager.vendor import keepachangelog

WRAPPED_CHANGELOG = """# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2018-06-01
### Added
- Initial release of `mastodon_mock`, a stateful FastAPI + SQLite mock of the Mastodon
  REST API, driveable by real clients including Mastodon.py.
- Auth & apps: app registration, `client_credentials` and `refresh_token` OAuth grants,
  token revocation, self-service account creation, and OAuth server metadata.
- Single line entry.
"""


def test_wrapped_entries_are_not_split():
    with io.StringIO(WRAPPED_CHANGELOG) as reader:
        result = keepachangelog.to_dict(reader)

    assert result["1.0.0"]["added"] == [
        "Initial release of `mastodon_mock`, a stateful FastAPI + SQLite mock of the "
        "Mastodon REST API, driveable by real clients including Mastodon.py.",
        "Auth & apps: app registration, `client_credentials` and `refresh_token` OAuth "
        "grants, token revocation, self-service account creation, and OAuth server "
        "metadata.",
        "Single line entry.",
    ]


def test_wrapped_entries_round_trip():
    """A wrapped entry survives a to_dict -> from_dict round-trip as one bullet."""
    with io.StringIO(WRAPPED_CHANGELOG) as reader:
        result = keepachangelog.to_dict(reader)

    rendered = keepachangelog.from_dict(result)

    # Each logical entry renders as exactly one bullet; the continuation text
    # stays on the same entry instead of becoming its own dangling bullet.
    assert rendered.count("\n- ") == 3
    assert "driveable by real clients including Mastodon.py." in rendered
    assert "\n- REST API" not in rendered
