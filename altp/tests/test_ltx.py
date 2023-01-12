"""
Unittests for ltx module.
"""
import os
import signal
import asyncio
import subprocess
import pytest
import altp.ltx as ltx

pytestmark = pytest.mark.asyncio

TEST_LTX_BINARY = os.environ.get("TEST_LTX_BINARY", None)


@pytest.mark.ltx
@pytest.mark.skipif(
    not TEST_LTX_BINARY or not os.path.isfile(TEST_LTX_BINARY),
    reason="TEST_LTX_BINARY doesn't exist")
class TestLTX:
    """
    Unittest for LTX class.
    """

    @pytest.fixture(scope="session")
    async def handle(self):
        """
        LTX session handler.
        """
        with subprocess.Popen(
                TEST_LTX_BINARY,
                bufsize=0,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE) as proc:
            async with ltx.Session(
                    proc.stdin.fileno(),
                    proc.stdout.fileno()) as handle:
                yield handle

    async def test_version(self, handle):
        """
        Test version request.
        """
        req = ltx.version()

        version = []
        req.on_complete = lambda x: version.append(x)

        async def complete():
            while not version:
                await asyncio.sleep(1e-6)

            assert isinstance(version.pop(), str)

        await asyncio.gather(*[
            handle.send([req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

    async def test_ping(self, handle):
        """
        Test ping request.
        """
        req = ltx.ping()

        time_ns = []
        req.on_complete = lambda x: time_ns.append(x)

        async def complete():
            while not time_ns:
                await asyncio.sleep(1e-6)

            assert isinstance(time_ns[0], int)
            assert time_ns[0] > 0

        await asyncio.gather(*[
            handle.send([req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

    async def test_ping_flood(self, handle):
        """
        Test multiple ping request in a row.
        """
        times = 100
        requests = []
        completed = []

        for _ in range(times):
            request = ltx.ping()
            request.on_complete = lambda x: completed.append(x)
            requests.append(request)

        async def complete():
            while len(completed) < times:
                await asyncio.sleep(1e-6)

            for res in completed:
                assert isinstance(res, int)
                assert res > 0

        await asyncio.gather(*[
            handle.send(requests),
            asyncio.wait_for(complete(), timeout=10),
        ])

    async def test_execute(self, handle):
        """
        Test execute request.
        """
        completed = []
        stdout = []

        def _stdout_callback(data):
            stdout.append(data)

        req = ltx.execute(0, "uname", stdout_callback=_stdout_callback)
        req.on_complete = lambda x, y, z, w: completed.extend([x, y, z, w])

        async def complete():
            while len(completed) < 4:
                await asyncio.sleep(1e-6)

            assert completed[0] == "Linux\n"
            assert completed[1] > 0
            assert completed[2] == 1
            assert completed[3] == 0

        await asyncio.gather(*[
            handle.send([req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

        assert ''.join(stdout) == "Linux\n"

    async def test_execute_builtin(self, handle):
        """
        Test execute request with builtin command.
        """
        completed = []
        stdout = []

        def _stdout_callback(data):
            stdout.append(data)

        req = ltx.execute(0, "echo ciao", stdout_callback=_stdout_callback)
        req.on_complete = lambda x, y, z, w: completed.extend([x, y, z, w])

        async def complete():
            while len(completed) < 4:
                await asyncio.sleep(1e-6)

            assert completed[0] == "ciao\n"
            assert completed[1] > 0
            assert completed[2] == 1
            assert completed[3] == 0

        await asyncio.gather(*[
            handle.send([req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

        assert ''.join(stdout) == "ciao\n"

    async def test_execute_multiple(self, handle):
        """
        Test multiple execute request in a row.
        """
        times = os.cpu_count()
        completed = []
        requests = []
        stdout = []

        def _stdout_callback(data):
            stdout.append(data)

        for slot in range(times):
            req = ltx.execute(
                slot,
                "echo -n ciao",
                stdout_callback=_stdout_callback)
            req.on_complete = lambda x, y, z, w: completed.append([x, y, z, w])
            requests.append(req)

        async def complete():
            while len(completed) < times:
                await asyncio.sleep(1e-6)

            for args in completed:
                assert args[0] == "ciao"
                assert args[1] > 0
                assert args[2] == 1
                assert args[3] == 0

        await asyncio.gather(*[
            handle.send(requests),
            asyncio.wait_for(complete(), timeout=10),
        ])

        assert len(stdout) == times
        for log in stdout:
            assert log == "ciao"

    async def test_set_file(self, handle, tmp_path):
        """
        Test set_file request.
        """
        data = b'AaXa\x00\x01\x02Zz' * 2048
        pfile = tmp_path / 'file.bin'

        req = ltx.set_file(str(pfile), data)

        async def complete():
            while not os.path.exists(str(pfile)):
                await asyncio.sleep(1e-6)

            content = pfile.read_bytes()
            assert content == data

        await asyncio.gather(*[
            handle.send([req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

    async def test_get_file(self, handle, tmp_path):
        """
        Test get_file request.
        """
        pfile = tmp_path / 'file.bin'
        pfile.write_bytes(b'AaXa\x00\x01\x02Zz' * 1024)
        data = []

        async def complete():
            while not data:
                await asyncio.sleep(1e-6)

            content = pfile.read_bytes()
            assert content == data[0]

        req = ltx.get_file(str(pfile))
        req.on_complete = lambda x: data.append(x)

        await asyncio.gather(*[
            handle.send([req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

    async def test_kill(self, handle):
        """
        Test kill method.
        """
        slot = 0
        completed = []

        exec_req = ltx.execute(slot, "sleep 1")
        exec_req.on_complete = lambda x, y, z, w: completed.extend([
            x, y, z, w
        ])
        kill_req = ltx.kill(slot)

        async def complete():
            while len(completed) < 4:
                await asyncio.sleep(1e-6)

            assert completed[0] == ""
            assert completed[1] > 0
            assert completed[2] == 2
            assert completed[3] == signal.SIGKILL

        await asyncio.gather(*[
            handle.send([exec_req, kill_req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

    async def test_env(self, handle):
        """
        Test env request.
        """
        completed = []

        env_req = ltx.env(0, "LTPROOT", "/opt/ltp")
        exec_req = ltx.execute(0, "echo -n $LTPROOT")
        exec_req.on_complete = lambda x, y, z, w: completed.append(x)

        async def complete():
            while not completed:
                await asyncio.sleep(1e-6)

            assert completed[0] == "/opt/ltp"

        await asyncio.gather(*[
            handle.send([env_req, exec_req]),
            asyncio.wait_for(complete(), timeout=5),
        ])

    async def test_env_multiple(self, handle):
        """
        Test env request.
        """
        times = os.cpu_count()
        completed = []
        requests = []

        env_req = ltx.env(128, "LTPROOT", "/opt/ltp")
        requests.append(env_req)

        for slot in range(times):
            exec_req = ltx.execute(slot, "echo -n $LTPROOT")
            exec_req.on_complete = lambda x, y, z, w: completed.append(x)
            requests.append(exec_req)

        async def complete():
            while len(completed) < times:
                await asyncio.sleep(1e-3)

            for slot in range(times):
                assert completed[slot] == "/opt/ltp"

        await asyncio.gather(*[
            handle.send(requests),
            asyncio.wait_for(complete(), timeout=10),
        ])

    async def test_all_together(self, handle, tmp_path):
        """
        Test all requests together.
        """
        data = b'AaXa\x00\x01\x02Zz' * 1024
        pfile = tmp_path / 'file.bin'
        completed = []
        requests = []

        def on_complete(*args):
            completed.append("done")

        version_req = ltx.version()
        version_req.on_complete = on_complete
        requests.append(version_req)

        setfile_req = ltx.set_file(str(pfile), data)
        setfile_req.on_complete = on_complete
        requests.append(setfile_req)

        ping_req = ltx.ping()
        ping_req.on_complete = on_complete
        requests.append(ping_req)

        env_req = ltx.env(0, "LTPROOT", "/opt/ltp")
        env_req.on_complete = on_complete
        requests.append(env_req)

        exec_req = ltx.execute(0, "sleep 1")
        exec_req.on_complete = on_complete
        requests.append(exec_req)

        kill_req = ltx.kill(0)
        kill_req.on_complete = on_complete
        requests.append(kill_req)

        getfile_req = ltx.get_file(str(pfile))
        getfile_req.on_complete = on_complete
        requests.append(getfile_req)

        async def complete():
            while len(completed) < len(requests):
                await asyncio.sleep(1e-6)

        await asyncio.gather(*[
            handle.send(requests),
            asyncio.wait_for(complete(), timeout=10),
        ])
