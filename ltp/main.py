"""
.. module:: main
    :platform: Linux
    :synopsis: main script

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import sys
import inspect
import argparse
import importlib
import importlib.util
from argparse import ArgumentParser
from argparse import Namespace
import ltp
from ltp.sut import SUT
from ltp.tempfile import TempDir
from ltp.session import Session
from ltp.ui import SimpleUserInterface
from ltp.ui import VerboseUserInterface


# runtime loaded SUT(s)
LOADED_SUT = []


def _from_params_to_config(params: list) -> dict:
    """
    Return a configuration as dictionary according with input parameters
    given to the commandline option.
    """
    config = {}
    for param in params:
        if '=' not in param:
            raise argparse.ArgumentTypeError(
                f"Missing '=' assignment in '{param}' parameter")

        data = param.split('=', 1)
        key = data[0]
        value = data[1]

        if not key:
            raise argparse.ArgumentTypeError(
                f"Empty key for '{param}' parameter")

        if not key:
            raise argparse.ArgumentTypeError(
                f"Empty value for '{param}' parameter")

        config[key] = value

    return config


def _sut_config(value: str) -> dict:
    """
    Return a SUT configuration according with input string.
    """
    if value == "help":
        msg = "--sut option supports the following syntax:\n"
        msg += "\n\t<SUT>:<param1>=<value1>:<param2>=<value2>:..\n"
        msg += "\nSupported SUT: | "

        for sut in LOADED_SUT:
            msg += f"{sut.name} | "

        msg += '\n'

        for sut in LOADED_SUT:
            if not sut.config_help:
                msg += f"\n{sut.name} has not configuration\n"
            else:
                msg += f"\n{sut.name} configuration:\n"
                for opt, desc in sut.config_help.items():
                    msg += f"\t{opt}: {desc}\n"

        return dict(help=msg)

    if not value:
        raise argparse.ArgumentTypeError("SUT parameters can't be empty")

    params = value.split(':')
    name = params[0]

    config = _from_params_to_config(params[1:])
    config['name'] = name

    return config


def _discover_sut(folder: str) -> list:
    """
    Discover new SUT implementations inside a specific folder.
    """
    LOADED_SUT.clear()

    for myfile in os.listdir(folder):
        if not myfile.endswith('.py'):
            continue

        path = os.path.join(folder, myfile)
        if not os.path.isfile(path):
            continue

        spec = importlib.util.spec_from_file_location('sut', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        members = inspect.getmembers(module, inspect.isclass)
        for _, klass in members:
            if klass.__module__ != module.__name__ or \
                    klass is SUT or \
                    klass in LOADED_SUT:
                continue

            if issubclass(klass, SUT):
                LOADED_SUT.append(klass())

    if len(LOADED_SUT) > 0:
        LOADED_SUT.sort(key=lambda x: x.name)


def _ltp_run(parser: ArgumentParser, args: Namespace) -> None:
    """
    Handle runltp-ng command options.
    """
    if args.sut and "help" in args.sut:
        print(args.sut["help"])
        return

    if args.json_report and os.path.exists(args.json_report):
        parser.error(f"JSON report file already exists: {args.json_report}")

    if not args.run_suite and not args.run_cmd:
        parser.error("--run-suite/--run-cmd are required")

    if args.skip_file and not os.path.isfile(args.skip_file):
        parser.error(f"'{args.skip_file}' skip file doesn't exist")

    if args.tmp_dir and not os.path.isdir(args.tmp_dir):
        parser.error(f"'{args.tmp_dir}' temporary folder doesn't exist")

    # create regex of tests to skip
    skip_tests = args.skip_tests

    if args.skip_file:
        lines = None
        with open(args.skip_file, 'r', encoding="utf-8") as skip_file:
            lines = skip_file.readlines()

        toskip = [
            line.rstrip()
            for line in lines
            if not re.search(r'^\s+#.*', line)
        ]
        skip_tests = '|'.join(toskip) + '|' + skip_tests

    if skip_tests:
        try:
            re.compile(skip_tests)
        except re.error:
            parser.error(f"'{skip_tests}' is not a valid regular expression")

    ltp.events.start_event_loop()

    if args.verbose:
        VerboseUserInterface(args.no_colors)
    else:
        SimpleUserInterface(args.no_colors)

    session = Session(
        LOADED_SUT,
        suite_timeout=args.suite_timeout,
        exec_timeout=args.exec_timeout,
        no_colors=args.no_colors)

    tmpdir = TempDir(args.tmp_dir)

    exit_code = session.run_single(
        args.sut,
        args.json_report,
        args.run_suite,
        args.run_cmd,
        args.ltp_dir,
        tmpdir,
        skip_tests=skip_tests)

    ltp.events.stop_event_loop()

    sys.exit(exit_code)


def run() -> None:
    """
    Entry point of the application.
    """
    _discover_sut(os.path.dirname(os.path.realpath(__file__)))

    parser = argparse.ArgumentParser(description='LTP next-gen runner')
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose mode")
    parser.add_argument(
        "--no-colors",
        "-n",
        action="store_true",
        help="If defined, no colors are shown")
    parser.add_argument(
        "--ltp-dir",
        "-l",
        type=str,
        default="/opt/ltp",
        help="LTP install directory")
    parser.add_argument(
        "--tmp-dir",
        "-d",
        type=str,
        default="/tmp",
        help="LTP temporary directory")
    parser.add_argument(
        "--skip-tests",
        "-i",
        type=str,
        help="Skip specific tests")
    parser.add_argument(
        "--skip-file",
        "-I",
        type=str,
        help="Skip specific tests using a skip file (newline separated item)")
    parser.add_argument(
        "--suite-timeout",
        "-T",
        type=int,
        default=3600,
        help="Timeout before stopping the suite")
    parser.add_argument(
        "--exec-timeout",
        "-t",
        type=int,
        default=3600,
        help="Timeout before stopping a single execution")
    parser.add_argument(
        "--run-suite",
        "-r",
        nargs="*",
        help="Suites to run")
    parser.add_argument(
        "--run-cmd",
        "-c",
        help="Command to run")
    parser.add_argument(
        "--sut",
        "-s",
        default="host",
        type=_sut_config,
        help="System Under Test parameters")
    parser.add_argument(
        "--json-report",
        "-j",
        type=str,
        help="JSON output report")

    args = parser.parse_args()

    _ltp_run(parser, args)


if __name__ == "__main__":
    run()
