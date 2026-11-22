import ctypes
from ctypes import wintypes
import io
import math
import struct
import time
import wave

SAMPLE_RATE = 44100
SND_ASYNC = 0x0001
SND_NODEFAULT = 0x0002
SND_MEMORY = 0x0004

try:
    _winmm = ctypes.windll.winmm
    _winmm.PlaySoundW.argtypes = [wintypes.LPCVOID, wintypes.HMODULE, wintypes.DWORD]
    _winmm.PlaySoundW.restype = wintypes.BOOL
except Exception:
    _winmm = None


def _synthesize_relay_pulse(
    duration_ms,
    f_start,
    f_end,
    body_freq,
    tau_ms,
    amplitude,
    click_strength=0.35,
):
    """Synthesize a warm, damped mechanical relay impulse."""
    num_samples = max(1, int(SAMPLE_RATE * (duration_ms / 1000.0)))
    tau = max(0.0005, tau_ms / 1000.0)
    dur_s = duration_ms / 1000.0

    # Deterministic pseudo-noise seed for organic mechanical contact transient
    lcg = 0x5A3C9E17
    prev_out = 0.0
    alpha = 0.42  # One-pole low-pass smoothing to remove harsh digital aliasing

    samples = []
    phase_main = 0.0
    phase_body = 0.0
    two_pi = 2.0 * math.pi

    for i in range(num_samples):
        t = i / float(SAMPLE_RATE)
        prog = min(1.0, t / max(0.0001, dur_s))

        # Fast attack (0.45 ms) to avoid speaker pop, followed by damped wood/felt exponential decay
        attack = min(1.0, t / 0.00045)
        env = attack * math.exp(-t / tau)

        # Downward pitch glide models the physical armature hitting a damped stop
        freq = f_start + (f_end - f_start) * (prog ** 0.55)
        phase_main += two_pi * freq / SAMPLE_RATE
        phase_body += two_pi * body_freq / SAMPLE_RATE

        tonal = 0.68 * math.sin(phase_main) + 0.32 * math.sin(phase_body)

        # Ultra-brief (1.2 ms) damped mechanical contact transient
        lcg = (1103515245 * lcg + 12345) & 0x7FFFFFFF
        noise = (lcg / 1073741823.5) - 1.0
        contact_env = math.exp(-t / 0.00045)
        raw = amplitude * (env * tonal + click_strength * contact_env * noise)

        # Low-pass filter keeps the click warm and organic
        filtered = prev_out + alpha * (raw - prev_out)
        prev_out = filtered
        val = max(-0.98, min(0.98, filtered))
        samples.append(int(val * 32767.0))

    return samples


def _samples_to_wav_bytes(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def _build_tick_tock_wav(tick_samples, tock_samples, gap_ms=26.0):
    gap_samples = [0] * int(SAMPLE_RATE * (gap_ms / 1000.0))
    return _samples_to_wav_bytes(tick_samples + gap_samples + tock_samples)


class TactileAudioEngine:
    """Low-latency in-memory tactile audio engine for mechanical clicks and notifications."""

    def __init__(self, config_store=None):
        self._config = config_store
        self._last_nav_ts = 0.0
        self._c_buffers = {}
        vol = 100 if config_store is None else int(config_store.get("sound_volume", 100))
        self.set_volume(vol)

    def set_volume(self, volume_pct):
        """Rebuild in-memory WAV buffers scaled to volume_pct (10..100)."""
        pct = max(10, min(100, int(volume_pct)))
        gain = pct / 100.0

        nav_samples = _synthesize_relay_pulse(
            duration_ms=14.0,
            f_start=980.0,
            f_end=470.0,
            body_freq=320.0,
            tau_ms=3.2,
            amplitude=min(0.96, 0.78 * gain),
            click_strength=0.40,
        )
        tick_samples = _synthesize_relay_pulse(
            duration_ms=18.0,
            f_start=1260.0,
            f_end=630.0,
            body_freq=350.0,
            tau_ms=4.2,
            amplitude=min(0.98, 0.96 * gain),
            click_strength=0.48,
        )
        tock_samples = _synthesize_relay_pulse(
            duration_ms=18.0,
            f_start=860.0,
            f_end=410.0,
            body_freq=250.0,
            tau_ms=4.4,
            amplitude=min(0.98, 0.92 * gain),
            click_strength=0.42,
        )

        self._wav_nav = _samples_to_wav_bytes(nav_samples)
        self._wav_press = _samples_to_wav_bytes(tick_samples)
        self._wav_back = _samples_to_wav_bytes(tock_samples)
        self._wav_mode = _build_tick_tock_wav(tick_samples, tock_samples, gap_ms=34.0)

        toast_a = _synthesize_relay_pulse(
            duration_ms=28.0,
            f_start=980.0,
            f_end=960.0,
            body_freq=490.0,
            tau_ms=8.0,
            amplitude=min(0.95, 0.78 * gain),
            click_strength=0.14,
        )
        toast_b = _synthesize_relay_pulse(
            duration_ms=36.0,
            f_start=1310.0,
            f_end=1290.0,
            body_freq=655.0,
            tau_ms=10.5,
            amplitude=min(0.95, 0.84 * gain),
            click_strength=0.12,
        )
        self._wav_toast = _build_tick_tock_wav(toast_a, toast_b, gap_ms=42.0)

        # Keep C buffers pinned in memory so PlaySoundW(SND_MEMORY | SND_ASYNC) is 100% safe
        self._c_buffers = {
            "nav": ctypes.create_string_buffer(self._wav_nav),
            "press": ctypes.create_string_buffer(self._wav_press),
            "back": ctypes.create_string_buffer(self._wav_back),
            "mode": ctypes.create_string_buffer(self._wav_mode),
            "toast": ctypes.create_string_buffer(self._wav_toast),
        }

    def is_enabled(self):
        if self._config is None:
            return True
        return bool(self._config.get("tactile_sound", True))

    def _play_buffer(self, key):
        if not self.is_enabled() or _winmm is None:
            return
        buf = self._c_buffers.get(key)
        if buf is None:
            return
        try:
            _winmm.PlaySoundW(buf, None, SND_MEMORY | SND_ASYNC | SND_NODEFAULT)
        except Exception:
            pass

    def close(self):
        if _winmm is not None:
            try:
                _winmm.PlaySoundW(None, None, 0)
            except Exception:
                pass

    def play_nav(self):
        now = time.monotonic()
        if now - self._last_nav_ts < 0.025:
            return
        self._last_nav_ts = now
        self._play_buffer("nav")

    def play_press(self):
        self._play_buffer("press")

    def play_back(self):
        self._play_buffer("back")

    def play_mode(self):
        self._play_buffer("mode")

    def play_toast(self):
        self._play_buffer("toast")
