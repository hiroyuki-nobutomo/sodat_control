"""Mock sensor — emits random temperature/humidity. Used for testing without hardware."""

import random
from datetime import datetime, timezone

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor


@register_sensor("Mock")
class MockSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60):
        super().__init__(sensor_id, "mock", interval)

    def read_data(self) -> SensorReading:
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=self.sensor_type,
            value={
                "temperature": round(random.uniform(20.0, 30.0), 2),
                "humidity": round(random.uniform(30.0, 70.0), 2),
            },
            timestamp=datetime.now(timezone.utc),
        )

    def get_measurement_keys(self) -> list[str]:
        return ["temperature", "humidity"]
