"""
.. module:: main
    :platform: Linux
    :synopsis: main script

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import argparse
from argparse import ArgumentParser
from argparse import Namespace
from ltp.tempfile import TempDir
from ltp.session import Session
from ltp.ui import SimpleUserInterface
from ltp.ui import VerboseUserInterface


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

        data = param.split('=')
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


def _get_qemu_config(params: list) -> dict:
    """
    Return qemu configuration.
    """
    config = _from_params_to_config(params)

    if "image" not in config:
        raise argparse.ArgumentTypeError(
            "'image' parameter is required by qemu SUT")

    defaults = (
        'image',
        'image_overlay',
        'password',
        'system',
        'ram',
        'smp',
        'serial',
        'ro_image',
        'virtfs'
    )

    if not set(config).issubset(defaults):
        raise argparse.ArgumentTypeError(
            "Some parameters are not supported. "
            f"Please use the following: {', '.join(defaults)}")

    if "image" in config and not os.path.isfile(config["image"]):
        raise argparse.ArgumentTypeError("Qemu image doesn't exist")

    if "image_overlay" in config and os.path.isfile(config["image_overlay"]):
        raise argparse.ArgumentTypeError("Qemu image overlay already exist")

    if "password" in config and not config["password"]:
        raise argparse.ArgumentTypeError("Qemu password is empty")

    if "smp" in config and not str.isdigit(config["smp"]):
        raise argparse.ArgumentTypeError("smp must be and integer")

    return config


def _sut_config(value: str) -> dict:
    """
    Return a SUT configuration according with input string.
    Format for value is, for example:

        qemu:ram=4G:smp=4:image=/local/vm.qcow2:virtfs=/opt/ltp:password=123

    """
    if value == "help":
        msg = "--sut option supports the following syntax:\n"
        msg += "\n\t<SUT>:<param1>=<value1>:<param2>=<value2>:..\n"
        msg += "\nSupported SUT:\n"
        msg += "\thost: current machine (default)\n"
        msg += "\tqemu: Qemu virtual machine\n"
        msg += "\nqemu parameters:\n"
        msg += "\timage: qcow2 image location\n"
        msg += "\timage_overlay: image copy location\n"
        msg += "\tpassword: root password (default: root)\n"
        msg += "\tsystem: system architecture (default: x86_64\n"
        msg += "\tram: RAM of the VM (default: 2G)\n"
        msg += "\tsmp: number of CPUs (default: 2)\n"
        msg += "\tserial: type of serial protocol. isa|virtio (default: isa)\n"
        msg += "\tvirtfs: directory to mount inside VM\n"
        msg += "\tro_image: path of the image that will exposed as read only\n"

        return dict(help=msg)

    if not value:
        raise argparse.ArgumentTypeError("SUT parameters can't be empty")

    params = value.split(':')
    name = params[0]

    config = None
    if name == 'qemu':
        config = _get_qemu_config(params[1:])
    elif name == 'host':
        config = _from_params_to_config(params[1:])
    else:
        raise argparse.ArgumentTypeError(f"'{name}' SUT is not supported")

    config['name'] = name

    return config


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

    if args.verbose:
        VerboseUserInterface(args.colors_rule)
    else:
        SimpleUserInterface(args.colors_rule)

    session = Session(
        suite_timeout=args.suite_timeout,
        exec_timeout=args.exec_timeout,
        colors_rule=args.colors_rule)

    # create list of tests to skip
    skip_tests = []
    if args.skip_tests:
        skip_tests.extend(args.skip_tests)

    if args.skip_file:
        lines = None
        with open(args.skip_file, 'r', encoding="utf-8") as skip_file:
            lines = skip_file.readlines()

        toskip = [
            line.rstrip()
            for line in lines
            if not re.search(r'^\s+#.*', line)
        ]
        skip_tests.extend(toskip)

    tmpdir = TempDir(args.tmp_dir)

    session.run_single(
        args.sut,
        args.json_report,
        args.run_suite,
        args.run_cmd,
        args.ltp_dir,
        tmpdir,
        skip_tests=skip_tests)


def run() -> None:
    """
    Entry point of the application.
    """
    parser = argparse.ArgumentParser(description='LTP next-gen runner')
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose mode")
    parser.add_argument(
        "--color",
        "-C",
        default="default",
        dest="colors_rule",
        help="Type of colors rule we want [none, default, ltp]")
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
        nargs="*",
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
