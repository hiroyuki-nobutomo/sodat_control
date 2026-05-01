import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from src.models import SensorReading

try:
    import gspread
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from tenacity import retry, stop_after_delay, wait_exponential
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

def robust_retry():
    """Retry network operations for up to 120s with exponential backoff."""
    return retry(
        stop=stop_after_delay(120),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )

class Uploader(ABC):
    @abstractmethod
    def upload(self, readings: List[SensorReading]) -> List[str]:
        """
        Uploads a list of sensor readings to the destination.
        Returns a list of timestamps (ISO strings) that were successfully uploaded.
        """
        pass
    
    @abstractmethod
    def upload_log(self, log_path: str):
        """Uploads the local log file to the cloud."""
        pass

class MockUploader(Uploader):
    def __init__(self, storage_path: str = "mock_uploads.jsonl"):
        self.storage_path = storage_path
        logging.info(f"MockUploader initialized with storage at {self.storage_path}")

    def upload(self, readings: List[SensorReading]) -> List[str]:
        """Appends sensor readings to a local JSONL file."""
        successful_timestamps = []
        try:
            with open(self.storage_path, "a") as f:
                for reading in readings:
                    json_str = json.dumps(reading.to_dict())
                    f.write(json_str + "\n")
                    successful_timestamps.append(reading.timestamp.isoformat())
            logging.info(f"Successfully 'uploaded' {len(readings)} readings to {self.storage_path}")
            return successful_timestamps
        except Exception as e:
            logging.error(f"MockUploader failed to write readings: {e}")
            return []
            
    def upload_log(self, log_path: str):
        logging.info(f"MockUploader: Would upload log file {log_path} now.")

class GoogleSheetsUploader(Uploader):
    def __init__(self, token_path: str, folder_id: Optional[str] = None, 
                 data_folder_id: Optional[str] = None, device_id: str = "Unknown",
                 initial_headers: Optional[List[str]] = None):
        if not HAS_GOOGLE:
            raise RuntimeError("Google libraries not installed.")
        
        self.token_path = token_path
        self.images_root_id = folder_id      # Config: images_folder_id (DATA/Images)
        self.data_root_id = data_folder_id   # Config: data_folder_id (DATA)
        self.device_id = device_id
        self.initial_headers = initial_headers or []
        
        self.gc = None
        self.drive_service = None
        self.spreadsheet_id = None
        
        # Subfolder IDs
        self.device_data_folder_id = None
        self.device_images_folder_id = None
        self.device_logs_folder_id = None
        
        # Authenticate immediately (with retry)
        try:
            self._authenticate()
            self._resolve_folder_structure()
            self._resolve_spreadsheet()
        except Exception as e:
            logging.error(f"Initialization failed (Network or Auth): {e}")
            # We don't crash here so the app can start and try again later? 
            # Or we let it crash and systemd restarts?
            # For robustness, we log and proceed, but instance might be broken until self-healed.
            pass

    @robust_retry()
    def _authenticate(self):
        if not os.path.exists(self.token_path):
            raise FileNotFoundError(f"Token file not found: {self.token_path}")
        
        creds = Credentials.from_authorized_user_file(self.token_path)
        self.gc = gspread.authorize(creds)
        self.drive_service = build('drive', 'v3', credentials=creds)
        logging.info("Authenticated with Google Sheets and Drive.")

    def _get_or_create_subfolder(self, parent_id: Optional[str], folder_name: str) -> Optional[str]:
        """Checks if a folder exists inside parent_id, creates it if not."""
        if not parent_id:
            return None
            
        try:
            return self._retry_get_or_create_subfolder(parent_id, folder_name)
        except Exception as e:
            logging.error(f"Failed to resolve subfolder '{folder_name}': {e}")
            return None

    @robust_retry()
    def _retry_get_or_create_subfolder(self, parent_id, folder_name):
        query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = self.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            logging.info(f"Created new subfolder '{folder_name}' ({file.get('id')})")
            return file.get('id')

    def _resolve_folder_structure(self):
        """Resolves/Creates the directory structure in Drive."""
        # 1. Images: DATA/Images/{device_id}
        self.device_images_folder_id = self._get_or_create_subfolder(self.images_root_id, self.device_id)

        # 2. Sensor Data: DATA/sensor/{device_id}
        sensor_root_id = self._get_or_create_subfolder(self.data_root_id, "sensor")
        self.device_data_folder_id = self._get_or_create_subfolder(sensor_root_id, self.device_id)
        
        # 3. Logs: DATA/logs/{device_id}
        logs_root_id = self._get_or_create_subfolder(self.data_root_id, "logs")
        self.device_logs_folder_id = self._get_or_create_subfolder(logs_root_id, self.device_id)

    def _resolve_spreadsheet(self):
        """Finds existing spreadsheet for this device or creates a new one."""
        if not self.device_data_folder_id:
            logging.warning("No device_data_folder_id available. Cannot resolve spreadsheet.")
            return

        target_name = f"SensorData_{self.device_id}"
        
        try:
            self._retry_resolve_spreadsheet(target_name)
        except Exception as e:
            logging.error(f"Failed to resolve spreadsheet after retries: {e}")

    @robust_retry()
    def _retry_resolve_spreadsheet(self, target_name):
        query = f"name = '{target_name}' and '{self.device_data_folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        results = self.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        if files:
            self.spreadsheet_id = files[0]['id']
            logging.info(f"Found existing spreadsheet: {target_name} ({self.spreadsheet_id})")
        else:
            logging.info(f"Spreadsheet {target_name} not found. Creating new one...")
            file_metadata = {
                'name': target_name,
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                'parents': [self.device_data_folder_id]
            }
            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            self.spreadsheet_id = file.get('id')
            logging.info(f"Created new spreadsheet: {target_name} ({self.spreadsheet_id})")
            
            # Add headers immediately
            self._ensure_headers()

    @robust_retry()
    def _ensure_headers(self):
        worksheet = self._get_sheet()
        if not worksheet.row_values(1):
            base_headers = ["Timestamp (JST)", "Device ID"]
            # Combine and sort extra headers for consistency
            extra_headers = sorted(list(set(self.initial_headers)))
            headers = base_headers + extra_headers
            
            worksheet.insert_row(headers, index=1)
            logging.info(f"Initialized headers for new spreadsheet: {headers}")

    @robust_retry()
    def _get_sheet(self):
        if self.spreadsheet_id:
            return self.gc.open_by_key(self.spreadsheet_id).sheet1
        raise ValueError("spreadsheet_id is not set. Check data_folder_id config.")
    
    @robust_retry()
    def _upload_image(self, image_path: str) -> Optional[Tuple[str, str]]:
        """Uploads an image to Google Drive and returns its webViewLink and file id."""
        if not self.device_images_folder_id:
            logging.warning("No device_images_folder_id available for image upload.")
            return None
            
        if not os.path.exists(image_path):
            logging.warning(f"Image file not found: {image_path}")
            return None

        filename = os.path.basename(image_path)
        file_metadata = {
            'name': filename,
            'parents': [self.device_images_folder_id]
        }
        media = MediaFileUpload(image_path, mimetype='image/jpeg')
        
        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        logging.info(f"Uploaded image {filename} to Drive (ID: {file.get('id')})")
        return file.get('webViewLink'), file.get('id')

    def _ensure_initialized(self):
        """Ensures we have active credentials and target spreadsheet IDs."""
        if not self.gc or not self.drive_service:
            logging.info("Attempting to re-authenticate with Google Drive...")
            self._authenticate()
            
        if not self.device_data_folder_id:
            logging.info("Re-resolving folder structure...")
            self._resolve_folder_structure()
            
        if not self.spreadsheet_id:
            logging.info("Re-resolving spreadsheet ID...")
            self._resolve_spreadsheet()

    def upload_log(self, log_path: str):
        """Uploads (overwrites) the log file to Google Drive."""
        # Self-Heal before upload
        try:
            self._ensure_initialized()
        except Exception as e:
            logging.warning(f"Self-healing failed during log upload (likely no connection): {e}")
            return

        if not self.device_logs_folder_id:
            logging.warning("No device_logs_folder_id available. Skipping log upload.")
            return

        if not os.path.exists(log_path):
            logging.warning(f"Log file not found at {log_path}. Skipping upload.")
            return
            
        filename = os.path.basename(log_path)
        
        try:
            self._retry_upload_log(log_path, filename)
        except Exception as e:
            logging.error(f"Failed to upload log file {filename} after retries: {e}")

    @robust_retry()
    def _retry_upload_log(self, log_path, filename):
        # Check if file exists to update it, otherwise create
        query = f"name = '{filename}' and '{self.device_logs_folder_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        files = results.get('files', [])
        
        # Use resumable=False to prevent HttpError 400 on small files
        media = MediaFileUpload(log_path, mimetype='text/plain', resumable=False)
        
        if files:
            # Update existing file
            file_id = files[0]['id']
            self.drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            logging.info(f"Updated log file {filename} in Drive (ID: {file_id})")
        else:
            # Create new file
            file_metadata = {
                'name': filename,
                'parents': [self.device_logs_folder_id]
            }
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            logging.info(f"Created log file {filename} in Drive (ID: {file.get('id')})")

    def upload(self, readings: List[SensorReading]) -> List[str]:
        if not readings:
            return []
            
        # Self-Heal before upload
        try:
            self._ensure_initialized()
        except Exception as e:
            logging.warning(f"Self-healing failed during data upload (likely no connection): {e}")
            return []
            
        try:
            return self._retry_upload_readings(readings)
        except Exception as e:
            logging.error(f"Google Sheets Upload failed after retries: {e}")
            return []

    @robust_retry()
    def _retry_upload_readings(self, readings: List[SensorReading]) -> List[str]:
        worksheet = self._get_sheet()
        
        # 1. Get Current Headers
        headers = worksheet.row_values(1)
        if not headers:
            # Initialize default headers if sheet is empty
            headers = ["Timestamp (JST)", "Device ID"]
            worksheet.insert_row(headers, index=1)
            logging.info("Initialized base headers.")

        # 2. Group Readings by Time Window (60s)
        # Structure: { rounded_timestamp: [reading1, reading2, ...] }
        grouped_readings = {}
        successful_timestamps = [] # We track all successful timestamps from the source list
        jst = timezone(timedelta(hours=9))

        for r in readings:
            # Round to nearest minute to handle jitter
            # This ensures 10:00:01 and 10:00:05 end up in the same row
            ts = r.timestamp
            # Guard against naive datetimes (no tzinfo).  All sensors
            # should produce UTC, but corrupted DB rows or future sensor
            # types might not — silently assuming local time would shift
            # the displayed timestamp by hours.
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rounded_ts = ts.replace(second=0, microsecond=0)
            if ts.second >= 30:
                rounded_ts += timedelta(minutes=1)
            
            if rounded_ts not in grouped_readings:
                grouped_readings[rounded_ts] = []
            grouped_readings[rounded_ts].append(r)

        # 3. Identify Headers needed for this batch
        # We need to scan ALL grouped readings to ensure headers exist before we start building rows
        # Header Format: "Key (Type - ID)" e.g., "Temperature (TDSN7200 - env-02)"
        
        needed_headers = set()
        for r in readings:
            # Anticipate image_direct_link if image_path exists so it gets added to headers
            if "image_path" in r.value and "image_direct_link" not in r.value:
                r.value["image_direct_link"] = ""
                
            for k in r.value.keys():
                # Format Key
                display_key = k.replace("_", " ").title()
                header_name = f"{display_key} ({r.sensor_type} - {r.sensor_id})"
                needed_headers.add(header_name)

        # Update Sheet Headers if new ones found
        new_headers_added = False
        for h_name in sorted(list(needed_headers)):
            found = False
            for existing_h in headers:
                if existing_h.lower() == h_name.lower():
                    found = True
                    break
            
            if not found:
                headers.append(h_name)
                worksheet.update_cell(1, len(headers), h_name)
                logging.info(f"Added new column header: {h_name}")
                new_headers_added = True

        # 4. Build Rows
        rows_to_upload = []
        header_map = {h: i for i, h in enumerate(headers)}

        for rounded_ts, group in sorted(grouped_readings.items()):
            # Initialize row with None
            row = [None] * len(headers)
            
            # Set Timestamp (JST)
            dt_jst = rounded_ts.astimezone(jst)
            row[0] = dt_jst.strftime("%Y-%m-%d %H:%M:%S") # Assumes Timestamp is at index 0
            
            # Set Device ID (Assumes Device ID is at index 1)
            if len(headers) > 1 and headers[1] == "Device ID":
                row[1] = self.device_id
            
            # Fill Data from all readings in this group
            for r in group:
                v = r.value
                image_link = v.get("image_path")

                # Evict stale readings whose local image was already
                # deleted (e.g. by the retention policy) before it
                # could be uploaded.  Mark as "successful" so the DB
                # row is purged, but do NOT add garbage to the Sheet.
                if (image_link
                        and not image_link.startswith("http")
                        and image_link != "IMAGE_UPLOAD_FAILED"
                        and not os.path.exists(image_link)):
                    logging.warning(
                        f"Evicting stale reading {r.timestamp}: "
                        f"local image no longer exists ({image_link})")
                    successful_timestamps.append(r.timestamp.isoformat())
                    continue

                # Image Upload Logic (Atomic per reading)
                if image_link and not image_link.startswith("http") and image_link != "IMAGE_UPLOAD_FAILED":
                    try:
                        upload_result = self._upload_image(image_link)
                        if upload_result:
                            uploaded_link, file_id = upload_result
                            v["image_path"] = uploaded_link
                            v["image_direct_link"] = f"https://drive.google.com/uc?export=view&id={file_id}"
                        else:
                            logging.warning(f"Image upload returned None for {r.timestamp}. Marking as failed.")
                            v["image_path"] = "IMAGE_UPLOAD_FAILED"
                            v["image_direct_link"] = "IMAGE_UPLOAD_FAILED"
                    except Exception as e:
                        logging.warning(f"Image upload exception for {r.timestamp}: {e}. Marking as failed.")
                        v["image_path"] = "IMAGE_UPLOAD_FAILED"
                        v["image_direct_link"] = "IMAGE_UPLOAD_FAILED"
                elif image_link and image_link.startswith("http"):
                    if "image_direct_link" not in v:
                        match = re.search(r'/d/([a-zA-Z0-9_-]+)', image_link)
                        if match:
                            v["image_direct_link"] = f"https://drive.google.com/uc?export=view&id={match.group(1)}"
                        else:
                            v["image_direct_link"] = image_link
                elif image_link == "IMAGE_UPLOAD_FAILED":
                    v["image_direct_link"] = "IMAGE_UPLOAD_FAILED"
                
                # Populate Row
                for key, val in v.items():
                    display_key = key.replace("_", " ").title()
                    header_name = f"{display_key} ({r.sensor_type} - {r.sensor_id})"
                    
                    target_index = -1
                    # Find exact match in header map
                    # (We did case-insensitive check for creation, but map creation is exact string if we rely on headers list)
                    # Let's simple scan or use map.
                    if header_name in header_map:
                        row[header_map[header_name]] = val
                    else:
                        # Fallback case-insensitive
                        for h, idx in header_map.items():
                            if h.lower() == header_name.lower():
                                row[idx] = val
                                break
                
                # Mark this reading as processed for return
                successful_timestamps.append(r.timestamp.isoformat())

            rows_to_upload.append(row)
        
        if rows_to_upload:
            worksheet.append_rows(rows_to_upload)
            logging.info(f"Uploaded {len(rows_to_upload)} rows (merged from {len(readings)} readings) to Google Sheets.")
            return successful_timestamps
        else:
            logging.info("No rows ready for upload (failures or empty).")
            return []
