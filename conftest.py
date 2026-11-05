"""Live service tests are opt-in; ordinary pytest never makes paid/network calls."""
import pytest
from dotenv import load_dotenv

load_dotenv()


def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False,
                     help="Run tests requiring live TigerGraph/LLM services (may write review case memory).")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="Live services: opt in with --run-integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
