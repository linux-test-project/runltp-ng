"""
.. module:: ltx
    :platform: Linux
    :synopsis: module containing LTX communication class

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import select
import asyncio
import logging
import altp

try:
    import msgpack
except ModuleNotFoundError:
    pass


class LTXError(altp.LTPException):
    """
    Raised when an error occurs during LTX execution.
    """


MAX_SLOTS = 128
"""
Maximum number of execution slots supported by LTX.
"""


class Request:
    """
    LTX request.
    """
    ERROR = 0xff
    VERSION = 0x00
    PING = 0x01
    PONG = 0x02
    GET_FILE = 0x03
    SET_FILE = 0x04
    ENV = 0x05
    CWD = 0x06
    EXEC = 0x07
    RESULT = 0x08
    LOG = 0x09
    DATA = 0xa0
    KILL = 0xa1
    MAX_SLOTS = 128
    MAX_ENVS = 16

    def __init__(self, **kwargs: dict) -> None:
        """
        :param args: request arguments
        :type args: list
        """
        self._logger = logging.getLogger("ltx.request")
        self._request_id = None
        self._args = kwargs.get("args", [])
        self._completed = False
        self._on_complete = None

    @property
    def completed(self) -> bool:
        """
        If True the request has been completed.
        """
        return self._completed

    @property
    def on_complete(self) -> callable:
        """
        Get the `on_complete` event.
        """
        return self._on_complete

    @on_complete.setter
    def on_complete(self, callback: callable) -> None:
        """
        Set the `on_complete` event.
        """
        self._on_complete = callback

    def pack(self) -> bytes:
        """
        Pack request to msgpack.
        """
        msg = []
        msg.append(self._request_id)
        msg.extend(self._args)

        data = msgpack.packb(msg)

        return data

    @staticmethod
    def _check_slot_id(slot_id: int) -> None:
        """
        Check if `slot_id` is in between bounds and eventually rise an
        exception.
        """
        if slot_id and (slot_id < 0 or slot_id >= MAX_SLOTS):
            raise ValueError("Out of bounds slot ID [0-127]")

    def _raise_complete(self, *args) -> None:
        """
        Raise the complete callback with given data.
        """
        if self._on_complete:
            self._logger.info("Raising 'on_complete%s'", args)
            self._on_complete(*args)

        self._completed = True

    def feed(self, message: list) -> None:
        """
        Feed request queue with data and return when the request
        has been completed.
        :param message: processed msgpack message
        :type message: list
        """
        raise NotImplementedError()


def version() -> Request:
    """
    Create VERSION request.
    :returns: Request
    """
    class _VersionRequest(Request):
        """
        VERSION request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.VERSION

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self._request_id:
                ver = message[1]
                self._logger.debug("version=%s", ver)

                self._raise_complete(ver)
                self._completed = True

    return _VersionRequest()


def ping() -> Request:
    """
    Create PING request.
    :returns: Request
    """
    class _PingRequest(Request):
        """
        PING request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._echoed = False
            self._request_id = self.PING

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.PING:
                self._logger.info("PING echoed back")
                self._logger.info("Waiting for PONG")
                self._echoed = True
            elif message[0] == self.PONG:
                if not self._echoed:
                    raise LTXError("PONG received without PING echo")

                end_t = message[1]

                self._logger.debug("end_t=%s", end_t)

                self._raise_complete(end_t)
                self._completed = True

    return _PingRequest()


def env(slot_id: int, key: str, value: str) -> Request:
    """
    Create ENV request.
    :param slot_id: command table ID. Can be None if we want to apply the
        same environment variables to all commands
    :type slot_id: int
    :param key: key of the environment variable
    :type key: str
    :param value: value of the environment variable
    :type value: str
    :returns: Request
    """
    if not key:
        raise ValueError("key is empty")

    if not value:
        raise ValueError("value is empty")

    class _EnvRequest(Request):
        """
        ENV request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.ENV
            self._slot_id = self._args[0]

            if self._slot_id and (self._slot_id < 0 or self._slot_id > 128):
                raise ValueError("Out of bounds slot ID [0-128]")

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.ENV:
                self._logger.info("ENV echoed back")

                self._raise_complete()
                self._completed = True

    return _EnvRequest(args=[slot_id, key, value])


def get_file(path: str) -> Request:
    """
    Create GET_FILE request.
    :param path: path of the file
    :type path: str
    :returns: Request
    """
    if not path:
        raise ValueError("path is empty")

    class _GetFileRequest(Request):
        """
        GET_FILE request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.GET_FILE
            self._data = []

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.GET_FILE:
                self._logger.info("GET_FILE echoed back")
                self._completed = True

                self._raise_complete(b''.join(self._data))
                self._completed = True
            elif message[0] == self.DATA:
                self._logger.info("Data received")
                self._data.append(message[1])

    return _GetFileRequest(args=[path])


def set_file(path: str, data: bytes) -> Request:
    """
    Create SET_FILE request.
    :param path: path of the file to write
    :type path: str
    :param data: data to write on file
    :type data: bytes
    :returns: Request
    """
    if not path:
        raise ValueError("path is empty")

    if not data:
        raise ValueError("data is empty")

    class _SetFileRequest(Request):
        """
        SET_FILE request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.SET_FILE

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.SET_FILE and message[1] == self._args[0]:
                self._logger.info("SETFILE echoed back")

                self._raise_complete()
                self._completed = True

    return _SetFileRequest(args=[path, data])


def execute(slot_id: int,
            command: str,
            stdout_callback: callable = None) -> Request:
    """
    Create EXEC request.
    :param slot_id: command table ID
    :type slot_id: int
    :param command: command to run
    :type command: str
    :param stdout_callback: called when new data arrives inside stdout
    :type stdout_callback: callable
    :returns: Request
    """
    if not command:
        raise ValueError("Command is empty")

    class _ExecRequest(Request):
        """
        EXEC request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._stdout_callback = kwargs.get("stdout_callback", None)
            self._stdout = []
            self._echoed = False
            self._request_id = self.EXEC
            self._slot_id = self._args[0]
            self._check_slot_id(self._slot_id)

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.EXEC:
                self._logger.info("EXEC echoed back")
                self._echoed = True
            elif message[0] == self.LOG:
                if not self._echoed:
                    raise LTXError("LOG received without EXEC echo")

                log = message[3]

                self._logger.info("LOG replied with data: %s", repr(log))
                self._stdout.append(log)

                if self._stdout_callback:
                    self._stdout_callback(log)
            elif message[0] == self.RESULT:
                if not self._echoed:
                    raise LTXError("RESULT received without EXEC echo")

                self._logger.info("RESULT received")

                stdout = "".join(self._stdout)
                time_ns = message[2]
                si_code = message[3]
                si_status = message[4]

                self._logger.debug(
                    "time_ns=%s, si_code=%s, si_status=%s",
                    time_ns,
                    si_code,
                    si_status)

                self._raise_complete(
                    stdout,
                    time_ns,
                    si_code,
                    si_status)

                self._completed = True

    args = [slot_id, command]

    return _ExecRequest(stdout_callback=stdout_callback, args=args)


def kill(slot_id: int) -> Request:
    """
    Create KILL request.
    :param slot_id: command table ID
    :type slot_id: int
    :returns: Request
    """
    class _KillRequest(Request):
        """
        KILL request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.KILL
            self._slot_id = self._args[0]
            self._check_slot_id(self._slot_id)

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.KILL:
                self._logger.info("KILL echoed back")

                self._raise_complete()
                self._completed = True

    return _KillRequest(args=[slot_id])


class Session:
    """
    This class communicates with LTX by processing given requests.
    Typical usage is the following:

        with ltx.Session(stdin_fd, stdout_fd) as session:
            # create requests
            request1 = ltx.execute("echo 'hello world' > myfile")
            request2 = ltx.cat("myfile")

            # set the complete event
            request1.on_complete = exec_complete_handler
            request2.on_complete = cat_complete_handler

            # send request
            session.send([request1, request2])

            # process exec_complete_handler/cat_complete_handler output
            ...

    """
    BUFFSIZE = 1 << 21

    def __init__(self, stdin_fd: int, stdout_fd: int) -> None:
        self._logger = logging.getLogger("ltx")
        self._requests = []
        self._stop = False
        self._connected = False
        self._stdin_fd = stdin_fd
        self._stdout_fd = stdout_fd

    async def __aenter__(self) -> None:
        """
        Connect to the LTX service.
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Disconnect from LTX service.
        """
        await self.disconnect()

    def _blocking_read(self, size: int) -> bytes:
        """
        Blocking I/O method to read from stdout.
        """
        return os.read(self._stdout_fd, size)

    def _blocking_write(self, data: bytes) -> None:
        """
        Blocking I/O method to write on stdin.
        """
        towrite = len(data)
        wrote = os.write(self._stdin_fd, data)

        if towrite != wrote:
            raise altp.LTPException(
                f"Wrote {wrote} bytes but expected {towrite}")

    def _feed_requests(self, data: list) -> None:
        """
        Feed the list of requests with given data.
        """
        # TODO: this method could be improved by using producer/consumer
        # pattern and gathering multiple tasks according with the number
        # of requests we have
        pos = 0

        while pos < len(self._requests):
            request = self._requests[pos]
            request.feed(data)

            if request.completed:
                del self._requests[pos]
            else:
                pos += 1

    def _blocking_producer(self) -> None:
        """
        Blocking I/O producer that reads messages from stdout.
        """
        self._logger.info("Starting message polling")
        self._connected = True

        poller = select.epoll()
        poller.register(self._stdout_fd, select.EPOLLIN)

        # force utf-8 encoding by using raw=False
        unpacker = msgpack.Unpacker(raw=False)

        while not self._stop:
            events = poller.poll(0.1)

            for fdesc, _ in events:
                if fdesc != self._stdout_fd:
                    continue

                data = self._blocking_read(self.BUFFSIZE)
                if not data:
                    continue

                unpacker.feed(data)

                self._logger.debug("Unpacking bytes: %s", data)

                while True:
                    try:
                        msg = unpacker.unpack()
                        if msg:
                            self._logger.info("Received message: %s", msg)
                            self._feed_requests(msg)
                    except msgpack.OutOfData:
                        break

        self._connected = False
        self._logger.info("Ending message polling")

    async def connect(self) -> None:
        """
        Connect to LTX.
        """
        self._logger.info("Connecting to LTX")

        altp.to_thread(self._blocking_producer)

        while not self._connected:
            await asyncio.sleep(1e-6)

        self._logger.info("Connected")

    async def disconnect(self) -> None:
        """
        Disconnect from LTX service.
        """
        self._logger.info("Disconnecting")
        self._stop = True

        while self._connected:
            await asyncio.sleep(1e-6)

        self._logger.info("Disconnected")

    async def send(self, requests: list) -> None:
        """
        Send requests to LTX service. The order is preserved during
        requests execution.
        :param requests: list of requests to send
        :type requests: list
        """
        if not requests:
            raise ValueError("No requests given")

        if not self._connected:
            raise LTXError("Client is not connected to LTX")

        self._logger.info("Sending requests")
        self._requests.extend(requests)

        data = [req.pack() for req in requests]
        tosend = b''.join(data)

        self._blocking_write(bytes(tosend))
