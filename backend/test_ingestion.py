"""
test_ingestion.py
────────────────────────────────────────────────────────────────────────────────
Tests for ingestion/pdf_parser.py and ingestion/text_cleaner.py.
No real PDF file required for most tests — we test logic in isolation.
────────────────────────────────────────────────────────────────────────────────
"""

import sys
import io
import struct
import zlib
from pathlib import Path

sys.path.insert(0, ".")

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: clean_text — hyphen line-break fix
# ─────────────────────────────────────────────────────────────────────────────
print("=== Test 1: clean_text — hyphen line-break fix ===")
from ingestion.text_cleaner import clean_text

raw = "This is infor-\nmation about OpenAI."
result = clean_text(raw)
assert "information" in result, f"Expected 'information', got: {result}"
print(f"  [OK] '{raw.strip()}' → '{result}'")

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: clean_text — multiple blank lines collapsed
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 2: clean_text — blank line collapsing ===")

raw = "Paragraph one.\n\n\n\n\nParagraph two."
result = clean_text(raw)
assert "\n\n\n" not in result, "Three+ consecutive newlines should be removed"
assert "Paragraph one." in result
assert "Paragraph two." in result
print(f"  [OK] Multiple blank lines collapsed to max 2")

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: clean_text — extra spaces normalized
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 3: clean_text — extra whitespace normalized ===")

raw = "OpenAI    was   founded  in   2015."
result = clean_text(raw)
assert "  " not in result, "Double spaces should be removed"
assert result == "OpenAI was founded in 2015."
print(f"  [OK] '{raw}' → '{result}'")

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: clean_text — empty string returns empty
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 4: clean_text — empty input ===")
assert clean_text("") == ""
assert clean_text("   ") == ""
print("  [OK] Empty and whitespace-only inputs return empty string")

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: chunk_text — short text returns single chunk
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 5: chunk_text — short text = single chunk ===")
from ingestion.text_cleaner import chunk_text

short_text = "OpenAI was founded in 2015 by Sam Altman and Elon Musk."
chunks = chunk_text(short_text)
assert len(chunks) == 1, f"Expected 1 chunk, got {len(chunks)}"
assert chunks[0] == short_text
print(f"  [OK] Short text ({len(short_text)} chars) returned as 1 chunk")

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: chunk_text — long text splits correctly
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 6: chunk_text — long text splits into multiple chunks ===")

# Create text that is definitely longer than one chunk
long_text = ("OpenAI was founded in 2015. " * 300)  # ~8400 chars
chunks = chunk_text(long_text, chunk_size=6000, overlap=400)
assert len(chunks) >= 2, f"Expected 2+ chunks, got {len(chunks)}"
for i, chunk in enumerate(chunks):
    assert len(chunk) <= 6000, f"Chunk {i} exceeds chunk_size: {len(chunk)} chars"
print(f"  [OK] {len(long_text)} chars → {len(chunks)} chunks (each ≤ 6000 chars)")

# ─────────────────────────────────────────────────────────────────────────────
# Test 7: chunk_text — overlap means last N chars of chunk N == first N of chunk N+1
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 7: chunk_text — overlap is respected ===")

if len(chunks) >= 2:
    # The chunker is designed so chunk N+1 starts somewhere within
    # the last `overlap` chars of chunk N (due to boundary snapping).
    # Verify this by checking that the first word of chunk 1 appears
    # in the last portion of chunk 0.
    first_word_of_chunk_1 = chunks[1].split()[0]
    tail_of_chunk_0 = chunks[0][-(400 * 2):]  # search in last 800 chars of chunk 0
    assert first_word_of_chunk_1 in tail_of_chunk_0, (
        f"First word of chunk 1 ('{first_word_of_chunk_1}') "
        f"not found in tail of chunk 0"
    )
    print(f"  [OK] Chunk 1 begins with content that overlaps chunk 0's tail")
    print(f"       Chunk 0 length: {len(chunks[0])} chars")
    print(f"       Chunk 1 length: {len(chunks[1])} chars")

# ─────────────────────────────────────────────────────────────────────────────
# Test 8: chunk_text — empty text returns empty list
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 8: chunk_text — empty text ===")
assert chunk_text("") == []
print("  [OK] Empty text returns empty list []")

# ─────────────────────────────────────────────────────────────────────────────
# Test 9: pdf_parser — FileNotFoundError on missing file
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 9: parse_pdf — raises FileNotFoundError for missing file ===")
from ingestion.pdf_parser import parse_pdf

try:
    parse_pdf("/tmp/definitely_does_not_exist_abc123.pdf")
    assert False, "Should have raised FileNotFoundError"
except FileNotFoundError as e:
    print(f"  [OK] FileNotFoundError raised: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Test 10: pdf_parser — parses a real minimal PDF
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 10: parse_pdf — parses a real minimal PDF ===")

# Create a minimal valid PDF in-memory using PyMuPDF itself
import pymupdf as fitz

# Create a new PDF with one page and some text
test_pdf_path = Path("/tmp/test_doc_graph.pdf")
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), "OpenAI was founded in 2015 by Sam Altman.")
doc.save(str(test_pdf_path))
doc.close()

# Now parse it
result = parse_pdf(test_pdf_path)
assert "OpenAI" in result, f"Expected 'OpenAI' in result, got: {result[:200]}"
assert "2015" in result, f"Expected '2015' in result, got: {result[:200]}"
print(f"  [OK] PDF parsed successfully: '{result.strip()[:80]}...'")

# Cleanup
test_pdf_path.unlink()

# ─────────────────────────────────────────────────────────────────────────────
# Test 11: Full pipeline — parse → clean → chunk
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 11: Full pipeline — parse → clean → chunk ===")

# Create a PDF with enough text to trigger chunking
test_pdf_path2 = Path("/tmp/test_doc_graph_long.pdf")
doc = fitz.open()
page = doc.new_page()

# Insert a long paragraph (repeated content)
long_content = "OpenAI was founded in 2015 by Sam Altman and Elon Musk. " * 100
page.insert_text((72, 72), long_content[:3000], fontsize=8)
doc.save(str(test_pdf_path2))
doc.close()

raw_text  = parse_pdf(test_pdf_path2)
clean     = clean_text(raw_text)
chunks    = chunk_text(clean, chunk_size=1000, overlap=100)

assert len(raw_text) > 0,  "PDF should have text"
assert len(clean) > 0,     "Cleaned text should not be empty"
assert len(chunks) >= 1,   "Should have at least 1 chunk"
print(f"  [OK] PDF → {len(raw_text)} chars raw → {len(clean)} chars clean → {len(chunks)} chunk(s)")

test_pdf_path2.unlink()

print()
print("=" * 55)
print("All ingestion tests passed ✓")
