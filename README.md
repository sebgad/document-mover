# document-mover

A Python-based automated PDF merging and file movement workflow, particularly useful for scanning operations.

## Features

### PDF Merger (`pdf-merger`)
- **Merge two PDFs** with alternating page order (page1, page2, page3, page4, etc.)
- **Delete source files** after successful merge (optional)
- **Remove empty pages** from the merged PDF (optional)
- **CLI interface** for easy command-line usage

### Consecutive PDF Merger (`process_pdf_merge`)
- **Auto-detect consecutive PDFs** based on filename numbering
- **Merge pairs** of consecutively numbered files automatically
- **Process entire folders** with batch operations
- **Dry-run mode** to preview operations before executing

### Document Mover (`document-mover`)
- **File stability checking** - ensures files are fully written before processing
- **Selective file movement** - separate handling for regular and dual-sided files
- **Dual-sided file pairing** - automatically pairs and merges dual-sided scans
- **Atomic operations** - safe file movements with proper permission handling
- **Comprehensive logging** - detailed tracking of all operations

## Installation

```bash
pdm install
```

## Usage

### PDF Merger

Merge two PDF files:
```bash
pdm run pdf-merger file1.pdf file2.pdf output.pdf
```

With options:
```bash
pdm run pdf-merger file1.pdf file2.pdf output.pdf --delete-source --remove-empty-pages --verbose
```

**Options:**
- `--delete-source`: Delete source PDF files after successful merge
- `--remove-empty-pages`: Remove empty pages from the merged PDF
- `--verbose`: Enable verbose logging

### Consecutive PDF Merger

Process a folder and merge consecutive PDFs:
```bash
pdm run process_pdf_merge /path/to/folder
```

With options:
```bash
pdm run process_pdf_merge /path/to/folder --dest-folder /path/to/dest --dry-run --verbose
```

**Options:**
- `--dest-folder`: Directory for merged PDF output (defaults to source folder)
- `--dry-run`: Preview operations without executing
- `--verbose`: Enable verbose logging

### Document Mover

Move processed documents:
```bash
pdm run document-mover /path/to/source --dest /path/to/dest
```

With options:
```bash
pdm run document-mover /path/to/source --dest /path/to/dest --dual-dest /path/to/dual-dest --stability-wait 5 --min-age 30 --verbose
```

**Options:**
- `--dest`: Destination folder for regular files (required)
- `--dual-dest`: Destination folder for dual-sided files
- `--stability-wait`: Seconds to wait before checking file stability (default: 2)
- `--min-age`: Minimum file age in seconds before processing (default: 60)
- `--verbose`: Enable verbose logging

## Configuration

### Ruff Formatting

The project is configured to use ruff with a line length of 120 characters. This is set in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 120
```

The VS Code editor is also configured to display a ruler at column 120 for consistency.

## Project Structure

```
document-mover/
├── src/
│   └── document_mover/
│       ├── __init__.py
│       ├── pdf_merger.py          # PDF merging utilities
│       ├── document_mover.py      # Main file movement system
│       └── file_lock.py           # File locking utilities
├── tests/
│   └── __init__.py
├── pyproject.toml                 # Project configuration & dependencies
└── README.md
```

## Requirements

- Python 3.13+
- pypdf >= 6.4.1
- ruff >= 0.14.8
- mypy >= 1.19.0

## Development

### Running Tests

```bash
pdm run pytest
```

### Code Quality

Format code with ruff:
```bash
pdm run ruff format .
```

Type checking with mypy:
```bash
pdm run mypy src/
```

## Use Cases

### Scanning Workflow
1. Scan dual-sided documents as separate files (page 1, page 2, etc.)
2. Run document-mover to automatically pair and merge dual-sided files
3. Process results to final destination with proper organization

### PDF Organization
1. Use consecutive PDF merger to automatically merge numbered PDF sets
2. Delete source files after successful merge to save space
3. Remove empty pages for cleaner final documents

## License

MIT