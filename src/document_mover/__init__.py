"""Document mover package."""

from document_mover.document_mover import main as document_mover_main
from document_mover.pdf_merger import main as pdf_merger_main
from .file_list import FileStats, FileListHandler

__all__ = ["document_mover_main", "pdf_merger_main", "FileStats", "FileListHandler"]
