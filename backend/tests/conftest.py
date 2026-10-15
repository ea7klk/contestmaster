import pytest

from backend.app.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_process_local_rate_limits():
    limiter.clear()
    yield
    limiter.clear()
