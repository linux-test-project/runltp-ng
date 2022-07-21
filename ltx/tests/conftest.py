"""
Tests configuration file.
"""
import os
import logging
import subprocess
import pytest


@pytest.fixture(scope="session")
def ltx_bin_dir():
    """
    The ltx binary path.
    """
    curr_dir = os.path.abspath(os.path.dirname(__file__))
    parent_dir = os.path.dirname(curr_dir)
    binary = os.path.join(parent_dir, "ltx")

    return binary


@pytest.fixture(scope="session")
def ltx_compile(ltx_bin_dir):
    """
    Compile LTX using a specific tool.
    """
    def _callback(tool):
        logger = logging.getLogger(f"test.{tool}")

        curr_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.dirname(curr_dir)

        ltx_dir = os.path.join(parent_dir, "ltx.c")

        cflags = '-v -Wall -Wextra -Werror -g ' \
            '-fno-omit-frame-pointer -fsanitize=address,undefined'

        cmd = f"{tool} {cflags} {ltx_dir} -o {ltx_bin_dir}"

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            check=True)

        logger.info(result.stdout.decode(encoding="utf-8", errors="ignore"))

    yield _callback


@pytest.fixture
def executor(ltx_bin_dir):
    """
    Prepare LTX executor and return the running process.
    """
    with subprocess.Popen(
            ltx_bin_dir,
            bufsize=0,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE) as proc:
        yield proc


@pytest.fixture(autouse=True, scope="session")
def setup_binary(ltx_compile, ltx_bin_dir):
    """
    Ensure that the ltx binary has been compiled before running a testing
    session.
    """
    if not os.path.isfile(ltx_bin_dir):
        ltx_compile("gcc")

    yield

    if os.path.isfile(ltx_bin_dir):
        os.remove(ltx_bin_dir)


@pytest.fixture
def whereis():
    """
    Wrapper around whereis command.
    """
    def _callback(binary):
        stdout = subprocess.check_output([f"whereis {binary}"], shell=True)
        paths = stdout.decode().split()[1:]

        assert len(paths) > 0
        return paths

    yield _callback
