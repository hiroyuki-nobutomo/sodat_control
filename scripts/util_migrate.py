#!/usr/bin/env python3
import os
import sys
try:
    import yaml
except ImportError:
    print("Error: The 'yaml' library is missing.", file=sys.stderr)
    print("This usually happens if the virtual environment failed to build due to network issues.", file=sys.stderr)
    print("Please check your internet connection and run the initialization script again.", file=sys.stderr)
    sys.exit(1)
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_CONFIG = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))
TEMPLATE_CONFIG = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml.template"))

def load_yaml(path: str) -> dict:
    """
    Loads a YAML file from the given path.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"\n\033[0;31mCRITICAL ERROR: Your {os.path.basename(path)} contains formatting errors.\033[0m")
        print(f"Details: {e}")
        print("Please open the file in a text editor, fix the syntax (e.g., check for missing quotes or incorrect indentation), and run the script again.")
        sys.exit(1)

def save_yaml(path: str, data: dict):
    """
    Saves a dictionary to a YAML file.
    """
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def migrate():
    """
    Main migration logic to intelligently merge config templates.
    """
    print("--- Running Configuration Migration ---")
    
    if not os.path.exists(TARGET_CONFIG):
        print(f"No existing config found at {TARGET_CONFIG}.")
        if os.path.exists(TEMPLATE_CONFIG):
            print("Copying template as new config.")
            shutil.copy(TEMPLATE_CONFIG, TARGET_CONFIG)
        return

    if not os.path.exists(TEMPLATE_CONFIG):
        print(f"Warning: Template config not found at {TEMPLATE_CONFIG}. Skipping migration.")
        return

    # Backup existing config
    backup_path = f"{TARGET_CONFIG}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(TARGET_CONFIG, backup_path)
    print(f"Backed up existing config to: {backup_path}")

    # 1. Update Safe Values using PyYAML
    current = load_yaml(TARGET_CONFIG)
    template = load_yaml(TEMPLATE_CONFIG)
    updated_safe_values = False

    # Interactive Retention Upgrade
    if 'storage' in current and 'retention' in current['storage']:
        current_retention = current['storage']['retention'].get('max_age_days')
        if current_retention is not None and current_retention != 90:
            print("\n[Configuration Update]")
            print(f"Your current local data retention is set to {current_retention} days.")
            print("We strongly recommend increasing this to 90 days. "
                  "This preserves more historical")
            print("data locally, giving us a much better chance of "
                  "resolving issues if the device")
            print("goes offline for an extended period.")
            
            while True:
                try:
                    prompt_text = f"Enter new retention period in days (recommended: 90) or 'n' to keep current [{current_retention}]: "
                    user_input = input(prompt_text).strip()
                    
                    if user_input.lower() in ['n', 'no']:
                        print("ℹ️ Keeping current retention setting.")
                        break
                    
                    new_retention = int(user_input) if user_input else 90
                    
                    if new_retention <= 0:
                        print("⚠️ Please enter a positive number of days.")
                        continue
                        
                    if new_retention != current_retention:
                        current['storage']['retention']['max_age_days'] = new_retention
                        print(f"✅ Updated retention max_age_days to {new_retention}.")
                        updated_safe_values = True
                    else:
                        print("ℹ️ Keeping current retention setting.")
                    break
                    
                except ValueError:
                    print("⚠️ Invalid input. Please enter a valid number or 'n'.")
                except (EOFError, KeyboardInterrupt):
                    print("\nℹ️ Skipping retention update.")
                    break
            
            print("💡 Tip: You can change this later by running: ./05_configure.sh")
             
    # Ensure uploader offset exists
    if 'uploader' in template and 'offset_seconds' in template['uploader']:
        if 'uploader' not in current:
            current['uploader'] = {}
        if 'offset_seconds' not in current['uploader']:
            current['uploader']['offset_seconds'] = template['uploader']['offset_seconds']
            print("Added missing uploader.offset_seconds.")
            updated_safe_values = True

    # Ensure log_interval_seconds exists
    if 'uploader' in template and 'log_interval_seconds' in template['uploader']:
        if 'uploader' not in current:
            current['uploader'] = {}
        if 'log_interval_seconds' not in current['uploader']:
            current['uploader']['log_interval_seconds'] = template['uploader']['log_interval_seconds']
            print("Added missing uploader.log_interval_seconds.")
            updated_safe_values = True

    if updated_safe_values:
        save_yaml(TARGET_CONFIG, current)
        print("Safely updated structural configurations.")

    print("--- Migration complete ---")

if __name__ == "__main__":
    migrate()
