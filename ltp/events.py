"""
.. module:: events
    :platform: Linux
    :synopsis: module containing the event handler implementation.

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

_EVENTS = {}


def reset() -> None:
    """
    Reset the entire events queue.
    """
    _EVENTS.clear()


def is_registered(event_name: str) -> bool:
    """
    Returns True if ``event_name`` is registered.
    :param event_name: name of the event
    :type event_name: str
    :returns: True if registered, False otherwise
    """
    if not event_name:
        raise ValueError("event_name is empty")

    return event_name in _EVENTS


def register(event_name: str, callback: callable) -> None:
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

    if not is_registered(event_name):
        _EVENTS[event_name] = []

    _EVENTS[event_name].append(callback)


def unregister(event_name: str) -> None:
    """
    Unregister an event with ``event_name``.
    :param event_name: name of the event
    :type event_name: str
    """
    if not event_name:
        raise ValueError("event_name is empty")

    if not is_registered(event_name):
        raise ValueError(f"{event_name} is not registered")

    _EVENTS.pop(event_name)


def fire(event_name: str, *args: list, **kwargs: dict) -> None:
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

    if not is_registered(event_name):
        # ignore raising the error
        return

    for callback in _EVENTS[event_name]:
        callback(*args, **kwargs)
