"""Popup publication regression; no browser or external services required."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from invisible_playwright._juggler import server as module
from invisible_playwright._juggler.dispatcher import Server
from invisible_playwright._juggler.server import PageDispatcher


class PopupOpenerTests(unittest.TestCase):
    def build(self, opener, on_create=None, assert_unlocked_after=True):
        messages = []

        def emit(message):
            messages.append(message)
            if message.get("method") == "__create__" and on_create is not None:
                on_create(message)

        server = Server()
        server.attach(SimpleNamespace(emit_message=emit))
        context = SimpleNamespace(
            guid="context", options={},
            browser=SimpleNamespace(actions_for_page=lambda *_: None, replay=lambda *_: 0),
        )
        page = object.__new__(PageDispatcher)
        page.injected = SimpleNamespace(install=lambda: None)
        page.lifecycle = SimpleNamespace(wait_for_main_frame=lambda **_: "main")
        page.number = 2

        def install_events():
            if opener is not None and assert_unlocked_after:
                self.assertFalse(opener._close_lock.locked(), "no native event/RPC work under opener lock")

        page._install_events = install_events
        frame = SimpleNamespace(channel={"guid": "frame"}, guid="frame")
        with patch.object(module, "FrameDispatcher", return_value=frame):
            page._build(server, context, "session", SimpleNamespace(dispatch_event=lambda *_: None), opener)
        return messages

    def opener(self, closed=False):
        return SimpleNamespace(_close_lock=threading.Lock(), _announced_closed=closed,
                               channel={"guid": "opener"})

    def test_closed_opener_is_not_a_dangling_initializer_reference(self):
        opener = self.opener(closed=True)
        messages = self.build(opener)
        self.assertNotIn("opener", messages[0]["params"]["initializer"])
        self.assertFalse(opener._close_lock.locked())

    def test_live_opener_reference_is_published_under_its_close_lock(self):
        opener = self.opener()

        def observe(message):
            self.assertTrue(opener._close_lock.locked())
            self.assertEqual(message["params"]["initializer"]["opener"], opener.channel)

        self.build(opener, observe)

    def test_opener_close_cannot_overtake_child_publication(self):
        opener = self.opener()
        publication = []
        attempted = threading.Event()
        finished = threading.Event()
        threads = []

        def close():
            attempted.set()
            with opener._close_lock:
                opener._announced_closed = True
                publication.append("opener_disposed")
            finished.set()

        def observe(_message):
            thread = threading.Thread(target=close)
            threads.append(thread)
            thread.start()
            self.assertTrue(attempted.wait(1))
            self.assertTrue(opener._close_lock.locked())
            publication.append("child_created")

        self.build(opener, observe, assert_unlocked_after=False)
        self.assertTrue(finished.wait(1))
        for thread in threads:
            thread.join(1)
        self.assertEqual(publication, ["child_created", "opener_disposed"])

    def test_no_opener_needs_no_reference_or_lock(self):
        self.assertNotIn("opener", self.build(None)[0]["params"]["initializer"])

    def test_publication_failure_releases_opener_lock(self):
        opener = self.opener()

        def fail(_message):
            raise RuntimeError("fixture publication failure")

        with self.assertRaisesRegex(RuntimeError, "fixture publication failure"):
            self.build(opener, fail)
        self.assertFalse(opener._close_lock.locked())


if __name__ == "__main__":
    unittest.main()
