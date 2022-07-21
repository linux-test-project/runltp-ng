"""
.. module:: __init__
    :platform: Linux
    :synopsis: ltx package initializer

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
from .ltx import LTX
from .ltx import LTXError

__all__ = [
    "LTX",
    "LTXError",
]
