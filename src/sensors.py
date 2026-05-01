import os
import time
import random
import logging
import serial
import subprocess
import json
from datetime import datetime, timezone, timedelta
from abc import ABC, abstractmethod
from typing import Optional

try:
    import smbus2
    import bme280
    HAS_BME_LIBS = True
except ImportError:
    HAS_BME_LIBS = False

from src.models import SensorReading

class Sensor(ABC):
    def __init__(self, sensor_id: str, sensor_type: str, interval: int = 60):
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.interval = interval
        self.error_count = 0  # Track consecutive failures

    @abstractmethod
    def read_data(self) -> SensorReading:
        """Reads data from the sensor and returns a SensorReading instance."""
        pass

    @abstractmethod
    def get_measurement_keys(self) -> list[str]:
        """Returns the list of keys (measurements) this sensor provides."""
        pass

class MockSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60):
        super().__init__(sensor_id, "mock", interval)

    def read_data(self) -> SensorReading:
        """Generates mock temperature and humidity data."""
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=self.sensor_type,
            value={
                "temperature": round(random.uniform(20.0, 30.0), 2),
                "humidity": round(random.uniform(30.0, 70.0), 2)
            },
            timestamp=datetime.now(timezone.utc)
        )

    def get_measurement_keys(self) -> list[str]:
        return ["temperature", "humidity"]

class BME280Sensor(Sensor):
    def __init__(self, sensor_id: str, port: int = 1, address: int = 0x76, interval: int = 60):
        super().__init__(sensor_id, "BME280", interval)
        self.port = port
        self.address = address
        self.bus = None
        self.calibration_params = None
        self._initialized = False

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
                    "pressure": round(data.pressure, 2)
                },
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            logging.error(f"Error reading from BME280 sensor {self.sensor_id}: {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["temperature", "humidity", "pressure"]

class TDSN7200Sensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, model_name: str = "tdsn7200"):
        super().__init__(sensor_id, "TDSN7200", interval)
        self.model_name = model_name
        self.cmd = ["td-usb", self.model_name, "get"]

    def read_data(self) -> SensorReading:
        try:
            result = subprocess.run(self.cmd, capture_output=True, text=True,
                                    check=True, timeout=30)
            output = result.stdout.strip()

            parts = output.split(',')

            if len(parts) >= 3:
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={
                        "temperature": float(parts[0]),
                        "humidity": float(parts[1]),
                        "pressure": float(parts[2])
                    },
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                raise ValueError(f"Unexpected output format: {output}")

        except subprocess.TimeoutExpired:
            logging.error(f"TDSN7200 ({self.model_name}): td-usb hung for >30s (USB stall?)")
            raise
        except Exception as e:
            msg = str(e)
            if "Could not claim interface" in msg or "Device open error" in msg:
                logging.error(
                    "Error reading from TDSN7200: permission denied. "
                    "Check udev rules for idVendor 32ee/idProduct 177d and replug."
                )
            else:
                logging.error(f"Error reading from TDSN7200 ({self.model_name}): {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["temperature", "humidity", "pressure"]

class TDSN7300Sensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, model_name: str = "tdsn7300"):
        super().__init__(sensor_id, "TDSN7300", interval)
        self.model_name = model_name
        self.cmd = ["td-usb", self.model_name, "get"]

    def read_data(self) -> SensorReading:
        try:
            result = subprocess.run(self.cmd, capture_output=True, text=True,
                                    check=True, timeout=30)
            output = result.stdout.strip()

            parts = output.split(',')

            if len(parts) >= 3:
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={
                        "co2": float(parts[0]),
                        "temperature": float(parts[1]),
                        "humidity": float(parts[2])
                    },
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                raise ValueError(f"Unexpected output format: {output}")

        except subprocess.TimeoutExpired:
            logging.error(f"TDSN7300 ({self.model_name}): td-usb hung for >30s (USB stall?)")
            raise
        except Exception as e:
            msg = str(e)
            if "Could not claim interface" in msg or "Device open error" in msg:
                logging.error(
                    "Error reading from TDSN7300: permission denied. "
                    "Check udev rules for idVendor 32ee/idProduct 1785 and replug."
                )
            else:
                logging.error(f"Error reading from TDSN7300 ({self.model_name}): {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["co2", "temperature", "humidity"]

class IWS660CSSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, model_name: str = "iws660"):
        super().__init__(sensor_id, "IWS660CS", interval)
        self.model_name = model_name
        self.cmd = ["td-usb", self.model_name, "get"]

    def read_data(self) -> SensorReading:
        try:
            result = subprocess.run(self.cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            
            if output.replace('.', '', 1).isdigit():
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={"illuminance": float(output)},
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                raise ValueError(f"Unexpected output format: {output}")

        except Exception as e:
            logging.error(f"Error reading from IWS660CS ({self.model_name}): {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["illuminance"]

class SerialJSONSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, port: str = "/dev/ttyACM0", 
                 baud_rate: int = 9600, k_constant: Optional[float] = None):
        super().__init__(sensor_id, "SerialJSON", interval)
        self.port = port
        self.baud_rate = baud_rate
        self.k_constant = k_constant

    def _find_serial_port(self) -> str:
        """Finds the actual serial port, falling back to other ACM/USB ports if unplugged/moved."""
        import glob
        if os.path.exists(self.port):
            return self.port
            
        # Fallback to any connected Arduino-like device
        potential_ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
        if potential_ports:
            fallback_port = potential_ports[0]
            logging.warning(f"Serial port {self.port} not found. Auto-discovering: {fallback_port}")
            return fallback_port
            
        raise FileNotFoundError(f"No serial device found (checked {self.port} and /dev/ttyACM*, /dev/ttyUSB*)")

    def read_data(self) -> SensorReading:
        try:
            actual_port = self._find_serial_port()
            # Context manager ensures port is closed after reading
            with serial.Serial(actual_port, self.baud_rate, timeout=10) as ser:
                # MANDATORY: Wait 2s for Arduino reboot (DTR toggle)
                time.sleep(2)
                
                # Flush input/output to remove noise/stale data from unplug events
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send 'R' command to trigger a reading (Pull Model)
                ser.write(b'R')
                ser.flush()
                
                # Wait for a line
                raw_line = ser.readline()
                if not raw_line:
                    raise TimeoutError(f"No data received from {actual_port} after 'R' command")
                
                line_str = raw_line.decode('utf-8', errors='ignore').strip()
                
                try:
                    data = json.loads(line_str)
                    if not isinstance(data, dict):
                        raise ValueError("JSON root must be an object")
                    
                    # Apply conductivity calculation if k_constant is set and voltage is present
                    if self.k_constant is not None and "voltage_v" in data:
                        # EC (ms/cm) = (K * voltage) / 0.5
                        # This assumes the DFRobot Gravity EC V2 (K=10) logic
                        voltage = float(data["voltage_v"])
                        conductivity = (self.k_constant * voltage) / 0.5
                        data["conductivity_ms_cm"] = round(conductivity, 2)
                        
                    return SensorReading(
                        sensor_id=self.sensor_id,
                        sensor_type=self.sensor_type,
                        value=data, # Dynamic dict
                        timestamp=datetime.now(timezone.utc)
                    )
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON received: {line_str}")

        except Exception as e:
            logging.error(f"Error reading from SerialJSONSensor ({self.port}): {e}")
            raise
    
    def get_measurement_keys(self) -> list[str]:
        # Since it's dynamic JSON, we can't know ahead of time.
        # Returning empty list means headers will be added dynamically on first upload.
        return []

class CameraSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 10800, output_dir: str = "data/images", device: str = "/dev/video0", resolution: str = "1280x720", device_name: str = "S01"):
        super().__init__(sensor_id, "Camera", interval)
        self.output_dir = output_dir
        self.device = device
        self.resolution = resolution
        self.device_name = device_name
        # Ensure output dir exists
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except OSError:
                pass 

    def _find_video_device(self) -> str:
        """Finds a valid video device if the configured one is missing or locked."""
        import glob
        if os.path.exists(self.device):
            return self.device
            
        potential_devices = glob.glob('/dev/video*')
        if potential_devices:
            # Simple heuristic: try the lowest numbered available node
            fallback_device = sorted(potential_devices)[0]
            logging.warning(f"Camera {self.device} not found. Auto-discovering: {fallback_device}")
            return fallback_device
            
        raise FileNotFoundError("No video devices found (/dev/video*).")

    def read_data(self) -> SensorReading:
        timestamp = datetime.now(timezone.utc)
        # Create YYYY-MM-DD subdir (Local/UTC based, kept for consistency)
        date_dir = timestamp.strftime("%Y-%m-%d")
        full_dir = os.path.join(self.output_dir, date_dir)
        if not os.path.exists(full_dir):
            try:
                os.makedirs(full_dir, exist_ok=True)
            except OSError:
                pass
            
        # Generate Filename with JST (UTC+9)
        # Format: {DeviceName}_{SensorID}_{YYYY-MM-DD_HH-MM-SS}.jpg
        jst_timestamp = timestamp + timedelta(hours=9)
        filename = f"{self.device_name}_{self.sensor_id}_{jst_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
        filepath = os.path.join(full_dir, filename)
        
        # AGGRESSIVE DISCOVERY: Try all available video nodes
        import glob
        potential_devices = sorted(glob.glob('/dev/video*'))
        if not potential_devices:
            raise FileNotFoundError("No video devices found (/dev/video*).")

        # Prioritize the configured device if it exists
        if self.device in potential_devices:
            # Move self.device to the front of the list
            potential_devices.remove(self.device)
            potential_devices.insert(0, self.device)

        last_error = ""
        for dev_node in potential_devices:
            cmd = [
                "fswebcam",
                "--no-banner",
                "-d", dev_node,
                "-r", self.resolution,
                "-S", "20", # Skip 20 frames for auto-exposure stabilization
                filepath
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, check=True,
                               timeout=30)
                # If we successfully captured, return immediately
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={"image_path": filepath},
                    timestamp=timestamp
                )
            except subprocess.TimeoutExpired:
                last_error = f"fswebcam hung for >30s on {dev_node}"
                logging.warning(f"Timeout on {dev_node}. Trying next node...")
                continue
            except subprocess.CalledProcessError as e:
                last_error = e.stderr.decode('utf-8') if e.stderr else str(e)
                logging.warning(f"Failed capture on {dev_node}. Trying next node... Error: {last_error}")
                continue

        # If we exhausted all nodes and failed
        logging.error(f"All video nodes failed. Last error: {last_error}")
        raise RuntimeError(f"Camera capture failed on all nodes: {last_error}")

    def get_measurement_keys(self) -> list[str]:
        return ["image_path"]

class WifiMonitor:
    def __init__(self, interface: str = "wlan0"):
        self.interface = interface

    def get_status_label(self, signal_dbm: float) -> str:
        """Translates dBm signal strength into human-readable labels."""
        if signal_dbm >= -60:
            return "[Very Good]"
        elif signal_dbm >= -70:
            return "[Good]"
        elif signal_dbm >= -80:
            return "[Poor]"
        else:
            return "[Very Poor]"

    def check_wifi(self) -> str:
        """Checks WiFi status and returns a formatted log string."""
        try:
            # Run iwconfig to get wifi stats
            result = subprocess.run(["/sbin/iwconfig", self.interface],
                                    capture_output=True, text=True,
                                    check=True, timeout=10)
            output = result.stdout
            
            if 'ESSID:off/any' in output or 'Not-Associated' in output:
                return f"WiFi Health: [No Connection] (Interface: {self.interface} is disconnected)"

            essid = "Unknown"
            if 'ESSID:"' in output:
                essid = output.split('ESSID:"')[1].split('"')[0]

            signal_dbm = None
            if "Signal level=" in output:
                level_str = output.split("Signal level=")[1].split()[0]
                try:
                    signal_dbm = float(level_str)
                except ValueError:
                    pass

            if signal_dbm is not None:
                label = self.get_status_label(signal_dbm)
                quality_str = ""
                if "Link Quality=" in output:
                    quality_str = output.split("Link Quality=")[1].split()[0]
                
                return f"WiFi Health: {label} (ESSID: '{essid}', Signal: {signal_dbm}dBm, Quality: {quality_str})"
            else:
                return f"WiFi Health: [Connected] (ESSID: '{essid}', but signal strength unknown)"

        except Exception as e:
            return f"WiFi Health: [Error] (Failed to check {self.interface}: {e})"
