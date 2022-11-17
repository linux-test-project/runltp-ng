"""
.. module:: __init__
    :platform: Linux
    :synopsis: ltp package definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import time
from queue import Queue
from threading import Thread


class EventsHandler:
    """
    This class implements event loop and events handling.
    """

    def __init__(self) -> None:
        self._stop = False
        self._tasks = Queue()
        self._events = {}
        self._loop = None

    def _event_loop(self) -> None:
        """
        Main event loop.
        """
        self._stop = False

        while True:
            time.sleep(1e-3)

            while not self._tasks.empty():
                task = self._tasks.get()

                # pylint: disable=broad-except
                try:
                    task()
                except Exception as exc:
                    if "internal_error" not in self._events:
                        return

                    calls = self._events["internal_error"]
                    if len(calls) > 0:
                        callback = calls[0]
                        callback(exc, callback.__name__)

            if self._stop:
                break

    def reset(self) -> None:
        """
        Reset the entire events queue.
        """
        self._events.clear()

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

        if not self.is_registered(event_name):
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

    def fire(self, event_name: str, *args: list, **kwargs: dict) -> None:
        """
        Fire a specific event.
        :param event_name: name of the event
        :type event_name: str
        :param args: Arguments to be passed to callback functions execution.
        :type args: list
        :param kwargs: Keyword arguments to be passed to callback functions
            execution.
        :type kwargs: dict
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not self.is_registered(event_name):
            # ignore raising the error
            return

        for callback in self._events[event_name]:
            self._tasks.put(lambda f=callback, x=args, y=kwargs: f(*x, **y))

    def stop_event_loop(self) -> None:
        """
        Stop the event loop.
        """
        if not self._loop:
            return

        self._stop = True
        self._loop.join(10)
        self._loop = None

    def start_event_loop(self) -> None:
        """
        Start the event loop.
        """
        self.stop_event_loop()

        self._loop = Thread(target=self._event_loop, daemon=True)
        self._loop.start()


events = EventsHandler()


class LTPException(Exception):
    """
    The most generic exception that is raised by any ltp package when
    something bad happens.
    """
    pass


__all__ = [
    "events",
    "LTPException"
]
