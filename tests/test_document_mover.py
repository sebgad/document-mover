#!/usr/bin/env python3
"""Tests for document_mover functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pypdf import PdfWriter

from document_mover.document_mover import ScanFileProcessor, FileStats


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def source_dir(temp_dir):
    """Create a source directory."""
    source = temp_dir / "source"
    source.mkdir()
    return source


@pytest.fixture
def dest_dir(temp_dir):
    """Create a destination directory."""
    dest = temp_dir / "dest"
    dest.mkdir()
    return dest


@pytest.fixture
def sample_pdf_file(source_dir):
    """Create a sample PDF file."""
    pdf_path = source_dir / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


@pytest.fixture
def sample_jpg_file(source_dir):
    """Create a sample JPG file."""
    jpg_path = source_dir / "sample.jpg"
    jpg_path.write_bytes(b"fake jpg content")
    return jpg_path


@pytest.fixture
def dual_sided_pdfs(source_dir):
    """Create dual-sided PDF files."""
    files = []
    for i in range(1, 5):
        pdf_path = source_dir / f"double-sided_{i}.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(pdf_path, "wb") as f:
            writer.write(f)
        files.append(pdf_path)
    return files


@pytest.fixture
def processor(source_dir, dest_dir):
    """Create a ScanFileProcessor instance."""
    return ScanFileProcessor(
        source_dir=str(source_dir),
        dest_dir=str(dest_dir),
        dual_side_prefix="double-sided",
        user_id=os.getuid(),
        group_id=os.getgid(),
        stability_wait=0,  # No wait for tests
        max_age=10,
        file_types=[".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"],
        dry_run=False,
    )


class TestScanFileProcessor:
    """Test cases for ScanFileProcessor class."""

    def test_processor_initialization(self, source_dir, dest_dir):
        """Test processor initialization."""
        processor = ScanFileProcessor(
            source_dir=str(source_dir),
            dest_dir=str(dest_dir),
            dual_side_prefix="double-sided",
            user_id=1000,
            group_id=1000,
            stability_wait=5,
            max_age=30,
            file_types=[".pdf"],
        )

        assert processor.source_dir == source_dir
        assert processor.dest_dir == dest_dir
        assert processor.dual_side_prefix == "double-sided"
        assert processor.stability_wait == 5
        assert processor.max_age_seconds == 1800  # 30 * 60

    def test_get_files_to_process(self, sample_pdf_file, sample_jpg_file, processor):
        """Test getting files to process."""
        files = processor.get_files_to_process()

        assert len(files) >= 2
        assert sample_pdf_file in files
        assert sample_jpg_file in files

    def test_get_files_to_process_filters_extensions(self, sample_pdf_file, source_dir, processor):
        """Test that only specified file types are returned."""
        # Create a file with unsupported extension
        txt_file = source_dir / "test.txt"
        txt_file.write_text("not a pdf")

        files = processor.get_files_to_process()

        assert txt_file not in files
        assert sample_pdf_file in files

    def test_collect_file_stats(self, sample_pdf_file, processor):
        """Test collecting file statistics."""
        files = [sample_pdf_file]
        processor.collect_file_stats(files)

        assert sample_pdf_file.name in processor.file_stats
        stats = processor.file_stats[sample_pdf_file.name]
        assert stats["path"] == sample_pdf_file
        assert stats["initial_size"] > 0
        assert stats["age"] >= 0
        assert stats["is_stable"] is False

    def test_check_file_stability(self, sample_pdf_file, processor):
        """Test file stability checking."""
        files = [sample_pdf_file]
        processor.collect_file_stats(files)
        processor.check_file_stability()

        stats = processor.file_stats[sample_pdf_file.name]
        assert stats["final_size"] > 0
        assert stats["is_stable"] is True

    def test_move_file_success(self, sample_pdf_file, dest_dir, processor):
        """Test successful file move."""
        files = [sample_pdf_file]
        processor.collect_file_stats(files)
        processor.check_file_stability()

        file_stat = processor.file_stats[sample_pdf_file.name]
        result = processor.move_file(file_stat)

        assert result is True
        assert not sample_pdf_file.exists()
        assert (dest_dir / sample_pdf_file.name).exists()

    def test_move_file_with_permissions(self, sample_pdf_file, dest_dir, processor):
        """Test that file permissions are set correctly."""
        files = [sample_pdf_file]
        processor.collect_file_stats(files)
        processor.check_file_stability()

        file_stat = processor.file_stats[sample_pdf_file.name]
        processor.move_file(file_stat)

        moved_file = dest_dir / sample_pdf_file.name
        assert moved_file.exists()
        # Check permissions (should be 0660)
        mode = oct(moved_file.stat().st_mode)[-3:]
        assert mode == "660"

    def test_move_file_destination_exists(self, sample_pdf_file, dest_dir, processor):
        """Test handling when destination file already exists."""
        # Copy file to destination
        dest_file = dest_dir / sample_pdf_file.name
        dest_file.write_bytes(sample_pdf_file.read_bytes())

        files = [sample_pdf_file]
        processor.collect_file_stats(files)
        processor.check_file_stability()

        file_stat = processor.file_stats[sample_pdf_file.name]
        result = processor.move_file(file_stat)

        assert result is False

    def test_dry_run_mode(self, sample_pdf_file, processor):
        """Test dry-run mode doesn't move files."""
        processor.dry_run = True

        files = [sample_pdf_file]
        processor.collect_file_stats(files)
        processor.check_file_stability()

        file_stat = processor.file_stats[sample_pdf_file.name]
        result = processor.move_file(file_stat)

        assert result is True
        assert sample_pdf_file.exists()  # File should still exist in dry-run

    def test_run_with_no_files(self, source_dir, processor):
        """Test run with no files to process."""
        # Remove all files from source
        for f in source_dir.iterdir():
            f.unlink()

        result = processor.run()

        assert result == 0

    def test_run_with_regular_files(self, sample_pdf_file, sample_jpg_file, processor):
        """Test run processes regular files."""
        result = processor.run()

        assert result >= 1
        assert not sample_pdf_file.exists()

    def test_get_file_age_static_method(self, sample_pdf_file):
        """Test static file age getter."""
        age = ScanFileProcessor.get_file_age(sample_pdf_file)

        assert age >= 0
        assert isinstance(age, float)

    def test_get_file_age_nonexistent_file(self):
        """Test get_file_age returns 0 for nonexistent file."""
        nonexistent = Path("/nonexistent/path/file.txt")
        age = ScanFileProcessor.get_file_age(nonexistent)

        assert age == 0

    def test_file_types_normalization(self, source_dir, dest_dir):
        """Test that file types are normalized."""
        processor = ScanFileProcessor(
            source_dir=str(source_dir),
            dest_dir=str(dest_dir),
            dual_side_prefix="double-sided",
            user_id=1000,
            group_id=1000,
            stability_wait=0,
            max_age=10,
            file_types=["pdf", "PDF", ".jpg", ".JPG"],  # Mixed case and with/without dot
        )

        assert ".pdf" in processor.file_types
        assert ".jpg" in processor.file_types
        assert ".jpg" in processor.file_types


class TestDualSidedFileProcessing:
    """Test cases for dual-sided file processing."""

    def test_dual_sided_file_detection(self, dual_sided_pdfs, processor):
        """Test detection of dual-sided files."""
        files = processor.get_files_to_process()
        processor.collect_file_stats(files)

        dual_side_count = sum(1 for f in files if f.name.startswith("double-sided"))
        assert dual_side_count == 4

    def test_dual_sided_file_pairing(self, dual_sided_pdfs, processor):
        """Test that dual-sided files are paired correctly."""
        result = processor.run()

        # Should have merged pairs (1-2, 3-4)
        assert result >= 1

    def test_dual_sided_file_merge_creates_output(self, dual_sided_pdfs, dest_dir, processor):
        """Test that dual-sided file merging creates output."""
        processor.run()

        # Check if merged files were created in destination
        merged_files = list(dest_dir.glob("double-sided_*_merged.pdf"))
        # We should have at least 1 merged file from pairs (1,2) and (3,4)
        assert len(merged_files) >= 1

    def test_run_return_value_counts_merged(self, dual_sided_pdfs, processor):
        """Test that run returns correct count of processed files."""
        result = processor.run()

        assert isinstance(result, int)
        assert result >= 1


class TestFileStats:
    """Test cases for FileStats TypedDict."""

    def test_file_stats_structure(self, sample_pdf_file):
        """Test FileStats TypedDict structure."""
        stats: FileStats = {
            "path": sample_pdf_file,
            "initial_size": 1024,
            "age": 10.5,
            "final_size": 1024,
            "is_stable": True,
        }

        assert stats["path"] == sample_pdf_file
        assert stats["initial_size"] == 1024
        assert stats["age"] == 10.5
        assert stats["final_size"] == 1024
        assert stats["is_stable"] is True


class TestErrorHandling:
    """Test error handling in ScanFileProcessor."""

    def test_source_dir_not_exists(self, dest_dir):
        """Test handling of non-existent source directory."""
        processor = ScanFileProcessor(
            source_dir="/nonexistent/source",
            dest_dir=str(dest_dir),
            dual_side_prefix="double-sided",
            user_id=os.getuid(),
            group_id=os.getgid(),
            stability_wait=0,
            max_age=10,
            file_types=[".pdf"],
        )

        result = processor.run()
        assert result == 0

    def test_dest_dir_not_exists(self, source_dir, sample_pdf_file):
        """Test handling of non-existent destination directory."""
        processor = ScanFileProcessor(
            source_dir=str(source_dir),
            dest_dir="/nonexistent/dest",
            dual_side_prefix="double-sided",
            user_id=os.getuid(),
            group_id=os.getgid(),
            stability_wait=0,
            max_age=10,
            file_types=[".pdf"],
        )

        result = processor.run()
        assert result == 0

    def test_unstable_file_skipped(self, sample_pdf_file, processor):
        """Test that unstable files are skipped."""
        files = [sample_pdf_file]
        processor.collect_file_stats(files)

        # Don't check stability, mark file as unstable manually
        processor.file_stats[sample_pdf_file.name]["is_stable"] = False

        file_stat = processor.file_stats[sample_pdf_file.name]
        result = processor.move_file(file_stat)

        assert result is False
        assert sample_pdf_file.exists()

    def test_single_dual_sided_file_not_merged(self, source_dir, dest_dir, processor):
        """Test that a single dual-sided file is not merged (waiting for pair)."""
        # Create only one dual-sided PDF
        pdf_path = source_dir / "double-sided_1.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = processor.run()

        # Single file should not be merged, should remain in source
        assert pdf_path.exists()
        assert len(list(dest_dir.glob("*"))) == 0  # No files in destination

    def test_odd_number_dual_sided_files(self, source_dir, dest_dir, processor):
        """Test that odd number of dual-sided files leaves last one unmerged."""
        # Create 3 dual-sided PDFs (odd number)
        for i in range(1, 4):
            pdf_path = source_dir / f"double-sided_{i}.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with open(pdf_path, "wb") as f:
                writer.write(f)

        result = processor.run()

        # First pair (1,2) should be merged, file 3 should remain
        assert (source_dir / "double-sided_3.pdf").exists()
        # Should have one merged file
        merged_files = list(dest_dir.glob("double-sided_*_merged.pdf"))
        assert len(merged_files) >= 1
