#!/usr/bin/env python3

import os
import re
import time
import shutil
from typing import TypedDict

import argparse
from pathlib import Path
import logging

from document_mover.pdf_merger import PDFMerger
from .file_lock import FileLock


class FileStats(TypedDict):
    path: Path
    initial_size: int
    age: float
    final_size: int
    is_stable: bool


# Default Configuration
DEFAULT_DUAL_SIDE_PREFIX = "double-sided"
DEFAULT_STABILITY_WAIT = 10  # seconds
DEFAULT_MAX_AGE = 10  # minutes
DEFAULT_LOCK_FILE = "/var/run/move-pdfs.lock"
DEFAULT_USER_ID = os.getuid()  # Current user ID
DEFAULT_GROUP_ID = os.getgid()  # Current group ID
DEFAULT_FILE_TYPES = [
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".tif",
]  # file extensions to process

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class ScanFileProcessor:
    """Handles processing of scanned files with stability checks and atomic moves."""

    def __init__(
        self,
        source_dir: str,
        dest_dir: str,
        dual_side_prefix: str,
        user_id: int,
        group_id: int,
        stability_wait: int,
        max_age: int,
        file_types: list,
        dry_run: bool = False,
    ):
        """
        Initialize the file processor.

        Args:
            source_dir: Source directory containing scanned files
            dest_dir: Default destination directory for processed files
            dual_side_prefix: Prefix for identifying dual-sided files
            user_id: User ID for file ownership
            group_id: Group ID for file ownership
            stability_wait: Wait time in seconds to check file stability
            max_age: Maximum file age in minutes before forcing move
            file_types: List of file extensions to process
            dry_run: If True, perform dry run without moving files
        """

        self.logger = logging.getLogger(__name__)
        self.source_dir = Path(source_dir)
        self.dest_dir = Path(dest_dir)
        self.dual_side_prefix = dual_side_prefix
        self.user_id = user_id
        self.group_id = group_id
        self.stability_wait = stability_wait
        self.max_age_seconds = max_age * 60
        self.file_types = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in file_types]
        self.dry_run = dry_run
        self.file_stats: dict[str, FileStats] = {}  # Dictionary to store file statistics

    @staticmethod
    def get_file_age(filepath: Path) -> float:
        """Get file age in seconds."""
        try:
            return time.time() - filepath.stat().st_mtime
        except FileNotFoundError:
            return 0

    def collect_file_stats(self, files: list[Path]) -> None:
        """
        Collect initial statistics for all files.

        Args:
            files: List of file paths to collect stats for
        """
        self.logger.info(f"Collecting initial file statistics for {len(files)} file(s)...")
        for filepath in files:
            if filepath.exists():
                self.file_stats[filepath.name] = {
                    "path": filepath,
                    "initial_size": filepath.stat().st_size,
                    "age": self.get_file_age(filepath),
                    "final_size": 0,
                    "is_stable": False,
                }

    def check_file_stability(self) -> None:
        """
        Check stability for all files by comparing sizes after wait time.
        """
        self.logger.info(f"Waiting {self.stability_wait} seconds to check file stability...")
        time.sleep(self.stability_wait)

        for filename, stats in self.file_stats.items():
            filepath = stats["path"]
            if filepath.exists():
                new_size = filepath.stat().st_size
                stats["final_size"] = new_size
                stats["is_stable"] = stats["initial_size"] == new_size and stats["initial_size"] > 0
                if not stats["is_stable"]:
                    self.logger.debug(
                        f"File unstable: {filename} (size changed: {stats['initial_size']} -> {new_size})"
                    )
            else:
                stats["is_stable"] = False
                self.logger.debug(f"File disappeared: {filename}")

    def move_file(self, file_stat: FileStats) -> bool:
        """
        Move a single file: move and set permissions.

        Args:
            filepath: Path to the file to process

        Returns:
            True if file was processed successfully, False otherwise
        """
        filename = file_stat["path"].name

        try:
            # Check if file still exists
            if not file_stat["path"].exists():
                self.logger.debug(f"File no longer exists: {filename}")
                return False

            # Get stats from dictionary
            stats = self.file_stats.get(filename)
            assert stats is not None, "File stats should have been collected"

            file_age = file_stat["age"]

            # Check if file is too old (might be stuck)
            if file_age > self.max_age_seconds:
                self.logger.warning(f"File {filename} is older than {self.max_age_seconds / 60} minutes, moving anyway")

            elif not file_stat.get("is_stable", False):
                self.logger.info(f"Skipping unstable file: {filename}")
                return False

            # Double-check file still exists before moving
            if not file_stat["path"].exists():
                self.logger.debug(f"File disappeared before move: {filename}")
                return False

            # Determine destination path
            dest_path = self.dest_dir / filename

            # Check if destination already exists
            if dest_path.exists():
                self.logger.warning(f"Destination file already exists, skipping: {filename}")
                # Remove source file if it's identical
                if not self.dry_run:
                    try:
                        file_stat["path"].unlink()
                        self.logger.info(f"Removed duplicate source file: {filename}")
                    except Exception:
                        pass
                return False

            if self.dry_run:
                self.logger.info(f"[DRY-RUN] Would move file: {file_stat['path']} -> {dest_path}")
                self.logger.info(
                    f"[DRY-RUN] Would set ownership to {self.user_id}:{self.group_id} and permissions to 0660"
                )
                return True

            shutil.move(str(file_stat["path"]), str(dest_path))

            # Change ownership and permissions
            os.chown(dest_path, self.user_id, self.group_id)
            os.chmod(dest_path, 0o660)

            self.logger.info(f"Successfully processed file: {filename} -> {self.dest_dir}")
            return True

        except FileNotFoundError:
            self.logger.debug(f"File disappeared during processing: {filename}")
            return False
        except PermissionError as e:
            self.logger.error(f"Permission error processing file {filename}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error processing file {filename}: {e}")
            return False

    def get_files_to_process(self) -> list[Path]:
        """Get list of files matching the specified file types."""
        return [f for f in self.source_dir.iterdir() if f.is_file() and f.suffix.lower() in self.file_types]

    def run(self) -> int:
        """
        Process all files in the source directory using single-threaded approach.

        Returns:
            int: Number of successfully processed files
        """
        # Verify directories exist
        if not self.source_dir.exists():
            self.logger.error(f"Source directory does not exist: {self.source_dir}")
            return 0

        if not self.dest_dir.exists():
            self.logger.error(f"Destination directory does not exist: {self.dest_dir}")
            return 0

        if self.dry_run:
            self.logger.info("DRY-RUN MODE: No files will be moved")

        self.logger.info(f"Processing file types: {', '.join(self.file_types)}")
        self.logger.info(f"Default destination: {self.dest_dir}")

        # Get all files to process
        files = self.get_files_to_process()

        if not files:
            self.logger.info("No files to process")
            return 0

        self.logger.info(f"Found {len(files)} file(s) to process")

        # Collect initial statistics for all files
        self.collect_file_stats(files)
        self.check_file_stability()

        success_count = 0
        dual_side_files: list[FileStats] = []

        for filestat in self.file_stats.values():
            if filestat["is_stable"]:
                filepath = filestat["path"]
                is_dual_side = filepath.name.startswith(self.dual_side_prefix)

                if not is_dual_side and self.move_file(filestat):
                    success_count += 1

                elif is_dual_side:
                    # if dual-side, only pdf files are supported for merging
                    if filepath.suffix.lower() == ".pdf":
                        dual_side_files.append(filestat)

        # sort dual-side files by name to ensure correct processing order
        dual_side_files.sort(key=lambda x: x["path"].name)

        if len(dual_side_files) <= 1:
            self.logger.info(
                f"Only one or less dual-side file found ({dual_side_files[0]['path'].name}), cannot perform merge"
            )
            return success_count

        # find files with consecutive numbering
        for i in range(0, len(dual_side_files) - 1, 2):
            # Process file1 and file2 as a pair
            file1 = dual_side_files[i]
            file2 = dual_side_files[i + 1]

            file1_number = re.findall(r"\d+", file1["path"].name)[0]
            file2_number = re.findall(r"\d+", file2["path"].name)[0]

            if int(file1_number) < int(file2_number):
                # Merge PDF of file1 and file2
                merged_filename = f"{self.dual_side_prefix}_{file1_number}_{file2_number}_merged.pdf"
                merged_filepath = self.dest_dir / merged_filename

                if self.dry_run:
                    self.logger.info(
                        f"[DRY-RUN] Would merge dual-side files: {file1['path'].name} + {file2['path'].name} -> {merged_filename}"
                    )
                    success_count += 1
                    continue
                else:
                    try:
                        pdf_merger = PDFMerger()
                        merge_success = pdf_merger.merge(
                            pdf1=file1["path"],
                            pdf2=file2["path"],
                            output_path=merged_filepath,
                            delete_source=True,
                            remove_empty_pages=True,
                        )

                        if merge_success:
                            max_retries = 5
                            retries = 0
                            while not is_file_stable(merged_filepath, self.stability_wait) and retries < max_retries:
                                time.sleep(1)
                                retries += 1

                            if retries == max_retries:
                                self.logger.error(f"Merged file is not stable after retries: {merged_filename}")
                                continue

                            # Set ownership and permissions for merged file
                            os.chown(merged_filepath, self.user_id, self.group_id)
                            os.chmod(merged_filepath, 0o660)

                            self.logger.info(f"Successfully merged dual-side files into: {merged_filename}")
                            success_count += 1
                        else:
                            self.logger.error(
                                f"Failed to merge dual-side files: {file1['path'].name} + {file2['path'].name}"
                            )

                    except Exception as e:
                        self.logger.error(
                            f"Error merging dual-side files {file1['path'].name} + {file2['path'].name}: {e}"
                        )

        return success_count


def is_file_stable(filepath: Path, stability_wait_seconds: int) -> bool:
    """Check if file is stable (not being written to)."""
    try:
        size1 = filepath.stat().st_size
        time.sleep(stability_wait_seconds)
        size2 = filepath.stat().st_size
        return size1 == size2
    except FileNotFoundError:
        return False


def get_file_age(filepath: Path) -> float:
    """Get file age in seconds."""
    try:
        return time.time() - filepath.stat().st_mtime
    except FileNotFoundError:
        return 0


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Move scanned files from source to destination directory with stability checks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--source-dir",
        required=True,
        help="Source directory containing scanned files",
    )

    parser.add_argument(
        "--dest-dir",
        required=True,
        help="Default destination directory for processed files",
    )

    parser.add_argument(
        "--dual-side-prefix",
        default=DEFAULT_DUAL_SIDE_PREFIX,
        help="Prefix for identifying dual-sided files",
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=DEFAULT_USER_ID,
        help="User ID for file ownership",
    )

    parser.add_argument(
        "--group-id",
        type=int,
        default=DEFAULT_GROUP_ID,
        help="Group ID for file ownership",
    )

    parser.add_argument(
        "--stability-wait",
        type=int,
        default=DEFAULT_STABILITY_WAIT,
        help="Wait time in seconds to check file stability",
    )

    parser.add_argument(
        "--max-age",
        type=int,
        default=DEFAULT_MAX_AGE,
        help="Maximum file age in minutes before forcing move",
    )

    parser.add_argument(
        "--lock-file",
        default=DEFAULT_LOCK_FILE,
        help="Lock file path to prevent concurrent execution",
    )

    parser.add_argument(
        "--file-types",
        nargs="+",
        default=DEFAULT_FILE_TYPES,
        help="File extensions to process (e.g., .pdf .jpg .png)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually moving files",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose (debug) logging")

    return parser.parse_args()


def main():
    """Main function to process all files in source directory."""
    args = parse_arguments()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create processor instance
    processor = ScanFileProcessor(
        source_dir=args.source_dir,
        dest_dir=args.dest_dir,
        dual_side_prefix=args.dual_side_prefix,
        max_age=args.max_age,
        user_id=args.user_id,
        group_id=args.group_id,
        stability_wait=args.stability_wait,
        file_types=args.file_types,
        dry_run=args.dry_run,
    )

    # Run the processor
    processor.run()


if __name__ == "__main__":
    args = parse_arguments()

    # Use file lock to prevent multiple instances from running
    with FileLock(args.lock_file):
        main()
