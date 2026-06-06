import argparse

from changelogmanager.cli import config_resolve


def test_apply_config_defaults_only_updates_builtin_defaults(monkeypatch):
    seen_configs = []

    def error_options(config):
        seen_configs.append(config)
        return {"error_format": "github"}

    monkeypatch.setattr(
        config_resolve,
        "CONFIG_DEFAULTS",
        (
            ("error_format", error_options, "error_format", "llvm"),
            (
                "commit_schema",
                lambda _config: {"commit_schema": "keepachangelog"},
                "commit_schema",
                "auto",
            ),
            (
                "missing_attr",
                lambda _config: {"missing_attr": "x"},
                "missing_attr",
                None,
            ),
        ),
    )

    args = argparse.Namespace(error_format="llvm", commit_schema="manual")

    config_resolve.apply_config_defaults(args, "changelogmanager.toml")

    assert args.error_format == "github"
    assert args.commit_schema == "manual"
    assert seen_configs == ["changelogmanager.toml"]


def test_config_source_text_prefers_explicit_then_detected_then_defaults():
    assert (
        config_resolve.config_source_text(
            argparse.Namespace(config="explicit.toml"), "resolved.toml"
        )
        == "explicit --config (resolved.toml)"
    )
    assert (
        config_resolve.config_source_text(argparse.Namespace(config=None), "auto.toml")
        == "auto-detected (auto.toml)"
    )
    assert (
        config_resolve.config_source_text(argparse.Namespace(config=None), None)
        == "built-in defaults"
    )


def test_resolved_config_path_returns_only_strings():
    assert (
        config_resolve.resolved_config_path(
            argparse.Namespace(resolved_config_path="changelogmanager.toml")
        )
        == "changelogmanager.toml"
    )
    assert (
        config_resolve.resolved_config_path(
            argparse.Namespace(resolved_config_path=object())
        )
        is None
    )
