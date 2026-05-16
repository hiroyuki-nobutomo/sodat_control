import sqlite3
import json
import logging
import os
from typing import List
from src.models import SensorReading

class StorageManager:
    def __init__(self, db_path: str = "sensor_data.db"):
        self.db_path = db_path
        
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        self._init_db()

    def _init_db(self):
        """Creates the database table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sensor_id TEXT NOT NULL,
                        sensor_type TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                """)
                # Index for faster retrieval and deletion
                conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)")
            logging.info(f"Storage initialized at {self.db_path}")
        except sqlite3.Error as e:
            logging.error(f"Failed to initialize database: {e}")
            raise

    def add_reading(self, reading: SensorReading):
        """Stores a new sensor reading in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO readings (sensor_id, sensor_type, value_json, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        reading.sensor_id,
                        reading.sensor_type,
                        json.dumps(reading.value),
                        reading.timestamp.isoformat()
                    )
                )
        except sqlite3.Error as e:
            logging.error(f"Failed to add reading to storage: {e}")
            raise

    def get_pending_readings(self, limit: int = 100) -> List[SensorReading]:
        """Retrieves a list of readings that haven't been uploaded yet."""
        readings = []
        corrupted_ids = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # Select ID specifically to handle corruption deletion
                cursor = conn.execute(
                    "SELECT id, sensor_id, sensor_type, value_json, timestamp FROM readings ORDER BY timestamp ASC LIMIT ?",
                    (limit,)
                )
                for row in cursor:
                    try:
                        readings.append(SensorReading.from_dict({
                            "sensor_id": row["sensor_id"],
                            "sensor_type": row["sensor_type"],
                            "value": json.loads(row["value_json"]),
                            "timestamp": row["timestamp"]
                        }))
                    except (json.JSONDecodeError, ValueError, TypeError) as e:
                        logging.error(f"Corrupted reading found (ID: {row['id']}). Deleting. Error: {e}")
                        corrupted_ids.append(row['id'])
                
                # Clean up corrupted rows immediately
                if corrupted_ids:
                    placeholders = ",".join(["?"] * len(corrupted_ids))
                    conn.execute(f"DELETE FROM readings WHERE id IN ({placeholders})", corrupted_ids)
                    conn.commit() # Ensure deletion persists
                    
            return readings
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve pending readings: {e}")
            return []

    def remove_readings(self, timestamps: List[str]):
        """Removes readings from storage after successful upload.

        Processes in batches of 500 to stay well within SQLite's
        SQLITE_MAX_VARIABLE_NUMBER limit (default 999, some builds 32766).
        """
        if not timestamps:
            return
        batch_size = 500
        try:
            with sqlite3.connect(self.db_path) as conn:
                for i in range(0, len(timestamps), batch_size):
                    batch = timestamps[i:i + batch_size]
                    placeholders = ",".join(["?"] * len(batch))
                    conn.execute(
                        f"DELETE FROM readings WHERE timestamp IN ({placeholders})",
                        batch)
        except sqlite3.Error as e:
            logging.error(f"Failed to remove readings from storage: {e}")
            raise

    def clear_all(self):
        """Clears all data from the database (for testing)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM readings")
        except sqlite3.Error as e:
            logging.error(f"Failed to clear storage: {e}")
            raise
