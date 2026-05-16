"""Sensor base class, plugin registry, and config-driven factory.

# Adding a new sensor

1. Create `src/sensors/<name>.py`.
2. In that file, subclass `Sensor` and implement `read_data()` and
   `get_measurement_keys()`.
3. Decorate the class with `@register_sensor("<TypeName>")` — the
   `<TypeName>` is the string that will appear in `config.yaml` as
   `- type: <TypeName>`.
4. If the YAML block has options beyond `id` and `interval_seconds`,
   override the `from_config` classmethod to extract them.

That is the only wiring required. The sensors package auto-imports every
sibling module at startup, which triggers each `@register_sensor`
decorator, so `create_sensor()` will find the new type without any edit
to `main.py` or this file.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional, Type

from src.models import SensorReading


class Sensor(ABC):
    def __init__(self, sensor_id: str, sensor_type: str, interval: int = 60):
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.interval = interval
        self.error_count = 0  # consecutive failures, managed by Application

    @abstractmethod
    def read_data(self) -> SensorReading:
        """Reads data from the sensor and returns a SensorReading instance."""

    @abstractmethod
    def get_measurement_keys(self) -> list[str]:
        """Returns the list of measurement keys this sensor produces."""

    @classmethod
    def from_config(cls, config: dict, *, device_id: str = "Unknown") -> "Sensor":
        """Build an instance from a YAML config block.

        Default implementation handles the common `id` + `interval_seconds`
        shape. Sensors with additional options (address, port, k_constant,
        ...) must override this classmethod.
        """
        return cls(
            sensor_id=config["id"],
            interval=config.get("interval_seconds", 60),
        )


# type-name -> Sensor subclass
SENSOR_REGISTRY: Dict[str, Type[Sensor]] = {}


def register_sensor(type_name: str) -> Callable[[Type[Sensor]], Type[Sensor]]:
    """Class decorator that registers a sensor class under `type_name`.

    `type_name` must match the `type:` value used in `config.yaml`.
    """

    def deco(cls: Type[Sensor]) -> Type[Sensor]:
        if type_name in SENSOR_REGISTRY and SENSOR_REGISTRY[type_name] is not cls:
            logging.warning(
                "Sensor type %r already registered as %s; overwriting with %s.",
                type_name, SENSOR_REGISTRY[type_name].__name__, cls.__name__,
            )
        SENSOR_REGISTRY[type_name] = cls
        return cls

    return deco


def create_sensor(sensor_config: dict, *, device_id: str = "S01") -> Optional[Sensor]:
    """Build a Sensor from a YAML config block.

    Looks up the class in SENSOR_REGISTRY by the `type:` field, then
    delegates instance construction to the class's `from_config`.
    Returns None on unknown type or initialization failure (the caller
    keeps running with the remaining sensors).
    """
    s_type = sensor_config.get("type")
    s_id = sensor_config.get("id")
    cls = SENSOR_REGISTRY.get(s_type)
    if cls is None:
        logging.warning(
            "Unknown sensor type %r (registered types: %s)",
            s_type, sorted(SENSOR_REGISTRY),
        )
        return None
    try:
        return cls.from_config(sensor_config, device_id=device_id)
    except Exception as e:
        logging.error("Failed to initialize sensor %s (%s): %s", s_id, s_type, e)
        return None
