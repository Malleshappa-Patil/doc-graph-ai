"""
ingestion/pdf_parser.py
────────────────────────────────────────────────────────────────────────────────
Extracts raw text from a PDF file using PyMuPDF (imported as `fitz`).

WHY PyMuPDF?
  PyMuPDF is fast, accurate, and handles a wide range of PDF types:
    - Text-based PDFs (reports, papers, articles) → direct text extraction
    - Scanned PDFs → returns empty string per page (OCR not in scope)
  It does NOT require any server-side tools (like poppler or pdftotext).
  Pure Python installation via pip.

HOW PyMuPDF WORKS (simplified):
  1. fitz.open(path) loads the PDF file into memory.
  2. The document object is a list of Page objects.
  3. page.get_text("text") extracts the text layer from that page.
  4. We join all pages into a single string separated by newlines.

DESIGN DECISIONS:
  - Returns raw text as a single string (not a list of pages).
    WHY: The text_cleaner and chunker downstream don't care about page
    boundaries — they work on pure text content.
  - Does NOT do OCR. If the PDF is a scan, the text will be empty/minimal.
    That's a deliberate scope boundary — OCR adds significant complexity.
  - Raises specific exceptions with clear messages so the API layer
    can return meaningful HTTP error responses to the client.

USAGE:
    from ingestion.pdf_parser import parse_pdf
    text = parse_pdf("/path/to/document.pdf")
    print(text[:200])
────────────────────────────────────────────────────────────────────────────────
"""

import logging
from pathlib import Path

import pymupdf as fitz  # PyMuPDF — new recommended import name

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str | Path) -> str:
    """
    Extracts all text from a PDF file and returns it as a single string.

    Args:
        file_path (str | Path):
            Absolute or relative path to the PDF file.
            Accepts both a plain string and a pathlib.Path object.

            Example: "/app/uploads/report.pdf"
                     Path("uploads/report.pdf")

    Returns:
        str: The full text content of the PDF, with pages separated by
             double newlines. Trailing/leading whitespace is stripped.

             Returns an empty string if the PDF has no extractable text
             (e.g. it is a scanned image-only PDF).

    Raises:
        FileNotFoundError: If the file does not exist at the given path.
        ValueError:        If the file is not a valid PDF (fitz cannot open it).
        RuntimeError:      If text extraction fails for any other reason.

    Example:
        text = parse_pdf("/uploads/openai_report.pdf")
        # → "OpenAI was founded in 2015 by Sam Altman and Elon Musk..."
    """
    # Convert to Path object for consistent handling
    path = Path(file_path)

    # ── Guard: file must exist ────────────────────────────────────────────────
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    logger.info("Parsing PDF: %s", path.name)

    try:
        # Open the PDF document.
        # fitz.open() can open PDFs by file path (str or Path).
        # The result is a Document object — think of it as a list of Pages.
        doc = fitz.open(str(path))

    except Exception as exc:
        raise ValueError(
            f"Cannot open '{path.name}' as a PDF. "
            f"Ensure the file is a valid PDF. Error: {exc}"
        ) from exc

    try:
        page_texts: list[str] = []

        for page_number, page in enumerate(doc, start=1):
            # page.get_text("text") extracts the text layer.
            #
            # Other modes exist:
            #   "html"   → HTML with formatting
            #   "dict"   → structured dict with blocks and spans
            #   "words"  → list of individual words with coordinates
            #
            # We use "text" (plain text) — simplest, fastest, all we need.
            page_text = page.get_text("text")

            if page_text.strip():
                page_texts.append(page_text)
                logger.debug("Page %d: extracted %d chars", page_number, len(page_text))
            else:
                logger.debug("Page %d: no extractable text (possibly a scan)", page_number)

        # Join all pages with double newline to preserve paragraph flow
        full_text = "\n\n".join(page_texts).strip()

        logger.info(
            "PDF parsed: %d pages, %d total chars extracted",
            len(doc),
            len(full_text),
        )

        return full_text

    except Exception as exc:
        raise RuntimeError(
            f"Failed to extract text from '{path.name}': {exc}"
        ) from exc

    finally:
        # Always close the document to release file handles and memory.
        # fitz documents hold OS-level file handles — not closing them
        # causes resource leaks, especially under high upload volume.
        doc.close()
