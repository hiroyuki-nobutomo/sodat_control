import os
import time
import logging
from typing import List, Union

class RetentionManager:
    def __init__(self, target_dirs: Union[str, List[str]], max_age_days: int):
        """
        Args:
            target_dirs: Single directory path or list of directory paths to clean.
            max_age_days: Files older than this will be deleted.
        """
        if isinstance(target_dirs, str):
            self.target_dirs = [target_dirs]
        else:
            self.target_dirs = target_dirs
            
        self.max_age_days = max_age_days
        
        for d in self.target_dirs:
            if not os.path.exists(d):
                logging.warning(f"RetentionManager: Directory {d} does not exist (yet).")

    def cleanup(self) -> int:
        """
        Scans target directories and deletes files older than max_age_days.
        Returns the number of files deleted.
        """
        deleted_count = 0
        now = time.time()
        max_age_seconds = self.max_age_days * 86400
        
        logging.info(f"Starting retention cleanup. Max age: {self.max_age_days} days.")

        for target_dir in self.target_dirs:
            if not os.path.exists(target_dir):
                continue
                
            for root, dirs, files in os.walk(target_dir):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    try:
                        file_mtime = os.path.getmtime(filepath)
                        file_age = now - file_mtime
                        
                        if file_age > max_age_seconds:
                            os.remove(filepath)
                            deleted_count += 1
                            logging.info(f"Deleted expired file: {filepath} (Age: {file_age/86400:.1f} days)")
                            
                    except OSError as e:
                        logging.error(f"Error accessing/deleting {filepath}: {e}")

        if deleted_count > 0:
            logging.info(f"Retention cleanup complete. Removed {deleted_count} files.")
        else:
            logging.debug("Retention cleanup complete. No files removed.")
            
        return deleted_count