"""Simple PDF merger for combining two PDF files."""

import pypdf
from pathlib import Path
import logging
import argparse
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


class PDFMerger:
    """A class to merge two PDF files into one."""

    def __init__(self) -> None:
        """Initialize the PDF merger."""
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def is_page_empty(page) -> bool:
        """
        Check if a PDF page is empty or contains only whitespace.

        Args:
            page: A PDF page object.

        Returns:
            True if page is empty or contains only whitespace, False otherwise.
        """
        try:
            text = page.extract_text().strip()
            return len(text) == 0
        except Exception:
            # If we can't extract text, assume page has content
            return False

    def merge(
        self,
        pdf1: str | Path,
        pdf2: str | Path,
        output_path: str | Path,
        delete_source: bool = False,
        remove_empty_pages: bool = False,
    ) -> bool:
        """
        Merge two PDF files into one.

        Args:
            pdf1: Path to the first PDF file.
            pdf2: Path to the second PDF file.
            output_path: Path where the merged PDF will be saved.
            delete_source: If True, delete source files after successful merge.
            remove_empty_pages: If True, remove empty/whitespace-only pages from merged PDF.

        Returns:
            True on success, False on failure
        """
        pdf1 = Path(pdf1)
        pdf2 = Path(pdf2)
        output_path = Path(output_path)

        # Validate input files
        if not pdf1.exists():
            self.logger.error(f"PDF file not found: {pdf1}")
            return False
        if not pdf2.exists():
            self.logger.error(f"PDF file not found: {pdf2}")
            return False

        try:
            self.logger.info(f"Merging: {pdf1.name} + {pdf2.name}")

            merger = pypdf.PdfWriter()

            with open(pdf1, "rb") as f1, open(pdf2, "rb") as f2:
                reader1 = pypdf.PdfReader(f1)
                reader2 = pypdf.PdfReader(f2)

                pages1 = list(reader1.pages)
                pages2 = list(reversed(reader2.pages))

                # Alternate pages from both files
                max_pages = max(len(pages1), len(pages2))
                for i in range(max_pages):
                    if i < len(pages1):
                        if remove_empty_pages and self.is_page_empty(pages1[i]):
                            self.logger.debug(f"Skipping empty page from {pdf1.name} at index {i}")
                        else:
                            merger.add_page(pages1[i])
                    if i < len(pages2):
                        if remove_empty_pages and self.is_page_empty(pages2[i]):
                            self.logger.debug(f"Skipping empty page from {pdf2.name} at index {i}")
                        else:
                            merger.add_page(pages2[i])

            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            merger.write(str(output_path))
            merger.close()

            self.logger.info(f"Successfully created merged PDF: {output_path}")

            # Delete source files if requested
            if delete_source:
                try:
                    pdf1.unlink()
                    self.logger.info(f"Deleted source file: {pdf1.name}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete {pdf1.name}: {e}")

                try:
                    pdf2.unlink()
                    self.logger.info(f"Deleted source file: {pdf2.name}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete {pdf2.name}: {e}")

            return True

        except Exception as e:
            self.logger.error(f"Error merging PDF files: {e}")
            return False


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge two PDF files into one", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("pdf1", type=Path, help="First PDF file to merge")

    parser.add_argument("pdf2", type=Path, help="Second PDF file to merge")

    parser.add_argument("output", type=Path, help="Output file path for merged PDF")

    parser.add_argument("--delete-source", action="store_true", help="Delete source files after successful merge")

    parser.add_argument(
        "--remove-empty-pages", action="store_true", help="Remove empty or whitespace-only pages from merged PDF"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


def main():
    """Main CLI entry point."""
    args = parse_arguments()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    merger = PDFMerger()
    success = merger.merge(
        args.pdf1, args.pdf2, args.output, delete_source=args.delete_source, remove_empty_pages=args.remove_empty_pages
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
