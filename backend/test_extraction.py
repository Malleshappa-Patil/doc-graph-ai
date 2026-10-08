"""
test_extraction.py
────────────────────────────────────────────────────────────────────────────────
Tests for extraction/prompts.py, entity_extractor.py, relationship_extractor.py
No real Gemini API calls are made — GeminiClient is fully mocked.
────────────────────────────────────────────────────────────────────────────────
"""
import sys
import json
import unittest.mock as mock

sys.path.insert(0, ".")

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: prompts.py — build_entity_prompt
# ─────────────────────────────────────────────────────────────────────────────
print("=== Test 1: build_entity_prompt ===")
from extraction.prompts import build_entity_prompt, build_relationship_prompt
from schemas.entities import COMMON_ENTITY_TYPES
from schemas.relationships import COMMON_RELATIONSHIP_TYPES

text = "Sam Altman is the CEO of OpenAI."
prompt = build_entity_prompt(text)

assert text in prompt,                       "Text should appear in prompt"
assert "Person" in prompt,                   "Common entity types should appear"
assert "Organization" in prompt,             "Common entity types should appear"
assert "entities" in prompt,                 "Output format key should appear"
assert "ONLY valid JSON" in prompt,          "JSON constraint should appear"
print(f"  [OK] Entity prompt built ({len(prompt)} chars)")
print(f"  [OK] Contains text, entity types, JSON format instructions")

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: prompts.py — build_relationship_prompt
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 2: build_relationship_prompt ===")

entities_json = json.dumps([
    {"name": "Sam Altman", "type": "Person"},
    {"name": "OpenAI",     "type": "Organization"},
])
rel_prompt = build_relationship_prompt(text, entities_json)

assert text in rel_prompt,                   "Text should appear in prompt"
assert "Sam Altman" in rel_prompt,           "Entities JSON should appear"
assert "OpenAI" in rel_prompt,               "Entities JSON should appear"
assert "UPPER_SNAKE_CASE" in rel_prompt,     "Relation format instruction should appear"
assert "ONLY valid JSON" in rel_prompt,      "JSON constraint should appear"
print(f"  [OK] Relationship prompt built ({len(rel_prompt)} chars)")
print(f"  [OK] Contains text, entities, relationship type instructions")

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: extract_entities — empty text returns empty EntityList
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 3: extract_entities — empty text ===")
from extraction.entity_extractor import extract_entities

result = extract_entities("")
assert result.entities == [], f"Expected empty list, got: {result.entities}"
result2 = extract_entities("   ")
assert result2.entities == []
print("  [OK] Empty and whitespace-only text returns EntityList(entities=[])")

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: extract_entities — happy path (mocked Gemini)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 4: extract_entities — happy path (mocked) ===")
from extraction.entity_extractor import extract_entities
from llm.gemini_client import GeminiClient

gemini_response = {
    "entities": [
        {"name": "Sam Altman", "type": "Person"},
        {"name": "openai",     "type": "organization"},  # test normalization
        {"name": "GPT-4",      "type": "Product"},
        {"name": "sam altman", "type": "person"},        # test deduplication
    ]
}

with mock.patch.object(GeminiClient, "get_instance") as mock_get:
    mock_client = mock.MagicMock()
    mock_client.generate_json.return_value = gemini_response
    mock_get.return_value = mock_client

    result = extract_entities("Sam Altman is the CEO of OpenAI, which created GPT-4.")

# Verify results
names = [e.name for e in result.entities]
assert "Sam Altman" in names,       f"Expected 'Sam Altman', got: {names}"
assert "Openai" in names,           f"Expected normalized 'Openai', got: {names}"
assert "Gpt-4" in names or "Gpt 4" in names or "GPT-4" in names, \
    f"Expected 'GPT-4' variant, got: {names}"

# Deduplication: "Sam Altman" and "sam altman" should collapse to 1
sam_count = sum(1 for n in names if n.lower() == "sam altman")
assert sam_count == 1, f"Expected 1 Sam Altman after dedup, got {sam_count}: {names}"

print(f"  [OK] Extracted {len(result.entities)} unique entities: {names}")
print(f"  [OK] Names normalized to Title Case")
print(f"  [OK] Duplicates removed")

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: extract_entities — malformed JSON returns empty list (no crash)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 5: extract_entities — malformed JSON → graceful empty ===")

with mock.patch.object(GeminiClient, "get_instance") as mock_get:
    mock_client = mock.MagicMock()
    # Simulate GeminiClient.generate_json raising ValueError (bad JSON)
    mock_client.generate_json.side_effect = ValueError("Invalid JSON from Gemini")
    mock_get.return_value = mock_client

    result = extract_entities("Some text here.")

assert result.entities == [], f"Expected empty list on bad JSON, got: {result.entities}"
print("  [OK] Malformed JSON returns EntityList(entities=[]) without crashing")

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: extract_relationships — empty text/entities returns empty
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 6: extract_relationships — empty inputs ===")
from extraction.relationship_extractor import extract_relationships
from schemas.entities import EntityList, Entity
from schemas.relationships import RelationshipList

result = extract_relationships("", EntityList(entities=[]))
assert result.relationships == []

# Empty entity list should also return empty (no point calling Gemini)
result2 = extract_relationships("Sam Altman is CEO of OpenAI.", EntityList(entities=[]))
assert result2.relationships == []
print("  [OK] Empty text or empty entity list returns RelationshipList(relationships=[])")

# ─────────────────────────────────────────────────────────────────────────────
# Test 7: extract_relationships — happy path (mocked Gemini)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 7: extract_relationships — happy path (mocked) ===")

known_entities = EntityList(entities=[
    Entity(name="Sam Altman", type="Person"),
    Entity(name="Openai",     type="Organization"),
    Entity(name="Gpt-4",      type="Product"),
])

gemini_rel_response = {
    "relationships": [
        {"source": "Sam Altman", "target": "Openai",  "relation": "ceo_of"},   # test normalization
        {"source": "Openai",     "target": "Gpt-4",   "relation": "CREATED"},
        {"source": "Sam Altman", "target": "Openai",  "relation": "CEO_OF"},   # test deduplication
    ]
}

with mock.patch.object(GeminiClient, "get_instance") as mock_get:
    mock_client = mock.MagicMock()
    mock_client.generate_json.return_value = gemini_rel_response
    mock_get.return_value = mock_client

    result = extract_relationships(
        "Sam Altman is the CEO of OpenAI, which created GPT-4.",
        known_entities,
    )

rels = [(r.source, r.relation, r.target) for r in result.relationships]
assert len(result.relationships) == 2, f"Expected 2 unique rels (after dedup), got: {rels}"
# Check normalization
for r in result.relationships:
    assert r.relation == r.relation.upper(), f"Relation not upper-case: {r.relation}"
print(f"  [OK] Extracted {len(result.relationships)} unique relationships: {rels}")
print(f"  [OK] Relations normalized to UPPER_SNAKE_CASE")
print(f"  [OK] Duplicates removed")

# ─────────────────────────────────────────────────────────────────────────────
# Test 8: extract_relationships — hallucinated entity is filtered out
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 8: extract_relationships — hallucinated entity filtered ===")

gemini_hallucinated = {
    "relationships": [
        # Valid: both entities are known
        {"source": "Sam Altman", "target": "Openai", "relation": "CEO_OF"},
        # Hallucinated: "Google" is NOT in known_entities
        {"source": "Openai",     "target": "Google", "relation": "COMPETES_WITH"},
    ]
}

with mock.patch.object(GeminiClient, "get_instance") as mock_get:
    mock_client = mock.MagicMock()
    mock_client.generate_json.return_value = gemini_hallucinated
    mock_get.return_value = mock_client

    result = extract_relationships(
        "Sam Altman is the CEO of OpenAI.",
        known_entities,
    )

assert len(result.relationships) == 1, \
    f"Expected 1 rel (hallucinated filtered), got: {[(r.source, r.relation, r.target) for r in result.relationships]}"
assert result.relationships[0].relation == "CEO_OF"
print(f"  [OK] Hallucinated entity 'Google' filtered out — only 1 valid relationship kept")

# ─────────────────────────────────────────────────────────────────────────────
# Test 9: extract_relationships_from_chunks — length mismatch raises ValueError
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 9: extract_relationships_from_chunks — length mismatch ===")
from extraction.relationship_extractor import extract_relationships_from_chunks

try:
    extract_relationships_from_chunks(
        chunks=["chunk1", "chunk2"],
        entities_per_chunk=[EntityList(entities=[])],  # wrong length
    )
    assert False, "Should have raised ValueError"
except ValueError as e:
    print(f"  [OK] ValueError raised: {e}")

print()
print("=" * 60)
print("All extraction tests passed ✓")
