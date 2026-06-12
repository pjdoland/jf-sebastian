"""
Output device package for J.F. Sebastian animatronic system.
Provides plugin-style device support via registry pattern.

Devices are modular, like personalities: every subpackage/module in this package
is imported at startup and self-registers via @register_device. The built-ins
are imported explicitly (a failure there is a real bug and should be loud);
anything else found alongside them, e.g. a private device package cloned or
symlinked into this directory, is imported best-effort, so an optional device
that fails to import (missing optional dependencies, absent on this host) just
logs a warning and the core fleet works unchanged.
"""

import importlib
import logging
import pkgutil

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import DeviceRegistry, register_device

# Built-in device implementations: imported explicitly to trigger registration.
from jf_sebastian.devices.teddy_ruxpin import TeddyRuxpinDevice
from jf_sebastian.devices.squawkers_mccaw import SquawkersMcCawDevice
from jf_sebastian.devices.headless import HeadlessDevice

_logger = logging.getLogger(__name__)
_BUILTIN_MODULES = {
    "base", "factory", "shared", "teddy_ruxpin", "squawkers_mccaw", "headless",
}

# Drop-in devices: import every other subpackage so it can self-register.
for _mod in pkgutil.iter_modules(__path__):
    if _mod.name in _BUILTIN_MODULES or _mod.name.startswith("_"):
        continue
    try:
        importlib.import_module(f"{__name__}.{_mod.name}")
    except Exception as _e:  # optional package: degrade, don't break the fleet
        _logger.warning("Optional device package %r not loaded: %s", _mod.name, _e)

__all__ = [
    'OutputDevice',
    'DeviceRegistry',
    'register_device',
    'TeddyRuxpinDevice',
    'SquawkersMcCawDevice',
    'HeadlessDevice',
]
