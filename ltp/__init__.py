"""
.. module:: __init__
    :platform: Linux
    :synopsis: ltp package definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""


class LTPException(Exception):
    """
    The most generic exception that is raised by any ltp package when
    something bad happens.
    """
    pass


__all__ = [
    "LTPException"
]
