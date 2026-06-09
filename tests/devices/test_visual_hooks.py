"""
Tests for the optional visual-device seam on the OutputDevice base class.

These cover the IP-free integration points that live in the core repo (the
no-op hooks every device inherits), independent of the private visual_device
device, which may or may not be installed.
"""

import numpy as np

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.headless import HeadlessDevice


def test_requires_visual_defaults_false():
    """Audio-only devices must report requires_visual == False."""
    assert HeadlessDevice().requires_visual is False


def test_base_declares_visual_hooks():
    """The base class exposes the optional visual lifecycle hooks."""
    for name in (
        "visual_start",
        "visual_step",
        "visual_on_playback_start",
        "visual_on_playback_end",
        "visual_set_mode",
        "visual_stop",
    ):
        assert hasattr(OutputDevice, name)


def test_visual_hooks_are_safe_noops_on_plain_device():
    """Calling the hooks on a non-visual device does nothing and never raises."""
    dev = HeadlessDevice()
    stereo = np.zeros((100, 2), dtype=np.float32)

    assert dev.visual_start() is None
    assert dev.visual_step() is None
    assert dev.visual_on_playback_start(stereo, 48000, "chunk") is None
    assert dev.visual_on_playback_end() is None
    assert dev.visual_set_mode("speaking") is None
    assert dev.visual_stop() is None
