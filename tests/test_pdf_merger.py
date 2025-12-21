#!/usr/bin/env python3
"""Tests for PDF merger functionality."""

import tempfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from document_mover.pdf_merger import PDFMerger


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_pdf_page1(temp_dir):
    """Create a simple PDF with one page."""
    pdf_path = temp_dir / "page1.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


@pytest.fixture
def sample_pdf_page2(temp_dir):
    """Create a simple PDF with one page."""
    pdf_path = temp_dir / "page2.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


@pytest.fixture
def sample_pdf_multi_page(temp_dir):
    """Create a PDF with multiple pages."""
    pdf_path = temp_dir / "multi_page.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


class TestPDFMerger:
    """Test cases for PDFMerger class."""

    def test_merge_two_pdfs(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test merging two PDFs."""
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        result = merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path,
            delete_source=False,
            remove_empty_pages=False,
        )

        assert result is True
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_merge_creates_output_file(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test that merge creates the output file."""
        output_path = temp_dir / "output.pdf"
        merger = PDFMerger()

        merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path,
            delete_source=False,
        )

        assert output_path.exists()

    def test_merge_with_delete_source(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test that source files are deleted when delete_source=True."""
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        # Verify source files exist
        assert sample_pdf_page1.exists()
        assert sample_pdf_page2.exists()

        merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path,
            delete_source=True,
            remove_empty_pages=False,
        )

        # Verify output exists and sources are deleted
        assert output_path.exists()
        assert not sample_pdf_page1.exists()
        assert not sample_pdf_page2.exists()

    def test_merge_without_delete_source(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test that source files are kept when delete_source=False."""
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path,
            delete_source=False,
        )

        # Verify output exists and sources are still there
        assert output_path.exists()
        assert sample_pdf_page1.exists()
        assert sample_pdf_page2.exists()

    def test_merge_with_non_existent_file(self, sample_pdf_page1, temp_dir):
        """Test merge fails gracefully with non-existent file."""
        non_existent = temp_dir / "non_existent.pdf"
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        result = merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=non_existent,
            output_path=output_path,
            delete_source=False,
        )

        assert result is False
        assert not output_path.exists()

    def test_merge_output_file_has_content(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test that merged PDF has actual content."""
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path,
            delete_source=False,
        )

        # Read merged PDF and verify it has content
        from pypdf import PdfReader

        reader = PdfReader(output_path)
        assert len(reader.pages) > 0

    def test_merge_multipage_pdfs(self, sample_pdf_page1, sample_pdf_multi_page, temp_dir):
        """Test merging PDFs with different page counts."""
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        result = merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_multi_page,
            output_path=output_path,
            delete_source=False,
        )

        assert result is True
        assert output_path.exists()

        # Verify merged PDF has pages from both sources
        from pypdf import PdfReader

        reader = PdfReader(output_path)
        # Should have at least pages from both PDFs (1 from page1 + 3 from multi_page)
        assert len(reader.pages) >= 4

    def test_merge_with_remove_empty_pages(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test merge with empty page removal."""
        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        result = merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path,
            delete_source=False,
            remove_empty_pages=True,
        )

        assert result is True
        assert output_path.exists()

    def test_merge_destination_path_type(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test merge works with both string and Path object for output."""
        # Test with Path object
        output_path_obj = temp_dir / "merged1.pdf"
        merger = PDFMerger()

        result1 = merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path_obj,
            delete_source=False,
        )

        assert result1 is True
        assert output_path_obj.exists()

        # Test with string
        output_path_str = str(temp_dir / "merged2.pdf")
        result2 = merger.merge(
            pdf1=sample_pdf_page1,
            pdf2=sample_pdf_page2,
            output_path=output_path_str,
            delete_source=False,
        )

        assert result2 is True
        assert Path(output_path_str).exists()


class TestPDFMergerEdgeCases:
    """Test edge cases for PDFMerger."""

    def test_merge_invalid_pdf_file(self, temp_dir):
        """Test merge fails with invalid PDF file."""
        invalid_pdf = temp_dir / "invalid.pdf"
        invalid_pdf.write_text("This is not a valid PDF")

        sample_pdf = temp_dir / "sample.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(sample_pdf, "wb") as f:
            writer.write(f)

        output_path = temp_dir / "merged.pdf"
        merger = PDFMerger()

        result = merger.merge(
            pdf1=invalid_pdf,
            pdf2=sample_pdf,
            output_path=output_path,
            delete_source=False,
        )

        assert result is False

    def test_merge_to_readonly_directory(self, sample_pdf_page1, sample_pdf_page2, temp_dir):
        """Test merge fails when output directory is read-only."""
        import os

        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()

        # Make directory read-only
        os.chmod(readonly_dir, 0o444)

        merger = PDFMerger()

        try:
            result = merger.merge(
                pdf1=sample_pdf_page1,
                pdf2=sample_pdf_page2,
                output_path=readonly_dir / "merged.pdf",
                delete_source=False,
            )
            assert result is False
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)
