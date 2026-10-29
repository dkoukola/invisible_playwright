"""ARIA locator strictness without changing upstream atomic read behavior."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from invisible_core.juggler.injected import EvaluationError
from invisible_playwright._juggler.server import FrameDispatcher


class AriaStrictnessTests(unittest.TestCase):
    def setUp(self):
        self.injected = Mock()
        self.frame = object.__new__(FrameDispatcher)
        self.frame.page = SimpleNamespace(injected=self.injected)
        self.frame.frame_id = "main-frame"
        self.frame.enter_frames = Mock(return_value=("child-frame", "resolved-selector"))

    def test_locator_is_strict_without_a_wire_strict_field_or_with_false(self):
        for extra in [{}, {"strict": False}]:
            with self.subTest(extra=extra):
                self.injected.reset_mock()
                self.injected.read_match.return_value = (True, "- heading fixture")
                self.assertEqual(self.frame.op_aria_snapshot({
                    "selector": "original-selector", "timeout": 2000, "mode": "ai", **extra,
                }), {"value": "- heading fixture"})
                self.injected.read_match.assert_called_once()
                call = self.injected.read_match.call_args
                self.assertEqual(call.args, (
                    "child-frame", "resolved-selector", "ariaSnapshot", {"mode": "ai"},
                ))
                self.assertTrue(call.kwargs["strict"])
                self.assertGreater(call.kwargs["timeout"], 0)
                self.assertLessEqual(call.kwargs["timeout"], 2)
                self.injected.query_selector.assert_not_called()
                self.injected.dispose.assert_not_called()

    def test_strict_error_is_not_retried_or_replaced(self):
        error = EvaluationError("strict mode violation")
        self.injected.read_match.side_effect = error
        with self.assertRaises(EvaluationError) as raised:
            self.frame.op_aria_snapshot({"selector": ".duplicate"})
        self.assertIs(raised.exception, error)
        self.injected.read_match.assert_called_once()

    def test_whole_page_snapshot_keeps_the_document_path(self):
        self.injected.call.return_value = "- document fixture"
        self.assertEqual(self.frame.op_aria_snapshot({"mode": "ai"}),
                         {"snapshot": "- document fixture"})
        self.injected.read_match.assert_not_called()
        self.frame.enter_frames.assert_not_called()
        self.assertEqual(self.injected.call.call_args.args[0], "main-frame")
        self.assertEqual(self.injected.call.call_args.args[2], {"mode": "ai"})


if __name__ == "__main__":
    unittest.main()
