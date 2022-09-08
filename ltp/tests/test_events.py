"""
Unittest for events module.
"""
import pytest
import ltp.events


@pytest.fixture(autouse=True, scope="function")
def setup():
    """
    Setup events before test.
    """
    ltp.events.reset()


def test_reset():
    """
    Test reset method.
    """
    def funct():
        pass

    ltp.events.register("myevent", funct)
    assert ltp.events.is_registered("myevent")

    ltp.events.reset()
    assert not ltp.events.is_registered("myevent")


def test_register_errors():
    """
    Test register method during errors.
    """
    def funct():
        pass

    with pytest.raises(ValueError):
        ltp.events.register(None, funct)

    with pytest.raises(ValueError):
        ltp.events.register("myevent", None)


def test_register():
    """
    Test register method.
    """
    def funct():
        pass

    ltp.events.register("myevent", funct)
    assert ltp.events.is_registered("myevent")


def test_unregister_errors():
    """
    Test unregister method during errors.
    """
    with pytest.raises(ValueError):
        ltp.events.unregister(None)


def test_unregister():
    """
    Test unregister method.
    """
    def funct():
        pass

    ltp.events.register("myevent", funct)
    assert ltp.events.is_registered("myevent")

    ltp.events.unregister("myevent")
    assert not ltp.events.is_registered("myevent")


def test_fire_errors():
    """
    Test fire method during errors.
    """
    with pytest.raises(ValueError):
        ltp.events.fire(None, "prova")


def test_fire():
    """
    Test fire method.
    """
    called = []

    def funct(param):
        called.append(param)

    ltp.events.register("myevent", funct)
    assert ltp.events.is_registered("myevent")

    for i in range(1000):
        ltp.events.fire("myevent", f"index{i}")

    for i in range(1000):
        assert called[i] == f"index{i}"
