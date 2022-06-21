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

        def funct2():
            pass

        with pytest.raises(ValueError):
            handler.register("myevent", funct2)

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

        handler.unregister("myevent")
        assert not handler.is_registered("myevent")

    def test_link_errors(self, handler):
        """
        Test link method during errors.
        """
        def funct():
            pass

        with pytest.raises(ValueError):
            handler.link(None, funct)

        with pytest.raises(ValueError):
            handler.link("myevent", None)

    def test_link(self, handler):
        """
        Test link method.
        """
        def funct():
            pass

        handler.register("myevent", funct)
        assert handler.is_registered("myevent")

        def funct2():
            pass

        handler.link("myevent", funct2)

    def test_unlink_errors(self, handler):
        """
        Test unlink method during errors.
        """
        def funct():
            pass

        with pytest.raises(ValueError):
            handler.unlink(None, funct)

        with pytest.raises(ValueError):
            handler.unlink("myevent", None)

    def test_unlink(self, handler):
        """
        Test unlink method.
        """
        def funct():
            pass

        handler.register("myevent", funct)
        assert handler.is_registered("myevent")

        def funct2():
            pass

        handler.link("myevent", funct2)
        assert handler.is_registered("myevent")

        handler.unlink("myevent", funct2)
        assert handler.is_registered("myevent")

    def test_fire_errors(self, handler):
        """
        Test fire method during errors.
        """
        with pytest.raises(ValueError):
            handler.fire("notmyevent", "prova")

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

        handler.link("myevent", funct2)
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
