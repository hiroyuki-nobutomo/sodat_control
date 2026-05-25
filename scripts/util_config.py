#!/usr/bin/env python3
import argparse
import os
import sys

try:
    import yaml
except ImportError:
    print("Error: The 'yaml' library is missing.", file=sys.stderr)
    print("This usually happens if the virtual environment failed to build due to network issues.", file=sys.stderr)
    print("Please check your internet connection and run the initialization script again.", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))

def load_config(path):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        sys.exit(1)
    with open(path, "r") as f:
        return yaml.safe_load(f)

def save_config(path, config):
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"Configuration saved to {path}")

def update_device_id(config, device_id):
    print(f"Updating Device ID: {config.get('device_id')} -> {device_id}")
    config['device_id'] = device_id

def update_spreadsheet_id(config, spreadsheet_id):
    if 'uploader' not in config:
        config['uploader'] = {}
    current = config['uploader'].get('spreadsheet_id')
    print(f"Updating uploader.spreadsheet_id: {current} -> {spreadsheet_id}")
    config['uploader']['spreadsheet_id'] = spreadsheet_id

def update_folder_id(config, key, value):
    if 'uploader' not in config:
        config['uploader'] = {}
    current = config['uploader'].get(key)
    print(f"Updating uploader.{key}: {current} -> {value}")
    config['uploader'][key] = value

def update_retention(config, days):
    if 'storage' in config and 'retention' in config['storage']:
        print(f"Updating Retention Policy: {days} days")
        config['storage']['retention']['max_age_days'] = days
    else:
        print("Warning: Retention configuration not found in config.yaml")

def update_intervals(config, sensor_int, camera_int, upload_int, upload_offset, log_int):
    # Update Uploader
    if 'uploader' in config:
        if upload_int is not None:
            print(f"Updating Upload Interval: {upload_int}s")
            config['uploader']['interval_seconds'] = upload_int

        if upload_offset is not None:
            print(f"Updating Upload Offset: {upload_offset}s")
            config['uploader']['offset_seconds'] = upload_offset

        if log_int is not None:
            print(f"Updating Log Upload Interval: {log_int}s")
            config['uploader']['log_interval_seconds'] = log_int
    
    # Update Sensors
    if 'sensors' in config:
        for sensor in config['sensors']:
            s_type = sensor.get('type')
            if s_type == "Camera":
                if camera_int is not None:
                    print(f"Updating Camera Interval: {camera_int}s")
                    sensor['interval_seconds'] = camera_int
            else:
                # Assuming all other sensors share the 'sensor_interval'
                if sensor_int is not None:
                    print(f"Updating {s_type} Interval: {sensor_int}s")
                    sensor['interval_seconds'] = sensor_int

def main():
    parser = argparse.ArgumentParser(description="Configure Sensor SFC Device Settings")
    parser.add_argument("--device-id", help="Set the unique Device ID (e.g., S01, A01)")
    parser.add_argument("--spreadsheet-id", help="Set the lab-wide master spreadsheet ID (uploader.spreadsheet_id)")
    parser.add_argument("--data-folder-id", help="Set the Drive folder ID for log/data uploads (uploader.data_folder_id)")
    parser.add_argument("--images-folder-id", help="Set the Drive folder ID for image uploads (uploader.images_folder_id)")
    parser.add_argument("--retention-days", type=int, help="Set local data retention period (days)")
    parser.add_argument("--sensor-interval", type=int, help="Set environmental sensor interval (seconds)")
    parser.add_argument("--camera-interval", type=int, help="Set camera interval (seconds)")
    parser.add_argument("--upload-interval", type=int, help="Set upload interval (seconds)")
    parser.add_argument("--upload-offset", type=int, help="Set upload start offset (seconds)")
    parser.add_argument("--log-interval", type=int, help="Set log upload interval (seconds)")
    parser.add_argument("--config", default=CONFIG_FILE, help=f"Path to config file (default: {CONFIG_FILE})")

    args = parser.parse_args()

    if not any([args.device_id, args.spreadsheet_id, args.data_folder_id, args.images_folder_id,
                args.retention_days, args.sensor_interval, args.camera_interval,
                args.upload_interval, args.upload_offset, args.log_interval]):
        parser.print_help()
        sys.exit(0)

    config = load_config(args.config)

    if args.device_id:
        update_device_id(config, args.device_id)

    if args.spreadsheet_id:
        update_spreadsheet_id(config, args.spreadsheet_id)

    if args.data_folder_id:
        update_folder_id(config, 'data_folder_id', args.data_folder_id)

    if args.images_folder_id:
        update_folder_id(config, 'images_folder_id', args.images_folder_id)

    if args.retention_days:
        update_retention(config, args.retention_days)

    update_intervals(config, args.sensor_interval, args.camera_interval, args.upload_interval, args.upload_offset, args.log_interval)

    save_config(args.config, config)

if __name__ == "__main__":
    main()
