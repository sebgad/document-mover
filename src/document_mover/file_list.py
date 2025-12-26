import logging
from pathlib import Path
import time
import re

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class FileStats:
    """File statistics for tracking file state during processing."""

    def __init__(self, path: Path, initial_size: int, age: float, final_size: int, is_stable: bool):
        """
        Initialize FileStats with file information.

        Args:
            path: Path to the file.
            initial_size: Initial size of the file in bytes.
            age: Age of the file in seconds.
            final_size: Final size of the file in bytes after stability check.
            is_stable: Whether the file is stable (not being written to).
        """
        self.path = path
        self.initial_size = initial_size
        self.age = age
        self.final_size = final_size
        self.is_stable = is_stable
        self.tags: list[str] = []

    def add_tag(self, tag: str) -> None:
        """
        Add a tag to the file.

        Args:
            tag: The tag name to add to the file.
        """
        self.tags.append(tag)

    def has_tag(self, tag: str) -> bool:
        """
        Check if the file has a specific tag.

        Args:
            tag: The tag name to check for. Empty string checks for untagged files.

        Returns:
            True if the file has the tag, False otherwise.
        """
        if tag == "":
            return len(self.tags) == 0

        return tag in self.tags


class FileListHandler:
    """Handles file collection, stability checking, and tagging."""

    def __init__(self, path: Path, include_file_types: list[str]) -> None:
        """
        Initialize FileListHandler.

        Args:
            path: Directory path to scan for files.
            include_file_types: List of file extensions to include (e.g., ['.pdf', '.jpg']).
        """
        self.path = path
        self.include_file_types = include_file_types
        self.files: dict[str, FileStats] = {}
        self.logger = logging.getLogger(__name__)

    def remove_unstable_files(self) -> None:
        """
        Remove all unstable files from the file list.

        Logs the removal of each unstable file.
        """
        unstable_files = [fname for fname, stats in self.files.items() if not stats.is_stable]
        for fname in unstable_files:
            self.logger.info(f"Removing unstable file from list: {fname}")
            del self.files[fname]

    def is_directory_stable(self, stability_wait: int) -> bool:
        """
        Check if the directory is stable (no new files being written).

        Args:
            stability_wait: Time in seconds to wait before checking stability.

        Returns:
            True if directory is stable, False otherwise.
        """
        initial_size = self.path.stat().st_size
        time.sleep(stability_wait)
        final_size = self.path.stat().st_size
        if initial_size == final_size and initial_size > 0:
            if self.file_list_changed():
                self.logger.info("Directory contents changed during stability wait.")
                return False

            self.logger.info("Directory is stable.")
            return True

        return False

    def file_list_changed(self) -> bool:
        """
        Check if the file list in the directory has changed.

        Compares current files with tracked files by name and size.

        Returns:
            True if file list has changed, False otherwise.
        """
        current_files = {
            file.name: file.stat().st_size
            for file in self.path.iterdir()
            if file.is_file() and any(file.name.lower().endswith(ext) for ext in self.include_file_types)
        }

        if len(current_files) != len(self.files):
            return True

        for filename, stats in self.files.items():
            if filename not in current_files or current_files[filename] != stats.final_size:
                return True

        return False

    def parse_files(self, stability_wait: int, only_stable_files: bool) -> None:
        """
        Parse and collect files from the directory.

        Collects file statistics, checks stability, and optionally removes unstable files.

        Args:
            stability_wait: Time in seconds to wait before checking file stability.
            only_stable_files: If True, remove unstable files from the list after parsing.
        """
        self.logger.info(f"Parsing files in directory: {self.path}")

        for file in self.path.iterdir():
            if file.is_file() and any(file.name.lower().endswith(ext) for ext in self.include_file_types):
                self.files[file.name] = FileStats(
                    path=file,
                    initial_size=file.stat().st_size,
                    age=time.time() - file.stat().st_mtime,
                    final_size=0,
                    is_stable=False,
                )

        self.update_file_stats(stability_wait=stability_wait)

        if only_stable_files:
            self.remove_unstable_files()

    def update_file_stats(self, stability_wait: int) -> None:
        """
        Update file statistics by checking final sizes after wait period.

        Waits for the specified time and then checks if file sizes have changed.
        Sets is_stable to True if size remained constant and is greater than 0.

        Args:
            stability_wait: Time in seconds to wait before checking file stability.
        """
        time.sleep(stability_wait)
        for filename, stats in self.files.items():
            filepath = stats.path
            if filepath.exists():
                new_size = filepath.stat().st_size
                stats.final_size = new_size
                stats.is_stable = stats.initial_size == new_size and stats.initial_size > 0
            else:
                stats.is_stable = False

    def has_unstable_files(self) -> bool:
        """
        Check if any files in the list are unstable.

        Returns:
            True if at least one file is unstable, False otherwise.
        """
        return any(not stats.is_stable for stats in self.files.values())

    def add_tag_to_files(self, regex_search_pattern: str, tag_name: str) -> None:
        """
        Add a tag to files matching a regex pattern.

        Files whose names match the regex pattern are tagged with the given tag name.

        Args:
            regex_search_pattern: Regular expression pattern to match against filenames.
            tag_name: The tag name to add to matching files.
        """
        pattern = re.compile(regex_search_pattern)
        for filename, stats in self.files.items():
            if pattern.search(filename):
                self.logger.debug(f"Tagging file {filename} with tag '{tag_name}'")
                stats.add_tag(tag_name)

    def get_files_with_tag(
        self,
        tag_name: str,
        file_types: list[str] | None = None,
        only_stable: bool = True,
        sort_key_regex: str | None = None,
    ) -> list[FileStats]:
        """
        Get all files with a specific tag.

        Args:
            tag_name: The tag name to filter by. Use empty string for untagged files.
            file_types: Optional list of file extensions to further filter by.
            only_stable: If True, only return stable files. Defaults to True.
            sort_key_regex: Regular expression pattern to sort the files by.

        Returns:
            List of FileStats objects matching the criteria.
        """
        file_list = [stats for stats in self.files.values() if stats.has_tag(tag_name)]

        if only_stable:
            file_list = [stats for stats in file_list if stats.is_stable]

        if file_types:
            file_list = [
                stats for stats in file_list if any(stats.path.name.lower().endswith(ext) for ext in file_types)
            ]

        if sort_key_regex is not None:
            pattern = re.compile(sort_key_regex)

            def get_sort_key(stats: FileStats) -> str:
                match = pattern.search(stats.path.name)
                if match:
                    return match.group()
                return ""

            file_list.sort(key=get_sort_key)

        return file_list

    def get_number_of_files(self) -> int:
        """
        Get the total number of files in the list.

        Returns:
            Number of files currently tracked.
        """
        return len(self.files)

    def get_untagged_files(
        self, only_stable: bool = True, file_types: list[str] | None = None, sort_key_regex: str | None = None
    ) -> list[FileStats]:
        """
        Get all untagged files.

        Args:
            only_stable: If True, only return stable files. Defaults to True.
            file_types: Optional list of file extensions to further filter by.
            sort_key_regex: Regular expression pattern to sort the files by.

        Returns:
            List of untagged FileStats objects matching the criteria.
        """
        return self.get_files_with_tag(
            tag_name="", file_types=file_types, only_stable=only_stable, sort_key_regex=sort_key_regex
        )
