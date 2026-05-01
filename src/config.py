import os
import yaml
import logging
from typing import Any, List, Optional

class ConfigManager:
    def __init__(self, config_path: Optional[str] = None, search_paths: Optional[List[str]] = None):
        """
        Initializes the ConfigManager.
        
        Args:
            config_path: A specific config file to load (deprecated, use search_paths).
            search_paths: A list of paths to search for config files. The first one found is loaded.
        """
        if search_paths:
            self.search_paths = search_paths
        else:
            # Priority: Local config (Dev/Manual) -> Boot partition (Golden Image fallback)
            self.search_paths = [
                "config.yaml",
                "/boot/firmware/sensor_config.yaml"
            ]
            if config_path:
                self.search_paths.insert(0, config_path)

        self.config_file = None
        self.config = self._load_config()

    def _load_config(self) -> dict:
        for path in self.search_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        config = yaml.safe_load(f) or {}
                        self.config_file = path
                        logging.info(f"Loaded configuration from: {path}")
                        return config
                except Exception as e:
                    logging.error(f"Error loading config from {path}: {e}")
        
        logging.warning("No configuration file found. Using defaults.")
        return {}

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value. Supports dot notation for nested keys.
        Checks for environment variable overrides first.
        Env var format: SENSOR_SFC_SECTION_KEY (e.g., SENSOR_SFC_SENSOR_INTERVAL_SECONDS)
        """
        # Check environment variable override
        # Convert "sensor.interval_seconds" to "SENSOR_SFC_SENSOR_INTERVAL_SECONDS"
        env_key = "SENSOR_SFC_" + key_path.replace(".", "_").upper()
        env_value = os.environ.get(env_key)
        
        if env_value is not None:
            # Simple type inference for env vars
            if env_value.isdigit():
                return int(env_value)
            if env_value.lower() in ("true", "yes"):
                return True
            if env_value.lower() in ("false", "no"):
                return False
            return env_value

        # Navigate nested dict
        keys = key_path.split(".")
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value