import changelogmanager.__main__ as main_module


def test_main_exits_with_cli_return_code(monkeypatch):
    captured = {}

    monkeypatch.setattr(main_module.cli, "main", lambda: 7)
    monkeypatch.setattr(
        main_module.sys, "exit", lambda code: captured.setdefault("code", code)
    )

    main_module.main()

    assert captured["code"] == 7
