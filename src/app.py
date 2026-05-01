import logging
import time
import schedule
import os
import glob
import csv
from datetime import datetime
from typing import List, Optional
from src.sensors import Sensor
from src.storage import StorageManager
from src.uploaders import Uploader
from src.status import StatusIndicator
from src.retention import RetentionManager
from src.models import SensorReading

class Application:
    def __init__(
        self, 
        sensors: List[Sensor], 
        storage_path: str, 
        uploader: Uploader,
        status_indicator: Optional[StatusIndicator] = None,
        retention_manager: Optional[RetentionManager] = None,
        wifi_monitor: Optional[any] = None,
        upload_interval: int = 300,
        upload_offset_seconds: int = 60,
        wifi_check_interval: int = 600,
        log_upload_interval: int = 300,
        log_file_path: Optional[str] = None
    ):
        self.sensors = sensors
        self.storage = StorageManager(storage_path)
        self.uploader = uploader
        self.status = status_indicator
        self.retention_manager = retention_manager
        self.wifi_monitor = wifi_monitor
        self.upload_interval = upload_interval
        self.upload_offset_seconds = upload_offset_seconds
        self.wifi_check_interval = wifi_check_interval
        self.log_upload_interval = log_upload_interval
        self.log_file_path = log_file_path
        self._stop_requested = False
        self.uploaded_files_cache = set()
        
        # Setup Archive Directory
        self.archive_dir = os.path.join(os.path.dirname(storage_path), "uploaded_data")
        os.makedirs(self.archive_dir, exist_ok=True)

    def collect_data(self, sensor: Sensor):
        """Task: Read from a specific sensor and save to local storage."""
        try:
            logging.info(f"Starting collection for sensor: {sensor.sensor_id}")
            reading = sensor.read_data()
            self.storage.add_reading(reading)
            logging.info(f"Reading from {sensor.sensor_id} saved to local storage.")
            # Reset error count on success
            sensor.error_count = 0
        except Exception as e:
            # Increment error count
            sensor.error_count += 1
            logging.error(f"Data collection failed for {sensor.sensor_id}: {e} (Failure #{sensor.error_count})")
            
            # Self-Healing: If stuck for too long (e.g. 10 times = ~10-30 mins depending on interval), restart.
            if sensor.error_count > 10:
                msg = f"CRITICAL: Sensor {sensor.sensor_id} failed {sensor.error_count} times consecutively. Force-restarting application to reset hardware."
                logging.critical(msg)
                # Raising exception here crashes the scheduler loop, which propagates to main, which exits.
                # Systemd will then restart the service.
                raise RuntimeError(msg)

            if self.status:
                self.status.signal_error()

    def archive_data(self, readings: List[SensorReading], successful_timestamps: List[str]):
        """Archives successfully uploaded readings to CSV."""
        if not successful_timestamps:
            return

        success_set = set(successful_timestamps)
        # Filter readings that were actually uploaded
        to_archive = [r for r in readings if r.timestamp.isoformat() in success_set]
        
        if not to_archive:
            return

        # Group by date for filename
        # Simplified: Just use today's date for the archive file
        date_str = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(self.archive_dir, f"{date_str}.csv")
        
        file_exists = os.path.exists(filepath)
        
        try:
            with open(filepath, 'a', newline='') as csvfile:
                fieldnames = ['timestamp', 'sensor_id', 'sensor_type', 'value']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                for r in to_archive:
                    writer.writerow({
                        'timestamp': r.timestamp.isoformat(),
                        'sensor_id': r.sensor_id,
                        'sensor_type': r.sensor_type,
                        'value': str(r.value) # Convert dict to string for CSV
                    })
            logging.info(f"Archived {len(to_archive)} readings to {filepath}")
        except Exception as e:
            logging.error(f"Failed to archive data: {e}")

    def upload_log_data(self):
        """Task: Sync all local logs to Google Drive."""
        if not self.log_file_path:
            return
            
        try:
            logging.info("Starting log upload cycle...")
            log_dir = os.path.dirname(self.log_file_path)
            log_basename = os.path.basename(self.log_file_path)
            active_log_path = self.log_file_path
            
            pattern = os.path.join(log_dir, f"{log_basename}*")
            found_logs = glob.glob(pattern)
            
            for log_path in found_logs:
                is_active = (log_path == active_log_path) or (os.path.basename(log_path) == log_basename)
                if not is_active and log_path in self.uploaded_files_cache:
                    continue

                try:
                    self.uploader.upload_log(log_path)
                    if not is_active:
                        self.uploaded_files_cache.add(log_path)
                except Exception as e:
                    logging.warning(f"Failed to upload log {log_path}: {e}")
        except Exception as e:
            logging.error(f"Log upload cycle failed: {e}")

    def upload_sensor_data(self):
        """Task: Retrieve pending readings from storage and upload them."""
        try:
            logging.info("Starting sensor data upload cycle...")
            readings = self.storage.get_pending_readings(limit=100)
            
            if not readings:
                logging.info("No pending readings to upload.")
                return

            # Returns list of successful timestamps (List[str])
            successful_timestamps = self.uploader.upload(readings)
            
            if successful_timestamps:
                # 1. Archive
                self.archive_data(readings, successful_timestamps)
                
                # 2. Remove from DB
                self.storage.remove_readings(successful_timestamps)
                logging.info(f"Successfully uploaded and cleared {len(successful_timestamps)} readings.")
                
                if self.status:
                    self.status.signal_success()
            else:
                logging.warning(f"Sensor data upload failed or no items processed. Readings retained in local storage.")
                if self.status:
                    self.status.signal_error()
                    
        except Exception as e:
            logging.error(f"Sensor data upload cycle failed: {e}")
            if self.status:
                self.status.signal_error()
    
    def run_cleanup(self):
        """Task: Run retention cleanup."""
        if self.retention_manager:
            try:
                # Cleanup Images & Archives
                self.retention_manager.cleanup()
            except Exception as e:
                logging.error(f"Cleanup task failed: {e}")

    def run_wifi_check(self):
        """Task: Check and log WiFi status."""
        if self.wifi_monitor:
            status_msg = self.wifi_monitor.check_wifi()
            logging.info(status_msg)

    def run(self):
        """Main loop: setup schedule and run indefinitely."""
        logging.info("Starting Main Application Loop...")
        if self.status:
            self.status.signal_boot()
        
        # Schedule Collection
        for sensor in self.sensors:
            logging.info(f"Scheduling sensor {sensor.sensor_id} every {sensor.interval} seconds.")
            schedule.every(sensor.interval).seconds.do(self.collect_data, sensor)
            # Run once at startup immediately to avoid initial gap
            self.collect_data(sensor)
        
        if self.retention_manager:
            logging.info(
                "Scheduling retention cleanup every 6 hours; "
                "files older than the configured max age will be deleted."
            )
            schedule.every(6).hours.do(self.run_cleanup)

        # Schedule WiFi Monitor
        if self.wifi_monitor:
            logging.info(f"Scheduling WiFi monitor every {self.wifi_check_interval} seconds.")
            schedule.every(self.wifi_check_interval).seconds.do(self.run_wifi_check)
            # Run once at startup immediately
            self.run_wifi_check()

        # OFFSET STRATEGY: Wait offset time before scheduling the upload loop
        # Use 1-second increments so SIGTERM / _stop_requested can interrupt.
        logging.info(f"Waiting {self.upload_offset_seconds} seconds to offset upload schedule...")
        for _ in range(self.upload_offset_seconds):
            if self._stop_requested:
                logging.info("Stop requested during upload offset wait. Exiting.")
                return
            time.sleep(1)
        
        logging.info(f"Scheduling sensor data upload every {self.upload_interval} seconds.")
        schedule.every(self.upload_interval).seconds.do(self.upload_sensor_data)
        # Run once at startup after offset to push initial reading
        self.upload_sensor_data()

        logging.info(f"Scheduling log upload every {self.log_upload_interval} seconds.")
        schedule.every(self.log_upload_interval).seconds.do(self.upload_log_data)
        # Run once at startup after offset to push initial logs
        self.upload_log_data()
        
        try:
            while not self._stop_requested:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Application stopped by user.")
        except Exception as e:
            logging.error(f"Application crashed: {e}")
            if self.status:
                self.status.signal_error()
            raise