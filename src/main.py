import os
import logging
from datetime import datetime
from typing import List, Optional
from src.config import ConfigManager
from src.logger import setup_logging
from src.sensors import Sensor, BME280Sensor, MockSensor, TDSN7200Sensor, TDSN7300Sensor, IWS660CSSensor, SerialJSONSensor, CameraSensor, WifiMonitor
from src.uploaders import MockUploader, GoogleSheetsUploader
from src.app import Application
from src.status import StatusIndicator
from src.retention import RetentionManager

def create_sensor(sensor_config: dict, device_id: str = "S01") -> Optional[Sensor]:
    """Factory to create a sensor instance from config."""
    s_type = sensor_config.get("type")
    s_id = sensor_config.get("id")
    interval = sensor_config.get("interval_seconds", 60)
    
    try:
        if s_type == "BME280":
            address = sensor_config.get("address", 0x76)
            return BME280Sensor(sensor_id=s_id, address=address, interval=interval)
        elif s_type == "Mock":
            return MockSensor(sensor_id=s_id, interval=interval)
        elif s_type == "TDSN7200":
            return TDSN7200Sensor(sensor_id=s_id, interval=interval)
        elif s_type == "TDSN7300":
            return TDSN7300Sensor(sensor_id=s_id, interval=interval)
        elif s_type == "IWS660CS":
            return IWS660CSSensor(sensor_id=s_id, interval=interval)
        elif s_type == "SerialJSON":
            port = sensor_config.get("port", "/dev/ttyACM0")
            baud_rate = sensor_config.get("baud_rate", 9600)
            k_constant = sensor_config.get("k_constant")
            return SerialJSONSensor(sensor_id=s_id, interval=interval, port=port, 
                                    baud_rate=baud_rate, k_constant=k_constant)
        elif s_type == "Camera":
            device = sensor_config.get("device", "/dev/video0")
            resolution = sensor_config.get("resolution", "1280x720")
            output_dir = sensor_config.get("output_dir", "data/images")
            # Pass device_id here
            return CameraSensor(sensor_id=s_id, interval=interval, device=device, 
                                resolution=resolution, output_dir=output_dir, device_name=device_id)
        else:
            logging.warning(f"Unknown sensor type: {s_type}")
            return None
    except Exception as e:
        logging.error(f"Failed to initialize sensor {s_id} ({s_type}): {e}")
        return None

def main():
    # 1. Load Configuration
    cm = ConfigManager()
    
    # Global Device ID (Fetch early for logging)
    device_id = cm.get("device_id", "S01")

    # 2. Setup Logging
    log_level = cm.get("logging.level", "INFO")
    
    # Determine log file based on Device ID and run start time
    log_dir = "log"
    os.makedirs(log_dir, exist_ok=True)
    # Fixed filename to allow rotation. 
    # History is preserved via TimedRotatingFileHandler (app.log.YYYY-MM-DD).
    log_file = os.path.join(log_dir, "app.log")
    
    setup_logging(level=log_level, log_file=log_file)
    
    logging.info("--- Starting Sensor SFC Application ---")
    logging.info(f"Device ID: {device_id}")
    logging.info(f"Logging to: {log_file}")
    
    # 3. Initialize Status Indicator
    led_pin = cm.get("status_led_pin", 17)
    status_indicator = StatusIndicator(pin=led_pin)
    
    # 4. Initialize Sensors
    sensors: List[Sensor] = []

    sensor_list = cm.get("sensors") or []

    for s_conf in sensor_list:
        sensor = create_sensor(s_conf, device_id=device_id)
        if sensor:
            sensors.append(sensor)
            
    if not sensors:
        logging.warning("No sensors successfully initialized. Application will run idle.")
    else:
        logging.info(f"Initialized {len(sensors)} sensors.")
    
    # 5. Initialize Uploader
    uploader_type = cm.get("uploader.type", "Mock")
    
    # Pre-calculate headers for Google Sheets
    initial_headers = []
    for sensor in sensors:
        try:
            keys = sensor.get_measurement_keys()
            for k in keys:
                display_key = k.replace("_", " ").title()
                header_name = f"{display_key} ({sensor.sensor_type} - {sensor.sensor_id})"
                initial_headers.append(header_name)
        except Exception as e:
            logging.warning(f"Could not determine headers for sensor {sensor.sensor_id}: {e}")

    if uploader_type == "GoogleDrive":
        logging.info("Using Google Sheets Uploader.")
        uploader = GoogleSheetsUploader(
            token_path=cm.get("uploader.token_file", "secrets/token.json"),
            folder_id=cm.get("uploader.images_folder_id"),    # New Config
            data_folder_id=cm.get("uploader.data_folder_id"), # New Config
            device_id=device_id,
            initial_headers=initial_headers
        )
    else:
        logging.info("Using Mock Uploader.")
        uploader = MockUploader(storage_path=cm.get("uploader.mock_path", "uploads.jsonl"))
    
    # 6. Initialize Retention Manager
    retention_manager = None
    if cm.get("storage.retention.enabled", False):
        images_dir = cm.get("storage.retention.images_dir", "data/images")
        
        # Calculate Archive Dir based on DB Path to match App logic
        db_path = cm.get("storage.db_path", "data/sensor/sensor_data.db")
        archive_dir = os.path.join(os.path.dirname(db_path), "uploaded_data")
        
        max_age_days = cm.get("storage.retention.max_age_days", 14)
        
        # Pass list of directories
        retention_manager = RetentionManager(target_dirs=[images_dir, archive_dir], max_age_days=max_age_days)
        logging.info(f"Retention Manager initialized (Max Age: {max_age_days} days). Monitoring: {images_dir}, {archive_dir}")

    # 7. Initialize Wifi Monitor
    wifi_monitor = WifiMonitor(interface="wlan0")
    wifi_check_interval = cm.get("wifi_monitor_interval_seconds", 600)

    # 8. Initialize and Run Application
    upload_interval = cm.get("uploader.interval_seconds", 300)
    log_upload_interval = cm.get("uploader.log_interval_seconds", upload_interval)

    app = Application(
        sensors=sensors,
        storage_path=cm.get("storage.db_path", "data/sensor/sensor_data.db"),
        uploader=uploader,
        status_indicator=status_indicator,
        retention_manager=retention_manager,
        wifi_monitor=wifi_monitor,
        upload_interval=upload_interval,
        upload_offset_seconds=cm.get("uploader.offset_seconds", 300),
        wifi_check_interval=wifi_check_interval,
        log_upload_interval=log_upload_interval,
        log_file_path=log_file
    )
    
    app.run()

if __name__ == "__main__":
    main()
