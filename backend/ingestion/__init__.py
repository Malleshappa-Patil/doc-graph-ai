# This file marks ingestion/ as a Python package.
# It re-exports the two main functions other modules will call.
#
# Usage from other modules:
#   from ingestion import parse_pdf, chunk_text
#   from ingestion.pdf_parser import parse_pdf
#   from ingestion.text_cleaner import clean_text, chunk_text

from ingestion.pdf_parser import parse_pdf
from ingestion.text_cleaner import clean_text, chunk_text

__all__ = ["parse_pdf", "clean_text", "chunk_text"]
