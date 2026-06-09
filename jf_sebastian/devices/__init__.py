"""
Output device package for J.F. Sebastian animatronic system.
Provides plugin-style device support via registry pattern.
"""

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import DeviceRegistry, register_device

# Import device implementations to trigger registration
from jf_sebastian.devices.teddy_ruxpin import TeddyRuxpinDevice
from jf_sebastian.devices.squawkers_mccaw import SquawkersMcCawDevice
from jf_sebastian.devices.headless import HeadlessDevice

# Optional private visual device(s). The visual_device device and its Panda3D
# renderer live in jf_sebastian/visual/, which is gitignored and slated to become
# a private git submodule (it can bundle licensed character assets). Importing it
# here lets it self-register via @register_device when present. The import is
# best-effort: ImportError simply means the module isn't installed on this host,
# and the core fleet works unchanged. (The package is written so this succeeds
# even when the heavy rendering deps like panda3d are absent — those load lazily
# only when a window actually opens.)
try:
    import jf_sebastian.visual  # noqa: F401  (self-registers 'visual_device')
except ImportError:
    pass

__all__ = [
    'OutputDevice',
    'DeviceRegistry',
    'register_device',
    'TeddyRuxpinDevice',
    'SquawkersMcCawDevice',
    'HeadlessDevice',
]
