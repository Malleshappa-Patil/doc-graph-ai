"""
ingestion/text_cleaner.py
────────────────────────────────────────────────────────────────────────────────
Cleans and chunks raw PDF text before it is sent to Gemini for extraction.

TWO RESPONSIBILITIES:
  1. clean_text()  — Removes noise from raw PDF text (extra whitespace,
                     broken hyphenation, garbage characters).
  2. chunk_text()  — Splits clean text into overlapping segments that fit
                     within Gemini's token limit.

WHY CLEAN BEFORE CHUNKING?
  Raw PDF text from PyMuPDF often contains:
    - Multiple consecutive blank lines (from PDF layout whitespace)
    - Words broken across lines with hyphens: "infor-\nmation" → "information"
    - Ligature characters that look like garbage: "ﬁle" instead of "file"
    - Page headers/footers mixed into the content
  Cleaning first ensures Gemini sees dense, meaningful text.

WHY CHUNK?
  Gemini has a context window limit. For gemini-1.5-flash it's ~1M tokens,
  but in practice:
    - Sending very large text in one call → high latency and cost
    - Very large context → Gemini may miss entities buried deep in the text
  Chunking with overlap ensures:
    - Each call is fast and focused
    - Entities/relationships that span chunk boundaries are not lost
      (overlap means the end of chunk N is the beginning of chunk N+1)

CHUNK SIZE STRATEGY:
  We use CHARACTER counts (not token counts) because:
    - Tokenizers vary by model and are expensive to run locally
    - 1 token ≈ 4 characters on average (rough heuristic)
    - CHUNK_SIZE = 6000 chars ≈ ~1500 tokens → well within Gemini's limits

USAGE:
    from ingestion.text_cleaner import clean_text, chunk_text

    raw  = parse_pdf("document.pdf")
    text = clean_text(raw)
    for chunk in chunk_text(text):
        entities = extract_entities(chunk)
────────────────────────────────────────────────────────────────────────────────
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Chunking configuration ─────────────────────────────────────────────────────
# CHUNK_SIZE:    Maximum characters per chunk (~1500 tokens at 4 chars/token)
# CHUNK_OVERLAP: Characters repeated between consecutive chunks.
#                WHY: An entity or relationship might be mentioned right at
#                the boundary between two chunks. Overlap ensures it appears
#                fully in at least one chunk.
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 400


def clean_text(text: str) -> str:
    """
    Cleans raw PDF text by removing noise and normalizing whitespace.

    Cleaning steps (in order):
      1. Fix hyphenated line-breaks  ("infor-\\nma tion" → "information")
      2. Replace all whitespace sequences with single spaces
      3. Normalize multiple blank lines into at most one
      4. Strip leading/trailing whitespace

    Args:
        text (str): Raw text from pdf_parser.parse_pdf().

    Returns:
        str: Cleaned text, ready for chunking and entity extraction.

    Example:
        raw = "OpenAI  was   found-\\ned in\\n\\n\\n\\n2015."
        clean_text(raw)
        # → "OpenAI was founded in 2015."
    """
    if not text:
        return ""

    # Step 1: Fix hyphenated line-breaks.
    # PDFs often break long words across lines with a hyphen:
    #   "infor-
    #    mation"
    # This regex matches a hyphen followed by a newline (with optional spaces)
    # and removes both, joining the word back together.
    text = re.sub(r"-\s*\n\s*", "", text)

    # Step 2: Normalize all whitespace runs within a line.
    # Replaces tabs, multiple spaces, etc. with a single space.
    # We use a line-by-line approach to preserve paragraph breaks.
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(lines)

    # Step 3: Collapse 3+ consecutive blank lines into at most 2.
    # Two blank lines = paragraph break. Three or more = wasted space.
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Step 4: Final strip
    return text.strip()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Splits text into overlapping chunks of a fixed maximum character size.

    HOW IT WORKS:
      - We slide a window of size `chunk_size` over the text.
      - Each next window starts at (previous_start + chunk_size - overlap).
      - So the last `overlap` characters of chunk N are also the first
        `overlap` characters of chunk N+1.

    Chunk boundaries are adjusted to fall on sentence or word boundaries
    where possible, to avoid cutting mid-sentence.

    Args:
        text (str):
            The cleaned text to split. Should be the output of clean_text().

        chunk_size (int):
            Maximum number of characters per chunk.
            Default: 6000 (~1500 tokens).

        overlap (int):
            Number of characters to repeat between consecutive chunks.
            Default: 400 (~100 tokens).

    Returns:
        list[str]: List of text chunks. Each chunk is at most `chunk_size`
                   characters. May return a single-element list if the text
                   is shorter than `chunk_size`.

    Example:
        chunks = chunk_text("A " * 5000, chunk_size=6000, overlap=400)
        len(chunks)  # → 2 (text is 10000 chars, split into 2 overlapping chunks)

    Notes:
        - If text is empty, returns an empty list [].
        - If text fits in one chunk, returns [text] (a one-element list).
        - Overlap cannot be >= chunk_size (raises ValueError).
    """
    if not text:
        logger.warning("chunk_text received empty text — returning empty list")
        return []

    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )

    # If the whole text fits in one chunk, return it as-is
    if len(text) <= chunk_size:
        logger.debug("Text fits in a single chunk (%d chars)", len(text))
        return [text]

    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        # Calculate the raw end of this chunk
        end = start + chunk_size

        # If we haven't reached the end of the text, try to find a
        # clean break point (end of sentence or end of word) rather than
        # cutting mid-sentence.
        if end < text_length:
            # Prefer breaking at a sentence boundary (. ! ?)
            # Look backward from `end` for the last sentence-ending punctuation
            sentence_break = _find_sentence_boundary(text, end, chunk_size)
            if sentence_break > start:
                # Found a sentence boundary — use it
                end = sentence_break
            else:
                # No sentence boundary found — fall back to word boundary
                word_break = text.rfind(" ", start, end)
                if word_break > start:
                    end = word_break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            logger.debug(
                "Chunk %d: chars %d-%d (%d chars)",
                len(chunks), start, end, len(chunk)
            )

        # Move the window forward, stepping back by `overlap` chars
        # so the next chunk starts `overlap` chars before this chunk ended.
        start = end - overlap

        # Safety: if `end - overlap` didn't advance (edge case with tiny text),
        # force forward progress to prevent infinite loop.
        if start <= 0 and len(chunks) > 0:
            break

    logger.info(
        "Text chunked: %d chars → %d chunk(s) (size=%d, overlap=%d)",
        text_length, len(chunks), chunk_size, overlap,
    )

    return chunks


def _find_sentence_boundary(text: str, near: int, chunk_size: int) -> int:
    """
    Finds the position just after the last sentence-ending punctuation
    (period, exclamation mark, or question mark) before position `near`.

    This is used by chunk_text() to prefer clean sentence breaks over
    breaking mid-sentence.

    Args:
        text (str): The full text.
        near (int): Position to search backwards from.

    Returns:
        int: Position just after the last sentence boundary found,
             or -1 if no sentence boundary found in the search window.

    Example:
        text = "OpenAI was founded in 2015. It created GPT-4 in 2023."
        _find_sentence_boundary(text, 35)
        # → 27  (position after the first period + space)
    """
    # Search in the last 20% of the chunk for a sentence boundary.
    # This avoids breaking very early if a sentence ends near the chunk start.
    search_start = max(0, near - chunk_size // 5)
    window = text[search_start:near]

    # Find all positions of sentence-ending punctuation followed by whitespace
    matches = list(re.finditer(r"[.!?]\s+", window))

    if matches:
        # Take the last match (rightmost sentence end in the window)
        last_match = matches[-1]
        # Return the position after the punctuation + whitespace
        return search_start + last_match.end()

    return -1
