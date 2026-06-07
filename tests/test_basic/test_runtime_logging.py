import logging as pylogging
import sys

import pytest

from changelogmanager import runtime_logging


def test_coerce_log_kwargs_accepts_defaults_and_valid_values():
    assert runtime_logging.coerce_log_kwargs({}) == (None, False, 1, None)

    error = RuntimeError("boom")
    exc_info = (RuntimeError, error, None)
    assert runtime_logging.coerce_log_kwargs(
        {
            "exc_info": exc_info,
            "stack_info": True,
            "stacklevel": 4,
            "extra": {"request_id": "123"},
        }
    ) == (exc_info, True, 4, {"request_id": "123"})


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"unknown": True}, "Unexpected logging keyword arguments"),
        ({"exc_info": "bad"}, "exc_info must be a bool, exception, or exc_info tuple"),
        ({"stack_info": "bad"}, "stack_info must be a bool"),
        ({"stacklevel": "bad"}, "stacklevel must be an int"),
        ({"extra": ["bad"]}, "extra must be a mapping"),
    ],
)
def test_coerce_log_kwargs_rejects_invalid_values(kwargs, message):
    with pytest.raises(TypeError, match=message):
        runtime_logging.coerce_log_kwargs(kwargs)


def test_install_verbose_level_adds_verbose_method_and_reuses_existing_method(
    monkeypatch,
):
    runtime_logging.install_verbose_level()

    logger = pylogging.getLogger("changelogmanager.tests.runtime")
    captured = {}

    def fake_log(self, level, message, *args, **kwargs):
        captured["level"] = level
        captured["message"] = message
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(pylogging.Logger, "log", fake_log)
    monkeypatch.setattr(logger, "isEnabledFor", lambda level: True)

    logger.verbose(
        "hello %s",
        "world",
        stack_info=True,
        stacklevel=4,
        extra={"request_id": "123"},
    )

    assert captured["level"] == runtime_logging.VERBOSE
    assert captured["message"] == "hello %s"
    assert captured["args"] == ("world",)
    assert captured["kwargs"]["exc_info"] is None
    assert captured["kwargs"]["stack_info"] is True
    assert captured["kwargs"]["stacklevel"] == 4
    assert captured["kwargs"]["extra"] == {"request_id": "123"}

    runtime_logging.install_verbose_level()
    assert pylogging.getLevelName(runtime_logging.VERBOSE) == "VERBOSE"


def test_configure_runtime_logging_disables_output_when_quiet():
    runtime_logging.configure_runtime_logging(info=False, verbose=False)

    logger = pylogging.getLogger(runtime_logging.LOGGER_NAME)

    assert logger.propagate is False
    assert logger.level == pylogging.CRITICAL + 1
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], pylogging.NullHandler)


def test_configure_runtime_logging_sets_expected_handler_and_levels():
    runtime_logging.configure_runtime_logging(info=True, verbose=False)

    logger = pylogging.getLogger(runtime_logging.LOGGER_NAME)
    assert logger.level == pylogging.INFO
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], pylogging.StreamHandler)
    assert logger.handlers[0].stream is sys.stderr
    assert logger.handlers[0].formatter._fmt == "[%(levelname)s] %(name)s: %(message)s"

    runtime_logging.configure_runtime_logging(info=False, verbose=True)

    assert logger.level == pylogging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], pylogging.StreamHandler)
