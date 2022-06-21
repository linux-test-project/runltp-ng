"""
Unittest for events module.
"""
import pytest
from ltp.events import SyncEventHandler

class _TestEventHandler:
    """
    Test EventHandlaer implementations.
    """

    @pytest.fixture
    def handler(self):
        """
        Fixture exposing EventHandler implementation.
        """
        raise NotImplementedError()

    def test_register_errors(self, handler):
        """
        Test register method during errors.
        """
        def funct():
            pass

        with pytest.raises(ValueError):
            handler.register(None, funct)

        with pytest.raises(ValueError):
            handler.register("myevent", None)

    def test_register(self, handler):
        """
        Test register method.
        """
        def funct():
            pass

        handler.register("myevent", funct)
        assert handler.is_registered("myevent")

    def test_unregister_errors(self, handler):
        """
        Test unregister method during errors.
        """
        with pytest.raises(ValueError):
            handler.unregister(None)

    def test_unregister(self, handler):
        """
        Test unregister method.
        """
        def funct():
            pass

        handler.register("myevent", funct)
        assert handler.is_registered("myevent")

    def test_fire_errors(self, handler):
        """
        Test fire method during errors.
        """
        with pytest.raises(ValueError):
            handler.fire(None, "prova")

    def test_fire(self, handler):
        """
        Test fire method.
        """
        def funct(_):
            pass

        handler.register("myevent", funct)
        assert handler.is_registered("myevent")

        called = []
        def funct2(param):
            called.append(param)

        handler.register("myevent", funct2)
        assert handler.is_registered("myevent")

        for i in range(1000):
            handler.fire("myevent", f"index{i}")

        for i in range(1000):
            assert called[i] == f"index{i}"


class TestSyncEventHandler(_TestEventHandler):
    """
    Test SyncEventHandler implementation.
    """

    @pytest.fixture
    def handler(self):
        return SyncEventHandler()
