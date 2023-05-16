"""
Unittest for events module.
"""
import asyncio
import pytest
import altp


pytestmark = pytest.mark.asyncio


def test_reset():
    """
    Test reset method.
    """
    async def funct():
        pass

    altp.events.register("myevent", funct)
    assert altp.events.is_registered("myevent")

    altp.events.reset()
    assert not altp.events.is_registered("myevent")


def test_register_errors():
    """
    Test register method during errors.
    """
    async def funct():
        pass

    with pytest.raises(ValueError):
        altp.events.register(None, funct)

    with pytest.raises(ValueError):
        altp.events.register("myevent", None)


def test_register():
    """
    Test register method.
    """
    async def funct():
        pass

    altp.events.register("myevent", funct)
    assert altp.events.is_registered("myevent")


def test_unregister_errors():
    """
    Test unregister method during errors.
    """
    with pytest.raises(ValueError):
        altp.events.unregister(None)


def test_unregister():
    """
    Test unregister method.
    """
    async def funct():
        pass

    altp.events.register("myevent", funct)
    assert altp.events.is_registered("myevent")

    altp.events.unregister("myevent")
    assert not altp.events.is_registered("myevent")


async def test_fire_errors():
    """
    Test fire method during errors.
    """
    with pytest.raises(ValueError):
        await altp.events.fire(None, "prova")


async def test_fire():
    """
    Test fire method.
    """
    times = 100
    called = []

    async def diehard(error, name):
        assert error is not None
        assert name is not None

    async def tofire(param):
        called.append(param)

    async def start():
        await altp.events.start()

    async def run():
        for i in range(times):
            await altp.events.fire("myevent", i)

        while len(called) < times:
            await asyncio.sleep(1e-3)

        await altp.events.stop()

    altp.events.register("myevent", tofire)
    assert altp.events.is_registered("myevent")

    altp.events.register("internal_error", diehard)
    assert altp.events.is_registered("internal_error")

    altp.create_task(start())
    await run()

    while len(called) < times:
        asyncio.sleep(1e-3)

    called.sort()
    for i in range(times):
        assert called[i] == i
