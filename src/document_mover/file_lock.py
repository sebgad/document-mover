import fcntl
import os
import sys
import logging
from pathlib import Path

class FileLock:
    """Context manager for file-based locking to prevent concurrent execution."""
    
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.lock_fd = None
        self.logger = logging.getLogger(__name__)
    
    def __enter__(self):
        try:
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            self.logger.info(f"Acquired lock: {self.lock_file}")
            return self
        except IOError:
            self.logger.warning("Another instance is already running, exiting")
            sys.exit(0)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_fd:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
            self.lock_fd.close()
            try:
                os.remove(self.lock_file)
            except OSError:
                pass
            self.logger.info(f"Released lock: {self.lock_file}")