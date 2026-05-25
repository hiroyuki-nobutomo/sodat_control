import os
import logging
from datetime import datetime
from typing import List
from src.config import ConfigManager
from src.logger import setup_logging
from src.sensors import Sensor, create_sensor
from src.wifi_monitor import WifiMonitor
from src.uploaders import MockUploader, GoogleSheetsUploader
from src.app import Application
from src.status import StatusIndicator
from src.retention import RetentionManager

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

    if uploader_type == "GoogleDrive":
        logging.info("Using Google Sheets Uploader.")
        credentials_path = cm.get("uploader.credentials_file", "secrets/service_account.json")
        # Master spreadsheet ID is required — every device writes long-form
        # rows into the lab-wide 'All' / 'Images' tabs. Missing config here
        # is a hard error (see GoogleSheetsUploader.__init__).
        uploader = GoogleSheetsUploader(
            credentials_path=credentials_path,
            spreadsheet_id=cm.get("uploader.spreadsheet_id"),
            folder_id=cm.get("uploader.images_folder_id"),
            data_folder_id=cm.get("uploader.data_folder_id"),
            device_id=device_id,
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
