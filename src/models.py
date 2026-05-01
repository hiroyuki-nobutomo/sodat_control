from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict

@dataclass
class SensorReading:
    sensor_id: str
    sensor_type: str
    value: Dict[str, Any]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Converts the model instance to a dictionary, formatting the timestamp as ISO 8601."""
        data = asdict(self)
        if isinstance(self.timestamp, datetime):
            data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SensorReading':
        """Creates a model instance from a dictionary, parsing the ISO 8601 timestamp."""
        timestamp = data["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        
        return cls(
            sensor_id=data["sensor_id"],
            sensor_type=data["sensor_type"],
            value=data["value"],
            timestamp=timestamp
        )
