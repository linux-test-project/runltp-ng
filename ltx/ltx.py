"""
.. module:: ltx
    :platform: Linux
    :synopsis: module containing LTX communication class

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import time
import select
import logging
import threading
import msgpack


class LTXError(Exception):
    """
    Raised when an error occurs during LTX operations.
    """


class LTX:
    """
    LTX executor is a simple and fast service built in C, used to send commands
    on SUT, as well as fetching or sending files to it. This class has been
    created to communicate with LTX using python.

    A generic class usage is the following:

        with subprocess.Popen(
            "ltx",
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE) as proc:

            ltx = LTX(proc.stdin.fileno(), proc.stdout.fileno())

            # check if executor replies
            ltx.ping()

            # reserve table ID for command execution
            table_id = ltx.reserve()

            # execute command
            stdout, \
                time_ns, \
                si_code, \
                si_status = ltx.execute(
                    table_id,
                    "/usr/bin/echo hello",
                    timeout=1)

    """
    TABLE_ID_MAXSIZE = 128
    PING = 0
    PONG = 1
    ENV = 2
    EXEC = 3
    LOG = 4
    RESULT = 5
    GET_FILE = 6
    SET_FILE = 7
    DATA = 8
    KILL = 9
    VERSION = 10

    def __init__(self, stdin_fd: int, stdout_fd: int) -> None:
        """
        :param stdin_fd: stdin file descriptor
        :type stdin_fd: int
        :param stdout_fd: stdout file descriptor
        :type stdout_fd: int
        """
        if not stdin_fd or stdin_fd < 0:
            raise ValueError("Invalid stdin file descriptor")

        if not stdout_fd or stdout_fd < 0:
            raise ValueError("Invalid stdout file descriptor")

        self._logger = logging.getLogger("ltx")
        self._stdin_fd = stdin_fd
        self._stdout_fd = stdout_fd
        self._rlock = threading.Lock()
        self._wlock = threading.Lock()
        self._table_id = []

    def _send_msg(self, msg: list) -> None:
        """
        Send a message to stdin.
        """
        with self._wlock:
            self._logger.info("Sending message: %s", msg)

            data = msgpack.packb(msg)

            bytes_towrite = len(data)
            bytes_written = os.write(self._stdin_fd, data)

            if bytes_written != bytes_towrite:
                raise LTXError(
                    f"Can't send all {bytes_towrite} bytes. "
                    f" Only {bytes_written} bytes were written.")

    def _read_reply(
            self,
            validate_msg: callable,
            timeout: float = 30) -> None:
        """
        Read a reply from stdout.
        """
        with self._rlock:
            self._logger.info("Getting the reply")

            poller = select.epoll()
            poller.register(self._stdout_fd, select.EPOLLIN)
            unpacker = msgpack.Unpacker()
            reply = None

            start_t = time.time()

            while not reply:
                events = poller.poll(1)

                if time.time() - start_t > timeout:
                    self._logger.info("Command timed out")
                    raise LTXError("Timeout reached when waiting for reply")

                for fdesc, _ in events:
                    if fdesc != self._stdout_fd:
                        continue

                    data = os.read(self._stdout_fd, 1 << 21)
                    unpacker.feed(data)

                    self._logger.debug("Unpacking bytes: %s", data)

                    while not reply:
                        try:
                            msg = unpacker.unpack()
                            if msg:
                                self._logger.info("Received message: %s", msg)

                                reply = validate_msg(msg)
                        except msgpack.OutOfData:
                            break

        return reply

    def _send_and_reply(
            self,
            msg: list,
            validate_msg: callable,
            timeout: float = 30) -> None:
        """
        Send a message and read the reply.
        """
        self._send_msg(msg)
        reply = self._read_reply(validate_msg, timeout=timeout)

        return reply

    def _check_table_id(self, table_id: int) -> None:
        """
        Check if `table_id` is in between bounds and eventually rise an
        exception.
        """
        if table_id < 0 or table_id >= self.TABLE_ID_MAXSIZE:
            raise ValueError("Out of bounds table ID [0-127]")

        if table_id not in self._table_id:
            raise ValueError("table ID is not available")

    def reserve(self) -> int:
        """
        Reserve a new table ID to execute a command.
        :returns: index of table ID as int
        """
        if len(self._table_id) >= self.TABLE_ID_MAXSIZE:
            raise LTXError("Not enough slots for other commands")

        counter = -1

        for counter in range(0, self.TABLE_ID_MAXSIZE):
            if counter not in self._table_id:
                break

        assert counter != -1

        self._logger.info("Reserving table ID: %d", counter)

        self._table_id.append(counter)

        return counter

    def version(self) -> str:
        """
        Get version from executor.
        """
        self._logger.info("Asking for version")

        def validate_msg(msg):
            """
            Validate messages and return version from LOG message.
            """
            if msg[0] == LTX.VERSION:
                self._logger.info("VERSION echoed back")
            elif msg[0] == LTX.LOG and msg[1] is None:
                match = re.match(r'LTX Version=(?P<version>.*)', msg[3])
                if match:
                    version = match.group("version").rstrip()
                    return version

            return None

        msg = [LTX.VERSION]

        version = self._send_and_reply(msg, validate_msg, timeout=10)

        self._logger.info("Version received: %s", version)

        return version

    def ping(self, timeout: float = 10) -> int:
        """
        Ping executor and wait for pong.
        :param timeout: time before raising a timeout during execution
        :type timeout: float
        :returns: nanoseconds between pong and epoch
        """
        self._logger.info("Sending ping")

        def validate_msg(msg):
            """
            Validate messages and return time_ns when PONG has been received.
            """
            if msg[0] == LTX.PING:
                self._logger.info("PING echoed back")
                self._logger.info("Waiting for PONG")
            elif msg[0] == LTX.PONG:
                self._logger.info("PONG received")
                return msg[1]

            return None

        msg = [LTX.PING]

        end_t = self._send_and_reply(msg, validate_msg, timeout=timeout)

        self._logger.info("PONG epoch time: %d nanoseconds", end_t)

        return end_t

    def env(self,
            table_id: int,
            key: str,
            value: str,
            timeout: float = 10) -> None:
        """
        Set environment variable on target.
        :param table_id: command table ID. It can be None if environment
            variable should be applied to all commands
        :type table_id: int
        :param key: key of the environment variable
        :type key: str
        :param value: value of the environment variable
        :type value: str
        :param timeout: time before raising a timeout during execution
        :type timeout: float
        """
        if table_id:
            self._check_table_id(table_id)

        self._logger.info("Setting env: %s=%s", key, value)

        def validate_msg(msg):
            """
            Validate messages and return (key, value) if environment variable
            has been set.
            """
            if msg[0] == LTX.ENV and \
                    msg[1] == table_id and \
                    msg[2] == key and \
                    msg[3] == value:
                self._logger.info("ENV echoed back")
                return msg[2], msg[3]

            return None

        msg = [LTX.ENV, table_id, key, value]

        self._send_and_reply(
            msg,
            validate_msg,
            timeout=timeout)

    def get_file(self, path: str, timeout: float = 30) -> bytes:
        """
        Read a file on target and return its content.
        :param path: path of the file
        :type path: str
        :param timeout: time before raising a timeout during execution
        :type timeout: float
        :returns: file contents as bytes
        """
        if not path:
            raise ValueError("path is empty")

        self._logger.info("Getting file: %s", path)

        def validate_msg(msg):
            """
            Validate messages and return data file when file has been fetched.
            """
            if msg[0] == LTX.GET_FILE and path == msg[1]:
                self._logger.info("GET_FILE echoed back")
            elif msg[0] == LTX.DATA:
                data = msg[1]
                return data

            return None

        msg = [LTX.GET_FILE, path]

        data = self._send_and_reply(msg, validate_msg, timeout=timeout)

        return data

    def set_file(self, path: str, data: bytes, timeout: float = 30) -> None:
        """
        Send a file on target.
        :param path: path of the file to write
        :type path: str
        :param data: data to write on file
        :type data: bytes
        :param timeout: time before raising a timeout during execution
        :type timeout: float
        """
        if not path:
            raise ValueError("path is empty")

        if not data:
            raise ValueError("data is empty")

        self._logger.info("Setting file: %s", path)

        def validate_msg(msg):
            """
            Validate messages and return data file when file has been sent.
            """
            if msg[0] == LTX.SET_FILE and \
                    path == msg[1] and \
                    data == msg[2]:
                self._logger.info("SET_FILE echoed back")
                return msg[2]

            return None

        msg = [LTX.SET_FILE, path, data]

        self._send_and_reply(msg, validate_msg, timeout=timeout)

    def execute(self,
                table_id: int,
                command: str,
                timeout: float = 30,
                stdout_callback: callable = None) -> set:
        """
        Execute a command on target.
        :param table_id: table ID of the command to run
        :type table_id: int
        :param command: command to run
        :type command: str
        :param timeout: time before raising a timeout during execution
        :type timeout: float
        :param stdout_callback: raised when new data is acquired during
            command execution
        :type stdout_callback: callable
        :returns: stdout, time_ns, si_code, si_status
        """
        self._check_table_id(table_id)

        if not command:
            raise ValueError("Command is empty")

        self._logger.info("Executing: %s", command)

        mystdout = []

        def validate_msg(msg, stdout):
            """
            Validate messages and return stdout, time_ns, si_code, si_status
            when process has been completed.
            """
            if table_id == msg[1]:
                if msg[0] == LTX.EXEC:
                    self._logger.info("EXEC echoed back")
                elif msg[0] == LTX.LOG:
                    log = msg[3]

                    self._logger.info("LOG replied with data: %s", repr(log))

                    stdout.append(log)

                    if stdout_callback:
                        stdout_callback(log)
                elif msg[0] == LTX.RESULT:
                    time_ns = msg[2]
                    si_code = msg[3]
                    si_status = msg[4]

                    self._logger.info("RESULT reply")
                    self._logger.debug(
                        "time_ns=%s, si_code=%s, si_status=%s",
                        time_ns,
                        si_code,
                        si_status)

                    self._logger.info("Removing table ID: %d", table_id)
                    self._table_id.remove(table_id)

                    return "".join(stdout), time_ns, si_code, si_status
                elif msg[0] == LTX.KILL:
                    self._logger.info("KILL echoed back")

            return None

        args = command.split()
        msg = [LTX.EXEC, table_id]
        msg.extend(args)

        stdout, time_ns, si_code, si_status = self._send_and_reply(
            msg,
            lambda x: validate_msg(x, mystdout),
            timeout=timeout)

        return stdout, time_ns, si_code, si_status

    def kill(self, table_id: int) -> None:
        """
        Kill a command on target.
        :param table_id: table ID of the running command
        :type table_id: int
        """
        self._check_table_id(table_id)

        self._logger.info("Killing process on table ID: %d", table_id)

        msg = [LTX.KILL, table_id]

        # let the execute method to handle reply messages
        self._send_msg(msg)
