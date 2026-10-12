"""Shared test fixtures."""

import sys
from pathlib import Path

import pytest

# Make the HA-independent API module importable as ``api``.
sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "mojekino"))

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    """Load custom_components."""
    return
