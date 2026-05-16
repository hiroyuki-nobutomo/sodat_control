"""Sensor plugin package.

Importing this package eagerly imports every sibling module, which triggers
each module's `@register_sensor(...)` decorator. After the package is
imported, `SENSOR_REGISTRY` is populated and `create_sensor(config)` can
build any registered sensor from a YAML block.

To add a sensor, drop a new `src/sensors/<name>.py` — no further wiring.
"""

import importlib as _importlib
import pkgutil as _pkgutil

from src.sensors.base import (
    SENSOR_REGISTRY,
    Sensor,
    create_sensor,
    register_sensor,
)

# Auto-import every sibling module so each @register_sensor decorator fires.
# Skip the base module (already imported above) and dunder/private modules.
for _module_info in _pkgutil.iter_modules(__path__):
    if _module_info.name == "base" or _module_info.name.startswith("_"):
        continue
    _importlib.import_module(f"{__name__}.{_module_info.name}")

__all__ = ["Sensor", "SENSOR_REGISTRY", "create_sensor", "register_sensor"]
