#!/usr/bin/env python3

import time
import os
import re
import shutil
from .file_list import FileStats, FileListHandler
import argparse
from pathlib import Path
import logging

from document_mover.pdf_merger import PDFMerger
from .file_lock import FileLock


# Default Configuration
DEFAULT_SINGLE_DUAL_SIDE_PREFIX = "single-double-sided"
DEFAULT_DUAL_SIDE_STABILITY_WAIT = 30  # seconds
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
        dual_side_prefix: str | None,
        single_dual_side_prefix: str | None,
        user_id: int,
        group_id: int,
        stability_wait: int,
        stability_wait_single_dual_side: int,
        max_age: int,
        file_types: list,
        dry_run: bool = False,
    ):
        """
        Initialize the file processor.

        Args:
            source_dir: Source directory containing scanned files
            dest_dir: Default destination directory for processed files
            dual_side_prefix: Prefix or regex pattern for identifying dual-sided files
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
        self.stability_wait_single_dual_side = stability_wait_single_dual_side
        self.single_dual_side_prefix_pattern = single_dual_side_prefix
        self.dual_side_prefix_pattern = dual_side_prefix
        self.user_id = user_id
        self.group_id = group_id
        self.stability_wait = stability_wait
        self.max_age_seconds = max_age * 60
        self.file_types = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in file_types]
        self.dry_run = dry_run
        self.file_list = FileListHandler(self.source_dir, self.file_types)

    def move_file(self, file_stat: FileStats) -> bool:
        """
        Move a single file: move and set permissions.

        Args:
            filepath: Path to the file to process

        Returns:
            True if file was processed successfully, False otherwise
        """
        filename = file_stat.path.name

        try:
            # Check if file still exists
            if not file_stat.path.exists():
                self.logger.debug(f"File no longer exists: {filename}")
                return False

            # Determine destination path
            dest_path = self.dest_dir / filename

            # Check if destination already exists
            if dest_path.exists():
                self.logger.warning(f"Destination file already exists, skipping: {filename}")
                # Remove source file if it's identical
                if not self.dry_run:
                    try:
                        file_stat.path.unlink()
                        self.logger.info(f"Removed duplicate source file: {filename}")
                    except Exception:
                        pass
                return False

            if self.dry_run:
                self.logger.info(f"[DRY-RUN] Would move file: {file_stat.path} -> {dest_path}")
                self.logger.info(
                    f"[DRY-RUN] Would set ownership to {self.user_id}:{self.group_id} and permissions to 0660"
                )
                return True

            shutil.move(str(file_stat.path), str(dest_path))

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

    def merge_pdf_files(
        self, pdf1: Path, pdf2: Path, output_path: Path, delete_source: bool = False, remove_empty_pages: bool = False
    ) -> bool:
        """
        Merge two PDF files into one.

        Args:
            pdf1: Path to the first PDF file
            pdf2: Path to the second PDF file
            output_path: Path to save the merged PDF file
            delete_source: If True, delete source files after merging
            remove_empty_pages: If True, remove empty pages from the merged PDF

        Returns:
            True if merge was successful, False otherwise
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would merge: {pdf1.name} + {pdf2.name} -> {output_path.name}")

            if delete_source:
                self.logger.info(f"[DRY-RUN] Would delete source files: {pdf1.name}, {pdf2.name}")
            return True

        try:
            pdf_merger = PDFMerger()
            merge_success = pdf_merger.merge(
                pdf1=pdf1,
                pdf2=pdf2,
                output_path=output_path,
                delete_source=delete_source,
                remove_empty_pages=remove_empty_pages,
            )

            if not merge_success:
                self.logger.error(f"Failed to merge PDF files: {pdf1} + {pdf2}")
                return False

            time.sleep(1)

            # Set ownership and permissions for merged file
            os.chown(output_path, self.user_id, self.group_id)
            os.chmod(output_path, 0o660)

            self.logger.info(f"Successfully merged dual-side files into: {output_path}")

        except Exception as e:
            self.logger.error(f"Error merging PDF files {pdf1} + {pdf2}: {e}")
            return False

        return True

    def handle_dual_side_files(
        self, files: list[FileStats], consecutive_pairwise: bool = False, outside_pairing: bool = False
    ) -> int:
        """
        Handle merging of dual-sided PDF files.

        Collects stable dual-sided files, pairs them by consecutive numbering,
        and merges each pair into a single PDF file.

        Returns:
            int: Number of successfully merged file pairs
        """
        # Consistency check for pairwise parameters
        if consecutive_pairwise and outside_pairing:
            self.logger.error("Cannot have both consecutive_pairwise and outside_pairing set to True.")
            return 0

        success_count = 0
        if len(files) % 2 != 0:
            self.logger.error(f"Odd number of dual-side files detected ({len(files)}), cannot perform merge")
            return success_count

        if consecutive_pairwise:
            file_range = [(i, i + 1) for i in range(0, len(files) - 1, 2)]
        elif outside_pairing:
            file_range = [(i, len(files) - 1 - i) for i in range(len(files) // 2)]
        else:
            self.logger.error("Either consecutive_pairwise or outside_pairing must be True.")
            return success_count

        for i, j in file_range:
            # Process file1 and file2 as a pair
            file1 = files[i]
            file2 = files[j]

            file1_match = re.search(r"\d+", file1.path.name)
            file2_match = re.search(r"\d+", file2.path.name)

            if not file1_match or not file2_match:
                self.logger.warning(f"Could not extract numbers from {file1.path.name} or {file2.path.name}")
                continue

            file1_number = int(file1_match.group(0))
            file2_number = int(file2_match.group(0))

            if file1_number < file2_number:
                # Merge PDF of file1 and file2
                merged_filename = f"dual-side_{file1_number}_{file2_number}_merged.pdf"
                merged_filepath = self.dest_dir / merged_filename

                if self.dry_run:
                    self.logger.info(
                        f"[DRY-RUN] Would merge dual-side files: {file1.path.name} + {file2.path.name} -> {merged_filename}"
                    )
                    success_count += 1
                    continue
                else:
                    if self.merge_pdf_files(
                        pdf1=file1.path,
                        pdf2=file2.path,
                        output_path=merged_filepath,
                        delete_source=True,
                        remove_empty_pages=True,
                    ):
                        success_count += 1

        return success_count

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

        self.file_list.parse_files(self.stability_wait, only_stable_files=False)

        if not self.file_list.get_number_of_files():
            self.logger.info("No files to process")
            return 0

        self.logger.info(f"Found {self.file_list.get_number_of_files()} file(s) to process")

        # Check if prefix given for dual-side files
        if self.dual_side_prefix_pattern is not None:
            self.file_list.add_tag_to_files(self.dual_side_prefix_pattern, "dual-side")

        if self.single_dual_side_prefix_pattern is not None:
            self.file_list.add_tag_to_files(self.single_dual_side_prefix_pattern, "single-dual-side")

        success_count = 0

        # handle files with no tag first -> normal files
        for file in self.file_list.get_untagged_files():
            if self.move_file(file):
                success_count += 1

        if self.file_list.is_directory_stable(self.stability_wait_single_dual_side):
            self.logger.info("Source directory is stable for single dual-side files.")

            file_list_single_dual = self.file_list.get_files_with_tag("single-dual-side", file_types=[".pdf"])
            file_list_dual = self.file_list.get_files_with_tag("dual-side", file_types=[".pdf"])

            if file_list_single_dual:
                self.logger.info(
                    f"Processing {len(file_list_single_dual)} single dual-side tagged file(s) for pairing and merging."
                )
                success_count += self.handle_dual_side_files(files=file_list_single_dual, outside_pairing=True)

            if file_list_dual:
                self.logger.info(
                    f"Processing {len(file_list_dual)} dual-side tagged file(s) for consecutive pairing and merging."
                )
                success_count += self.handle_dual_side_files(files=file_list_dual, consecutive_pairwise=True)
        else:
            self.logger.info("Source directory is not stable for single dual-side files, skipping processing.")
            return success_count

        return success_count


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
        help="Regex pattern for identifying dual-sided files (default: 'double-sided')",
    )

    parser.add_argument(
        "--single-dual-side-prefix",
        default=DEFAULT_SINGLE_DUAL_SIDE_PREFIX,
        help="Regex pattern for identifying single-dual-sided files (default: 'single-double-sided')",
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
        "--dual-side-stability-wait",
        type=int,
        default=DEFAULT_DUAL_SIDE_STABILITY_WAIT,
        help="Wait time in seconds to check dual-side file stability",
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
        single_dual_side_prefix=args.single_dual_side_prefix,
        stability_wait_single_dual_side=args.dual_side_stability_wait,
        max_age=args.max_age,
        user_id=args.user_id,
        group_id=args.group_id,
        stability_wait=args.stability_wait,
        file_types=args.file_types,
        dry_run=args.dry_run,
    )

    # Run the processor
    processed_files = processor.run()

    logging.getLogger().info(f"Total files processed successfully: {processed_files}")


if __name__ == "__main__":
    args = parse_arguments()

    # Use file lock to prevent multiple instances from running
    with FileLock(args.lock_file):
        main()
