"""
Generic stuff for pytest.
"""
import altp
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """
    Current event loop. Keep it in session scope, otherwise tests which
    will use same coroutines will be associated to different event_loop.
    In this way, pytest-asyncio plugin will work properly.
    """
    loop = altp.get_event_loop()

    yield loop

    if not loop.is_closed():
        loop.close()
