import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_profiles import MEDIA_OVERRIDE_MAP, AppProfileManager
from audio_feedback import VolvoBlinkerAudioEngine
from input_backend import AutoRepeater, InputEdgeTracker, MultiTapDetector
import rover_system


class TestInputEdgeTracker(unittest.TestCase):
    def test_b_close_keyboard_consumes_release_and_prevents_escape_leak(self):
        tracker = InputEdgeTracker()
        # User presses B while keyboard is open
        jp, jr, holds = tracker.update({"B"})
        self.assertEqual(jp, frozenset({"B"}))

        # Mode switch to Mouse Mode consumes B while held
        tracker.consume_current({"B"})
        jp2, jr2, holds2 = tracker.update({"B"})
        self.assertEqual(jp2, frozenset())
        self.assertEqual(holds2, frozenset())

        # Releasing B must not trigger release edge while consumed
        jp3, jr3, holds3 = tracker.update(set())
        self.assertEqual(jr3, frozenset())

        # Subsequent fresh press of B triggers normally (Esc in Mouse Mode)
        jp4, _, _ = tracker.update({"B"})
        self.assertEqual(jp4, frozenset({"B"}))

    def test_x_open_keyboard_consumes_backspace_leak(self):
        tracker = InputEdgeTracker()
        jp, _, _ = tracker.update({"X"})
        self.assertEqual(jp, frozenset({"X"}))
        tracker.consume_current({"X"})
        jp2, _, holds2 = tracker.update({"X"})
        self.assertEqual(jp2, frozenset())
        self.assertEqual(holds2, frozenset())


class TestDetectorsAndRepeaters(unittest.TestCase):
    def test_multi_tap_detector_single_and_double(self):
        det = MultiTapDetector(window_sec=0.30)
        self.assertEqual(det.step(True, 1.00), 0)
        self.assertEqual(det.step(False, 1.15), 0)
        self.assertEqual(det.step(False, 1.32), 1)

        self.assertEqual(det.step(True, 2.00), 0)
        self.assertEqual(det.step(True, 2.15), 0)
        self.assertEqual(det.step(False, 2.46), 2)

    def test_multi_tap_detector_immediate_double_tap_radial(self):
        det = MultiTapDetector(window_sec=0.36, immediate_at=2)
        # Single tap does not open radial menu
        self.assertEqual(det.step(True, 1.00), 0)
        self.assertEqual(det.step(False, 1.40), 1)
        # Double tap opens immediately on the second press
        self.assertEqual(det.step(True, 2.00), 0)
        self.assertEqual(det.step(True, 2.18), 2)

    def test_auto_repeater_initial_delay_and_interval(self):
        rep = AutoRepeater(initial_delay=0.30, interval=0.10)
        self.assertTrue(rep.step("X", 1.00))
        self.assertFalse(rep.step("X", 1.15))
        self.assertTrue(rep.step("X", 1.31))
        self.assertFalse(rep.step("X", 1.35))
        self.assertTrue(rep.step("X", 1.42))


class TestConfigAndProfiles(unittest.TestCase):
    def test_config_store_load_save_and_snippets(self):
        orig_dir, orig_path = rover_system.CONFIG_DIR, rover_system.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            rover_system.CONFIG_DIR = tmp
            rover_system.CONFIG_PATH = os.path.join(tmp, "config.json")
            try:
                store = rover_system.ConfigStore(valid_themes=("dark", "light"), valid_actions=("left_click", "escape", "radial_menu", "none"))
                self.assertEqual(store.get_kb_snippets(), [".com", "@gmail.com"])
                store.set_and_save("kb_snippets", ["mi@correo.es", "@outlook.com"])
                reloaded = rover_system.ConfigStore(valid_themes=("dark", "light"), valid_actions=("left_click", "escape", "radial_menu", "none"))
                self.assertEqual(reloaded.get_kb_snippets(), ["mi@correo.es", "@outlook.com"])
            finally:
                rover_system.CONFIG_DIR, rover_system.CONFIG_PATH = orig_dir, orig_path

    def test_app_profile_manager_matching_and_overrides(self):
        class DummyConfig:
            def get(self, k, d=None):
                return True if k == "auto_profiles_enabled" else d

            def snapshot_profile_lists(self):
                return ["eldenring.exe"], ["netflix.exe", "spotify.exe"]

        mgr = AppProfileManager(DummyConfig())
        kind, exe, _ = mgr.evaluate("eldenring.exe")
        self.assertEqual(kind, "game")
        self.assertEqual(exe, "eldenring.exe")

        kind, exe, _ = mgr.evaluate("netflix.exe")
        self.assertEqual(kind, "media")
        eff = mgr.effective_button_map({"D_LEFT": "scroll_left", "A": "left_click"})
        self.assertEqual(eff["D_LEFT"], MEDIA_OVERRIDE_MAP["D_LEFT"])
        self.assertEqual(eff["A"], "left_click")


class TestAudioEngine(unittest.TestCase):
    def test_wav_headers_and_nonblocking_playback(self):
        eng = VolvoBlinkerAudioEngine()
        for buf in (eng._wav_nav, eng._wav_press, eng._wav_back, eng._wav_mode, eng._wav_toast):
            self.assertTrue(buf.startswith(b"RIFF"))
            self.assertIn(b"WAVE", buf[:16])
        eng.play_press()
        eng.close()


if __name__ == "__main__":
    unittest.main()
