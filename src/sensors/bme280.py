"""BME280 — I2C temperature / humidity / pressure sensor."""

import logging
from datetime import datetime, timezone

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor

try:
    import bme280
    import smbus2
    HAS_BME_LIBS = True
except ImportError:
    HAS_BME_LIBS = False


@register_sensor("BME280")
class BME280Sensor(Sensor):
    def __init__(self, sensor_id: str, port: int = 1, address: int = 0x76, interval: int = 60):
        super().__init__(sensor_id, "BME280", interval)
        self.port = port
        self.address = address
        self.bus = None
        self.calibration_params = None
        self._initialized = False

    @classmethod
    def from_config(cls, config: dict, **_):
        return cls(
            sensor_id=config["id"],
            address=config.get("address", 0x76),
            interval=config.get("interval_seconds", 60),
        )

    def _initialize(self):
        if not HAS_BME_LIBS:
            raise RuntimeError("BME280 libraries (smbus2, RPi.bme280) not installed")

        try:
            self.bus = smbus2.SMBus(self.port)
            self.calibration_params = bme280.load_calibration_params(self.bus, self.address)
            self._initialized = True
            logging.info(f"BME280 Sensor {self.sensor_id} initialized at {hex(self.address)}")
        except Exception as e:
            msg = str(e)
            if "No such file or directory: '/dev/i2c" in msg:
                logging.error(f"BME280 I2C Error: I2C interface not enabled. Run 'sudo raspi-config nonint do_i2c 0' to enable. Details: {e}")
            else:
                logging.error(f"Failed to initialize BME280 sensor: {e}")
            raise

    def read_data(self) -> SensorReading:
        if not self._initialized:
            self._initialize()

        try:
            data = bme280.sample(self.bus, self.address, self.calibration_params)
            return SensorReading(
                sensor_id=self.sensor_id,
                sensor_type=self.sensor_type,
                value={
                    "temperature": round(data.temperature, 2),
                    "humidity": round(data.humidity, 2),
                    "pressure": round(data.pressure, 2),
                },
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logging.error(f"Error reading from BME280 sensor {self.sensor_id}: {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["temperature", "humidity", "pressure"]
