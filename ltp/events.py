"""
.. module:: events
    :platform: Linux
    :synopsis: module containing the event handler implementation.

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""


class EventHandler:
    """
    Synchronous event handler class.
    """

    def is_registered(self, event_name: str) -> bool:
        """
        Returns True if ``event_name`` is registered.
        :param event_name: name of the event
        :type event_name: str
        :returns: True if registered, False otherwise
        """
        raise NotImplementedError()

    def register(self, event_name: str, callback: callable) -> None:
        """
        Register an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        :param callback: function associated with ``event_name``
        :type callback: callable
        """
        raise NotImplementedError()

    def unregister(self, event_name: str) -> None:
        """
        Unregister an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        """
        raise NotImplementedError()

    def link(self, event_name: str, callback: callable) -> None:
        """
        Link ``callback`` to an existing event that has to be fired.
        :param event_name: name of the event
        :type event_name: str
        :param callback: callback to call on ``fire``
        :type callback: callable
        """
        raise NotImplementedError()

    def unlink(self, event_name: str, callback: callable) -> None:
        """
        Unlink ``callback`` to an existing event.
        :param event_name: name of the event
        :type event_name: str
        :param callback: linked callback
        :type callback: callable
        """
        raise NotImplementedError()

    def fire(self, event_name: str, *args: list, **kwargs: dict) -> None:
        """
        Fire a specific event.
        :param event_name: name of the event
        :type event_name: str
        :param args: Arguments to be passed to callback functions execution.
        :type args: list
        :param kwargs: Keyword arguments to be passed to callback functions execution.
        :type kwargs: dict
        """
        raise NotImplementedError()


class SyncEventHandler(EventHandler):
    """
    Synchronous event handler class.
    """

    def __init__(self) -> None:
        self._events = {}

    def is_registered(self, event_name: str) -> bool:
        """
        Returns True if ``event_name`` is registered.
        :param event_name: name of the event
        :type event_name: str
        :returns: True if registered, False otherwise
        """
        if not event_name:
            raise ValueError("event_name is empty")

        return event_name in self._events

    def register(self, event_name: str, callback: callable) -> None:
        """
        Register an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        :param callback: function associated with ``event_name``
        :type callback: callable
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not callback:
            raise ValueError("callback is empty")

        if self.is_registered(event_name):
            raise ValueError(f"{event_name} is already registered")

        self._events[event_name] = []
        self._events[event_name].append(callback)

    def unregister(self, event_name: str) -> None:
        """
        Unregister an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not self.is_registered(event_name):
            raise ValueError(f"{event_name} is not registered")

        self._events.pop(event_name)

    def link(self, event_name: str, callback: callable) -> None:
        """
        Link ``callback`` to an existing event that has to be fired.
        :param event_name: name of the event
        :type event_name: str
        :param callback: callback to call on ``fire``
        :type callback: callable
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not callback:
            raise ValueError("callback is empty")

        if not self.is_registered(event_name):
            raise ValueError(f"{event_name} is not registered")

        self._events[event_name].append(callback)

    def unlink(self, event_name: str, callback: callable) -> None:
        """
        Unlink ``callback`` to an existing event.
        :param event_name: name of the event
        :type event_name: str
        :param callback: linked callback
        :type callback: callable
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not callback:
            raise ValueError("callback is empty")

        if not self.is_registered(event_name):
            raise ValueError(f"{event_name} is not registered")

        self._events[event_name].remove(callback)

    def fire(self, event_name: str, *args: list, **kwargs: dict) -> None:
        """
        Fire a specific event.
        :param event_name: name of the event
        :type event_name: str
        :param args: Arguments to be passed to callback functions execution.
        :type args: list
        :param kwargs: Keyword arguments to be passed to callback functions execution.
        :type kwargs: dict
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not self.is_registered(event_name):
            raise ValueError(f"{event_name} is not registered")

        for callback in self._events[event_name]:
            callback(*args, **kwargs)
