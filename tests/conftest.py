"""Safety net: tests may only create/delete graphs whose name starts with 'test:'."""
import uuid

import pytest

from app.db import get_client


@pytest.fixture
def test_graph():
    name = f"test:{uuid.uuid4().hex[:8]}"
    assert name.startswith("test:")
    g = get_client().select_graph(name)
    try:
        yield g
    finally:
        try:
            g.delete()
        except Exception:
            pass  # graph may never have been created


@pytest.fixture(scope="module")
def seeded_graph():
    """One seeded 'test:' graph shared by a test module, deleted at the end."""
    from app.seed import seed_graph

    name = f"test:seed-{uuid.uuid4().hex[:8]}"
    assert name.startswith("test:")
    seed_graph(name)
    g = get_client().select_graph(name)
    try:
        yield g
    finally:
        try:
            g.delete()
        except Exception:
            pass
