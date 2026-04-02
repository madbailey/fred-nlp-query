from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("intent-evals")
    group.addoption(
        "--run-evals",
        action="store_true",
        default=False,
        help="Run live OpenAI-backed intent evals.",
    )
    group.addoption(
        "--eval-model",
        action="store",
        default=None,
        help="Override the OpenAI model used by live intent evals.",
    )
    group.addoption(
        "--eval-reasoning-effort",
        action="store",
        default=None,
        help="Override the OpenAI reasoning effort used by live intent evals.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-evals"):
        return

    skip_live_evals = pytest.mark.skip(reason="live intent evals require --run-evals")
    for item in items:
        if "evals" in item.keywords:
            item.add_marker(skip_live_evals)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    if config.getoption("--run-evals"):
        return False

    normalized_path = str(collection_path).replace("\\", "/")
    return "/tests/evals/" in normalized_path
