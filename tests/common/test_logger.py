import logging

import pytest

from itunes_tools.common.logger import get_logger


@pytest.fixture
def logger_name(request: pytest.FixtureRequest):
    """Give each test its own logger name and remove its handlers afterwards.

    Loggers are process-wide singletons, so without this, handlers leak between tests.
    """
    name = f"test.{request.node.name}"
    yield name
    logging.getLogger(name).handlers.clear()


def test_get_logger_returns_named_logger(logger_name):
    assert get_logger(logger_name).name == logger_name


def test_get_logger_defaults_to_debug(logger_name, monkeypatch):
    monkeypatch.delenv("ITUNES_TOOLS_LOG_LEVEL", raising=False)

    assert get_logger(logger_name).level == logging.DEBUG


def test_get_logger_reads_level_from_environment(logger_name, monkeypatch):
    monkeypatch.setenv("ITUNES_TOOLS_LOG_LEVEL", "WARNING")

    assert get_logger(logger_name).level == logging.WARNING


def test_get_logger_adds_formatted_stream_handler(logger_name):
    handlers = get_logger(logger_name).handlers

    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    assert handlers[0].formatter._fmt == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def test_get_logger_twice_does_not_duplicate_handlers(logger_name):
    get_logger(logger_name)

    assert len(get_logger(logger_name).handlers) == 1


def test_get_logger_twice_logs_each_message_once(logger_name, capsys):
    get_logger(logger_name)
    get_logger(logger_name).info("hello")

    assert capsys.readouterr().err.count("hello") == 1


def test_get_logger_adds_handler_even_when_root_has_one(logger_name):
    root = logging.getLogger()
    root_handler = logging.NullHandler()
    root.addHandler(root_handler)
    try:
        assert len(get_logger(logger_name).handlers) == 1
    finally:
        root.removeHandler(root_handler)
