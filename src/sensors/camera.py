"""Camera sensor — captures a JPG via fswebcam, tries every /dev/video* on failure."""

import glob
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor


@register_sensor("Camera")
class CameraSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 10800, output_dir: str = "data/images",
                 device: str = "/dev/video0", resolution: str = "1280x720", device_name: str = "S01"):
        super().__init__(sensor_id, "Camera", interval)
        self.output_dir = output_dir
        self.device = device
        self.resolution = resolution
        self.device_name = device_name
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except OSError:
                pass

    @classmethod
    def from_config(cls, config: dict, *, device_id: str = "Unknown"):
        return cls(
            sensor_id=config["id"],
            interval=config.get("interval_seconds", 10800),
            device=config.get("device", "/dev/video0"),
            resolution=config.get("resolution", "1280x720"),
            output_dir=config.get("output_dir", "data/images"),
            device_name=device_id,
        )

    def read_data(self) -> SensorReading:
        timestamp = datetime.now(timezone.utc)
        # YYYY-MM-DD subdir for organization
        date_dir = timestamp.strftime("%Y-%m-%d")
        full_dir = os.path.join(self.output_dir, date_dir)
        if not os.path.exists(full_dir):
            try:
                os.makedirs(full_dir, exist_ok=True)
            except OSError:
                pass

        # Filename uses JST (UTC+9): {DeviceName}_{SensorID}_{YYYY-MM-DD_HH-MM-SS}.jpg
        jst_timestamp = timestamp + timedelta(hours=9)
        filename = f"{self.device_name}_{self.sensor_id}_{jst_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
        filepath = os.path.join(full_dir, filename)

        # Aggressive discovery: try every available video node, configured one first.
        potential_devices = sorted(glob.glob('/dev/video*'))
        if not potential_devices:
            raise FileNotFoundError("No video devices found (/dev/video*).")

        if self.device in potential_devices:
            potential_devices.remove(self.device)
            potential_devices.insert(0, self.device)

        last_error = ""
        for dev_node in potential_devices:
            cmd = [
                "fswebcam",
                "--no-banner",
                "-d", dev_node,
                "-r", self.resolution,
                "-S", "20",  # Skip 20 frames for auto-exposure stabilization
                filepath,
            ]

            try:
                subprocess.run(cmd, capture_output=True, check=True, timeout=30)
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={"image_path": filepath},
                    timestamp=timestamp,
                )
            except subprocess.TimeoutExpired:
                last_error = f"fswebcam hung for >30s on {dev_node}"
                logging.warning(f"Timeout on {dev_node}. Trying next node...")
                continue
            except subprocess.CalledProcessError as e:
                last_error = e.stderr.decode('utf-8') if e.stderr else str(e)
                logging.warning(f"Failed capture on {dev_node}. Trying next node... Error: {last_error}")
                continue

        logging.error(f"All video nodes failed. Last error: {last_error}")
        raise RuntimeError(f"Camera capture failed on all nodes: {last_error}")

    def get_measurement_keys(self) -> list[str]:
        return ["image_path"]
