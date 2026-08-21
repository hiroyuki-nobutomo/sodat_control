"""Adafruit STEMMA Soil Sensor — I2C capacitive soil moisture + temperature.

The board is an Adafruit *seesaw* (ATSAMD10) that exposes:
  - capacitive **moisture** on the touch module (channel 0): a raw count that
    rises with wetness (~200 in dry air … ~2000 in wet soil).
  - the seesaw die **temperature** on the status module (a rough ambient proxy).

It is read directly over ``smbus2`` — the same stack the BME280 driver uses —
so no Blinka / ``adafruit-circuitpython-seesaw`` dependency is added. A seesaw
register read is a write of ``[module_base, function]`` followed, after a short
settle delay, by an N-byte read; that is done here as two ``i2c_rdwr`` messages
so the delay lands between the write and the read.

# Wiring (three sensors on one I2C bus)

Every board ships at I2C address ``0x36``. To run several on one bus, bridge
the on-board address jumpers so each has its own address and give each a
matching ``address:`` in ``config.yaml``:

    sensor 1 = 0x36 (no jumper), 2 = 0x37 (bridge A0), 3 = 0x38 (bridge A1),
    4 = 0x39 (bridge A0 + A1).

Alternatively route them through a TCA9548A multiplexer (all keep 0x36) and add
``mux_address`` + ``mux_channel`` to each config block.
"""

import logging
import time
from datetime import datetime, timezone

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor

try:
    from smbus2 import SMBus, i2c_msg
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False

# seesaw register map (subset used here)
_STATUS_BASE = 0x00
_STATUS_HW_ID = 0x01
_STATUS_TEMP = 0x04
_STATUS_SWRST = 0x7F
_TOUCH_BASE = 0x0F
_TOUCH_CHANNEL_OFFSET = 0x10
# HW_ID values reported by the seesaw MCUs Adafruit ships on this board.
_HW_IDS = (0x55, 0x87)


@register_sensor("STEMMASoil")
class STEMMASoilSensor(Sensor):
    def __init__(self, sensor_id, port=1, address=0x36,
                 mux_address=None, mux_channel=None, interval=60):
        super().__init__(sensor_id, "STEMMASoil", interval)
        self.port = port
        self.address = address
        self.mux_address = mux_address
        self.mux_channel = mux_channel
        self.bus = None
        self._initialized = False

    @classmethod
    def from_config(cls, config, **_):
        return cls(
            sensor_id=config["id"],
            port=config.get("port", 1),
            address=config.get("address", 0x36),
            mux_address=config.get("mux_address"),
            mux_channel=config.get("mux_channel"),
            interval=config.get("interval_seconds", 60),
        )

    # -- low level ---------------------------------------------------------
    def _select_mux(self):
        """Point a TCA9548A at this sensor's channel (no-op without a mux)."""
        if self.mux_address is None or self.mux_channel is None:
            return
        self.bus.write_byte(self.mux_address, 1 << self.mux_channel)

    def _seesaw_read(self, base, reg, length, delay):
        self._select_mux()
        write = i2c_msg.write(self.address, [base, reg])
        self.bus.i2c_rdwr(write)
        time.sleep(delay)
        read = i2c_msg.read(self.address, length)
        self.bus.i2c_rdwr(read)
        return bytes(read)

    def _initialize(self):
        if not HAS_SMBUS:
            raise RuntimeError("smbus2 not installed")

        self.bus = SMBus(self.port)

        # Soft-reset the seesaw and let it come back up.
        try:
            self._select_mux()
            reset = i2c_msg.write(self.address, [_STATUS_BASE, _STATUS_SWRST, 0xFF])
            self.bus.i2c_rdwr(reset)
            time.sleep(0.5)
        except Exception as e:
            logging.warning("STEMMASoil %s: soft-reset failed (continuing): %s",
                            self.sensor_id, e)

        # Best-effort identity check — warn on mismatch, fail only on a
        # missing bus (I2C not enabled) so the error is actionable.
        try:
            hw_id = self._seesaw_read(_STATUS_BASE, _STATUS_HW_ID, 1, 0.005)[0]
            if hw_id not in _HW_IDS:
                logging.warning("STEMMASoil %s: unexpected HW_ID 0x%02X at %s",
                                self.sensor_id, hw_id, hex(self.address))
        except Exception as e:
            if "/dev/i2c" in str(e):
                logging.error("STEMMASoil %s I2C Error: I2C interface not enabled. "
                              "Run 'sudo raspi-config nonint do_i2c 0'. Details: %s",
                              self.sensor_id, e)
            else:
                logging.error("Failed to initialize STEMMASoil %s at %s: %s",
                              self.sensor_id, hex(self.address), e)
            raise

        self._initialized = True
        via = ("" if self.mux_address is None
               else f" via mux {hex(self.mux_address)} ch{self.mux_channel}")
        logging.info("STEMMASoil %s initialized at %s%s",
                     self.sensor_id, hex(self.address), via)

    def _read_moisture(self):
        # The touch read occasionally returns 0xFFFF before the capacitive
        # measurement is ready; retry a few times with a longer settle.
        for attempt in range(4):
            raw = self._seesaw_read(_TOUCH_BASE, _TOUCH_CHANNEL_OFFSET, 2,
                                    0.005 + 0.003 * attempt)
            val = (raw[0] << 8) | raw[1]
            if val != 0xFFFF:
                return val
        raise RuntimeError("moisture read returned 0xFFFF after retries")

    def _read_temperature(self):
        raw = self._seesaw_read(_STATUS_BASE, _STATUS_TEMP, 4, 0.005)
        val = (raw[0] << 24) | (raw[1] << 16) | (raw[2] << 8) | raw[3]
        return val / 65536.0  # seesaw fixed-point → °C

    def read_data(self) -> SensorReading:
        if not self._initialized:
            self._initialize()

        try:
            moisture = self._read_moisture()
            temperature = self._read_temperature()
            return SensorReading(
                sensor_id=self.sensor_id,
                sensor_type=self.sensor_type,
                value={
                    "moisture": moisture,
                    "temperature": round(temperature, 2),
                },
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logging.error("Error reading from STEMMASoil sensor %s: %s",
                          self.sensor_id, e)
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["moisture", "temperature"]
