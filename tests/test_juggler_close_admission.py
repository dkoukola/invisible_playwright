"""Transport admission regression; no browser or external services required."""
import asyncio
import threading
import unittest

from invisible_playwright._juggler.transport import InProcessTransport


class Server:
    def __init__(self):
        self.release = threading.Event()
        self.started = [threading.Event() for _ in range(InProcessTransport.WORKERS)]
        self.calls = []

    def attach(self, transport):
        self.transport = transport

    def block(self, index):
        self.started[index].set()
        self.release.wait(3)
        return index

    def handle(self, message):
        self.calls.append(message["id"])
        if message["method"] == "blocking":
            return self.block(message["params"]["index"])
        if message.get("params", {}).get("fail"):
            raise ValueError("fixture close rejected")
        return {"closed": message["guid"]}

    def shutdown(self):
        self.release.set()


class CloseAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = Server()
        self.transport = InProcessTransport(asyncio.get_running_loop(), self.server)
        self.replies = {}
        self.transport.on_message = lambda value: self.replies[value["id"]].set_result(value)
        await self.transport.connect()

    async def asyncTearDown(self):
        self.server.release.set()
        self.transport.request_stop()
        await self.transport.wait_until_stopped()
        self.assertTrue(all(not thread.is_alive() for thread in self.transport._threads))

    def send(self, identity, method, **params):
        future = asyncio.get_running_loop().create_future()
        self.replies[identity] = future
        self.transport.send({"id": identity, "guid": f"page@{identity}",
                             "method": method, "params": params})
        return future

    async def saturated(self):
        calls = []
        for index in range(self.transport.WORKERS):
            if index % 2:
                calls.append(self.transport.run_blocking(self.server.block, index))
            else:
                calls.append(self.send(index, "blocking", index=index))
        for event in self.server.started:
            self.assertTrue(await asyncio.to_thread(event.wait, 1))
        return calls

    async def test_close_bypasses_blocked_channel_and_fused_calls_without_replaying_them(self):
        calls = await self.saturated()
        close = self.send(100, "close")
        result = await asyncio.wait_for(asyncio.shield(close), 0.5)
        self.assertEqual(result["result"], {"closed": "page@100"})
        self.assertTrue(all(not call.done() for call in calls))
        self.server.release.set()
        await asyncio.gather(*calls)
        self.assertEqual(self.server.calls.count(100), 1)
        self.assertEqual(self.server.calls.count(0), 1)
        self.assertEqual(self.server.calls.count(2), 1)

    async def test_close_protocol_errors_keep_existing_reply_shape(self):
        calls = await self.saturated()
        result = await asyncio.wait_for(self.send(100, "close", fail=True), 0.5)
        self.assertEqual(result["error"]["error"]["name"], "ValueError")
        self.assertIn("fixture close rejected", result["error"]["error"]["message"])
        self.server.release.set()
        await asyncio.gather(*calls)

    async def test_cancelled_fused_future_does_not_block_close_or_break_worker_settlement(self):
        calls = await self.saturated()
        calls[1].cancel()
        result = await asyncio.wait_for(self.send(100, "close"), 0.5)
        self.assertIn("result", result)
        self.server.release.set()
        await asyncio.gather(*calls, return_exceptions=True)
        self.assertEqual(await self.transport.run_blocking(lambda: "still usable"), "still usable")

    async def test_shutdown_drains_already_queued_work_and_joins_both_pools(self):
        calls = await self.saturated()
        self.send(100, "close")
        self.send(101, "ordinary")
        self.transport.request_stop()
        await self.transport.wait_until_stopped()
        self.assertEqual(self.server.calls.count(100), 1)
        self.assertEqual(self.server.calls.count(101), 1)
        # Protocol replies after stop are suppressed as before; fused futures
        # retain their existing safe settlement on the asyncio loop.
        await asyncio.gather(calls[1], calls[3])
        self.assertTrue(all(not thread.is_alive() for thread in self.transport._threads))


if __name__ == "__main__":
    unittest.main()
