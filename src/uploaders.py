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
    from google.oauth2.service_account import Credentials as SACredentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from tenacity import retry, stop_after_delay, wait_exponential
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Tab names inside the lab-wide master spreadsheet. Both must exist before the
# uploader runs; this code never creates them (the QUERY-based view tabs such
# as 'S01' that researchers consume must not be touched).
SHEET_SCALAR = "All"
SHEET_IMAGES = "Images"

# Long-form ("tidy") layout. Every scalar measurement becomes one row in
# `All`; every camera capture becomes one row in `Images`. Layouts are
# verified at startup but never written by code — Operators maintain them.
EXPECTED_HEADERS_SCALAR = [
    "Timestamp (JST)", "Device ID", "Sensor Type", "Sensor ID",
    "Metric", "Value", "Unit",
]
EXPECTED_HEADERS_IMAGES = [
    "Timestamp (JST)", "Device ID", "Sensor ID", "webViewLink", "directLink",
]

# Metric → unit suffix shown in the Unit column. Unknown metric names
# (e.g., custom keys from Arduino over SerialJSON) get an empty Unit cell
# rather than a guess — researchers can fill those in via the master sheet
# if/when conventions stabilise.
UNIT_BY_METRIC = {
    "temperature": "℃",
    "humidity":    "%",
    "pressure":    "hPa",
    "illuminance": "lx",
    "co2":         "ppm",
}

# Camera readings carry a local file path under value["image_path"] before
# upload; that key signals "this is a camera capture, not a scalar metric"
# and routes the row to the Images sheet instead of All. After a failed
# upload the path is replaced with IMAGE_UPLOAD_FAILED so retries don't
# re-attempt a known-bad image.
CAMERA_VALUE_KEY = "image_path"
IMAGE_UPLOAD_FAILED = "IMAGE_UPLOAD_FAILED"

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
    def __init__(self, credentials_path: str, spreadsheet_id: str,
                 folder_id: Optional[str] = None,
                 data_folder_id: Optional[str] = None,
                 device_id: str = "Unknown"):
        if not HAS_GOOGLE:
            raise RuntimeError("Google libraries not installed.")
        # spreadsheet_id is mandatory — refuse to start rather than silently
        # create a stray per-device file (the master sheet is human-managed).
        if not spreadsheet_id:
            raise ValueError(
                "uploader.spreadsheet_id is required. Set it in config.yaml "
                "(under 'uploader:') to the ID of the lab-wide master sheet "
                "that contains the 'All' and 'Images' tabs."
            )
        # Catch un-substituted template placeholders early — otherwise the
        # service starts, hits 404 against the literal placeholder string,
        # and silently retains every reading in the local SQLite buffer.
        for name, value in (
            ("uploader.spreadsheet_id", spreadsheet_id),
            ("uploader.data_folder_id", data_folder_id),
            ("uploader.images_folder_id", folder_id),
        ):
            if isinstance(value, str) and value.startswith("REPLACE_WITH_"):
                raise ValueError(
                    f"{name} is still the template placeholder '{value}'. "
                    f"Set the real Drive ID in config.yaml or via "
                    f"scripts/util_config.py."
                )

        self.credentials_path = credentials_path
        self.images_root_id = folder_id      # config: uploader.images_folder_id
        self.data_root_id = data_folder_id   # config: uploader.data_folder_id (logs)
        self.device_id = device_id
        self.spreadsheet_id = spreadsheet_id

        self.gc = None
        self.drive_service = None
        self.spreadsheet = None
        self.scalar_ws = None
        self.images_ws = None
        self.device_images_folder_id = None
        self.device_logs_folder_id = None

        # Swallow init failures so the app can keep running and self-heal on
        # the next upload cycle (Wi-Fi / NTP may not be ready at boot).
        try:
            self._authenticate()
            self._resolve_folder_structure()
            self._open_sheets()
        except Exception as e:
            logging.error(f"Initialization failed (Network or Auth): {e}")

    @robust_retry()
    def _authenticate(self):
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")

        with open(self.credentials_path) as f:
            cred_data = json.load(f)

        if cred_data.get("type") != "service_account":
            raise ValueError(
                f"Credentials file {self.credentials_path} is not a Service Account JSON "
                f"(type={cred_data.get('type')!r}). v2 only supports Service Accounts."
            )
        creds = SACredentials.from_service_account_info(cred_data, scopes=GOOGLE_SCOPES)

        self.gc = gspread.authorize(creds)
        self.drive_service = build('drive', 'v3', credentials=creds)
        logging.info("Authenticated with Google Sheets and Drive via Service Account.")

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
        # supportsAllDrives + includeItemsFromAllDrives are required when any of
        # the target folders live in a Shared Drive — Service Accounts have no
        # personal storage quota, so the only way to upload images/logs is to
        # use a Shared Drive (the quota is the drive's, not the SA's).
        results = self.drive_service.files().list(
            q=query, spaces='drive', fields='files(id, name)',
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files = results.get('files', [])

        if files:
            return files[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            file = self.drive_service.files().create(
                body=file_metadata, fields='id',
                supportsAllDrives=True,
            ).execute()
            logging.info(f"Created new subfolder '{folder_name}' ({file.get('id')})")
            return file.get('id')

    def _resolve_folder_structure(self):
        """Resolve per-device Drive subfolders for images + logs."""
        # Images: DATA/Images/{device_id}
        self.device_images_folder_id = self._get_or_create_subfolder(self.images_root_id, self.device_id)
        # Logs: DATA/logs/{device_id}
        logs_root_id = self._get_or_create_subfolder(self.data_root_id, "logs")
        self.device_logs_folder_id = self._get_or_create_subfolder(logs_root_id, self.device_id)

    def _open_sheets(self):
        """Open the master spreadsheet and resolve the All + Images tabs.

        Both tabs are expected to exist (operators maintain them, including
        the QUERY-based per-device view tabs which this code must never
        touch). A WorksheetNotFound here is a hard configuration error.
        """
        try:
            self._retry_open_sheets()
        except Exception as e:
            logging.error(f"Failed to open master spreadsheet {self.spreadsheet_id}: {e}")
            # Leave scalar_ws / images_ws as None — _ensure_initialized retries.

    @robust_retry()
    def _retry_open_sheets(self):
        self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
        self.scalar_ws = self._open_tab(SHEET_SCALAR)
        self.images_ws = self._open_tab(SHEET_IMAGES)
        # Best-effort header sanity check — warn only, never rewrite, since
        # the operator may intentionally have extra trailing columns.
        self._warn_if_headers_mismatch(self.scalar_ws, EXPECTED_HEADERS_SCALAR, SHEET_SCALAR)
        self._warn_if_headers_mismatch(self.images_ws, EXPECTED_HEADERS_IMAGES, SHEET_IMAGES)
        logging.info(
            f"Master spreadsheet opened: id={self.spreadsheet_id} "
            f"tabs=[{SHEET_SCALAR}, {SHEET_IMAGES}]"
        )

    def _open_tab(self, name):
        try:
            return self.spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            raise RuntimeError(
                f"Tab '{name}' not found in spreadsheet {self.spreadsheet_id}. "
                "Create it manually with the expected headers; this code never "
                "creates sheet tabs."
            )

    @staticmethod
    def _warn_if_headers_mismatch(worksheet, expected, tab_name):
        try:
            actual = worksheet.row_values(1)
        except Exception as e:
            logging.warning(f"Could not read header row of '{tab_name}': {e}")
            return
        # Trim trailing empties so a sheet with extra blank cols still matches.
        actual_trimmed = list(actual[:len(expected)])
        if actual_trimmed != expected:
            logging.warning(
                f"Header row of '{tab_name}' differs from expected. "
                f"Expected first {len(expected)} columns: {expected}. "
                f"Got: {actual_trimmed}. Will append rows anyway — verify the "
                "view sheets still produce sensible output."
            )


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
            fields='id, webViewLink',
            supportsAllDrives=True,
        ).execute()

        logging.info(f"Uploaded image {filename} to Drive (ID: {file.get('id')})")
        return file.get('webViewLink'), file.get('id')

    def _ensure_initialized(self):
        """Self-heal: re-authenticate / re-resolve folders / re-open sheets
        if any of them are missing (typically because the first attempt at
        boot raced Wi-Fi / NTP)."""
        if not self.gc or not self.drive_service:
            logging.info("Attempting to re-authenticate with Google...")
            self._authenticate()

        if not self.device_images_folder_id or not self.device_logs_folder_id:
            logging.info("Re-resolving Drive folder structure...")
            self._resolve_folder_structure()

        if self.scalar_ws is None or self.images_ws is None:
            logging.info("Re-opening master spreadsheet tabs...")
            self._open_sheets()

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
        results = self.drive_service.files().list(
            q=query, spaces='drive', fields='files(id)',
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files = results.get('files', [])

        # Use resumable=False to prevent HttpError 400 on small files
        media = MediaFileUpload(log_path, mimetype='text/plain', resumable=False)

        if files:
            # Update existing file
            file_id = files[0]['id']
            self.drive_service.files().update(
                fileId=file_id,
                media_body=media,
                supportsAllDrives=True,
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
                fields='id',
                supportsAllDrives=True,
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
        """Long-form / tidy upload.

        - Every scalar metric (temperature, humidity, pressure, illuminance, co2,
          plus any future / Arduino-emitted key) becomes one row in `All`:
          [Timestamp (JST), Device ID, Sensor Type, Sensor ID, Metric, Value, Unit].
        - Every camera capture becomes one row in `Images`:
          [Timestamp (JST), Device ID, Sensor ID, webViewLink, directLink].
        - Missing / null values do not produce empty rows — the metric is
          skipped entirely.
        - Readings within the same minute share one Timestamp string so
          Looker Studio can pivot back to wide form when needed.
        """
        if self.scalar_ws is None or self.images_ws is None:
            raise RuntimeError("Master spreadsheet tabs not initialised.")
        scalar_sheet = self.scalar_ws
        images_sheet = self.images_ws

        jst = timezone(timedelta(hours=9))
        successful_timestamps: List[str] = []
        scalar_rows: List[list] = []
        image_rows: List[list] = []

        for r in readings:
            # Normalise the timestamp into a stable per-minute JST string so
            # all rows from the same upload cycle share a Timestamp value
            # (lets the dashboard group/join scalar rows with image rows).
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rounded_ts = ts.replace(second=0, microsecond=0)
            if ts.second >= 30:
                rounded_ts += timedelta(minutes=1)
            ts_jst_str = rounded_ts.astimezone(jst).strftime("%Y-%m-%d %H:%M:%S")

            value_dict = r.value or {}
            iso_ts = r.timestamp.isoformat()

            # ----- Camera readings → Images sheet -----
            if CAMERA_VALUE_KEY in value_dict:
                image_link = value_dict.get(CAMERA_VALUE_KEY)

                # Stale reading: local file already trimmed by retention.
                # Mark successful so the DB row goes away, but don't write
                # garbage to Sheets.
                if (image_link
                        and not str(image_link).startswith("http")
                        and image_link != IMAGE_UPLOAD_FAILED
                        and not os.path.exists(image_link)):
                    logging.warning(
                        f"Evicting stale reading {r.timestamp}: "
                        f"local image no longer exists ({image_link})")
                    successful_timestamps.append(iso_ts)
                    continue

                web_view_link = None
                direct_link = None

                if image_link and not str(image_link).startswith("http") and image_link != IMAGE_UPLOAD_FAILED:
                    # Local path — upload to Drive now.
                    try:
                        upload_result = self._upload_image(image_link)
                        if upload_result:
                            web_view_link, file_id = upload_result
                            direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
                        else:
                            logging.warning(
                                f"Image upload returned None for {r.timestamp}; skipping row.")
                            # Don't append a row, don't mark successful — let the next cycle retry.
                            continue
                    except Exception as e:
                        logging.warning(
                            f"Image upload exception for {r.timestamp}: {e}; skipping row.")
                        continue
                elif image_link and str(image_link).startswith("http"):
                    # Already-uploaded URL persisted from a previous cycle.
                    web_view_link = image_link
                    match = re.search(r'/d/([a-zA-Z0-9_-]+)', image_link)
                    if match:
                        direct_link = f"https://drive.google.com/uc?export=view&id={match.group(1)}"
                    else:
                        direct_link = image_link
                else:
                    # image_link is empty / IMAGE_UPLOAD_FAILED — skip row.
                    successful_timestamps.append(iso_ts)
                    continue

                image_rows.append([
                    ts_jst_str, self.device_id, r.sensor_id,
                    web_view_link, direct_link,
                ])
                successful_timestamps.append(iso_ts)
                continue

            # ----- Scalar readings → All sheet (one row per metric) -----
            wrote_any = False
            for metric, value in value_dict.items():
                # None and empty string are missing; numeric 0 is a real value.
                if value is None:
                    continue
                if isinstance(value, str) and value.strip() == "":
                    continue
                scalar_rows.append([
                    ts_jst_str,
                    self.device_id,
                    r.sensor_type,
                    r.sensor_id,
                    metric,
                    value,
                    UNIT_BY_METRIC.get(metric, ""),
                ])
                wrote_any = True

            # Whether or not the reading produced rows, mark it processed so
            # we don't try again — readings with all-null metrics are a sensor
            # health issue, not an upload failure.
            successful_timestamps.append(iso_ts)
            if not wrote_any:
                logging.debug(
                    f"Reading {r.sensor_id}@{r.timestamp} had no non-null metrics; "
                    "no row appended.")

        # Append in two separate batched calls. USER_ENTERED so numeric
        # strings ("23.5") are stored as numbers, which Looker Studio needs
        # for the Value column.
        if scalar_rows:
            scalar_sheet.append_rows(scalar_rows, value_input_option="USER_ENTERED")
        if image_rows:
            images_sheet.append_rows(image_rows, value_input_option="USER_ENTERED")

        logging.info(
            f"Uploaded {len(scalar_rows)} scalar rows to '{SHEET_SCALAR}' and "
            f"{len(image_rows)} image rows to '{SHEET_IMAGES}' "
            f"(from {len(readings)} readings)."
        )
        return successful_timestamps
