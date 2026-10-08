"""
test_graph.py
────────────────────────────────────────────────────────────────────────────────
Tests for graph/ — neo4j_client, graph_builder, graph_query, cypher_generator.
Neo4jClient is fully mocked — no real Neo4j connection required.
────────────────────────────────────────────────────────────────────────────────
"""
import sys
import unittest.mock as mock

sys.path.insert(0, ".")

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: _sanitize_label — Cypher injection prevention
# ─────────────────────────────────────────────────────────────────────────────
print("=== Test 1: _sanitize_label ===")
from graph.graph_builder import _sanitize_label

cases = [
    ("Organization",   "Organization"),
    ("Software Tool",  "Software_Tool"),
    ("CEO & Founder",  "CEO_Founder"),
    ("Person",         "Person"),
    ("!!!",            "Entity"),        # fallback
    ("",               "Entity"),        # empty fallback
    ("Concept_Map",    "Concept_Map"),
]

for raw, expected in cases:
    result = _sanitize_label(raw)
    status = "OK" if result == expected else "FAIL"
    print(f"  [{status}] '{raw}' → '{result}' (expected: '{expected}')")
    assert result == expected, f"Mismatch for '{raw}'"

print("  All label sanitization cases passed")

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: build_graph — MERGE nodes and relationships (mocked Neo4j)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 2: build_graph — mocked Neo4j ===")
from graph.graph_builder import build_graph
from graph.neo4j_client import Neo4jClient
from schemas.entities import EntityList, Entity
from schemas.relationships import RelationshipList, Relationship

entities = EntityList(entities=[
    Entity(name="Sam Altman", type="Person"),
    Entity(name="Openai",     type="Organization"),
    Entity(name="Gpt-4",      type="Product"),
])
relationships = RelationshipList(relationships=[
    Relationship(source="Sam Altman", target="Openai",  relation="CEO_OF"),
    Relationship(source="Openai",     target="Gpt-4",   relation="CREATED"),
])

# Mock Neo4jClient so no real DB connection is made
mock_client = mock.MagicMock()
# run_query returns a non-empty list → counts as "merged"
mock_client.run_query.return_value = [{"name": "dummy"}]

with mock.patch.object(Neo4jClient, "get_instance", return_value=mock_client):
    result = build_graph(entities, relationships, document_id="doc-001")

assert result["nodes_merged"]         == 3, f"Expected 3 nodes, got {result}"
assert result["relationships_merged"] == 2, f"Expected 2 rels, got {result}"
print(f"  [OK] build_graph returned: {result}")

# Verify MERGE queries were called (not CREATE)
all_calls = [str(call) for call in mock_client.run_query.call_args_list]
assert all("MERGE" in call for call in all_calls), "All queries should use MERGE"
print(f"  [OK] All {len(all_calls)} queries used MERGE")

# Verify label sanitization in actual Cypher calls
cypher_calls = [call.args[0] for call in mock_client.run_query.call_args_list]
assert any("Person" in c for c in cypher_calls),       "Expected Person label in Cypher"
assert any("Organization" in c for c in cypher_calls), "Expected Organization label in Cypher"
assert any("CEO_OF" in c for c in cypher_calls),       "Expected CEO_OF in relationship Cypher"
print("  [OK] Labels and relationship types correctly embedded in Cypher")

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: execute_cypher — delegates to Neo4jClient.run_query
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 3: execute_cypher — mocked ===")
from graph.graph_query import execute_cypher

mock_client2 = mock.MagicMock()
mock_client2.run_query.return_value = [
    {"creator": "Openai", "product": "Gpt-4"}
]

with mock.patch.object(Neo4jClient, "get_instance", return_value=mock_client2):
    results = execute_cypher(
        "MATCH (a)-[:CREATED]->(b) RETURN a.name AS creator, b.name AS product"
    )

assert len(results) == 1
assert results[0]["creator"] == "Openai"
assert results[0]["product"] == "Gpt-4"
print(f"  [OK] execute_cypher returned: {results}")

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: get_graph_data — nodes and edges structure
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 4: get_graph_data — structure check ===")
from graph.graph_query import get_graph_data

mock_client3 = mock.MagicMock()
mock_client3.run_query.side_effect = [
    # First call: nodes query
    [
        {"name": "Openai",     "type": "Organization"},
        {"name": "Sam Altman", "type": "Person"},
    ],
    # Second call: edges query
    [
        {"source": "Sam Altman", "target": "Openai", "relation": "CEO_OF"},
    ],
]

with mock.patch.object(Neo4jClient, "get_instance", return_value=mock_client3):
    graph_data = get_graph_data()

assert "nodes" in graph_data,                   "Missing 'nodes' key"
assert "edges" in graph_data,                   "Missing 'edges' key"
assert len(graph_data["nodes"]) == 2,           f"Expected 2 nodes, got {len(graph_data['nodes'])}"
assert len(graph_data["edges"]) == 1,           f"Expected 1 edge, got {len(graph_data['edges'])}"

node = graph_data["nodes"][0]
assert "id"    in node, "Node missing 'id'"
assert "label" in node, "Node missing 'label'"
assert "type"  in node, "Node missing 'type'"

edge = graph_data["edges"][0]
assert "source" in edge, "Edge missing 'source'"
assert "target" in edge, "Edge missing 'target'"
assert "label"  in edge, "Edge missing 'label'"

print(f"  [OK] nodes: {graph_data['nodes']}")
print(f"  [OK] edges: {graph_data['edges']}")

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: get_graph_data — document_id filter passes correct param
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 5: get_graph_data — document_id filter ===")

mock_client4 = mock.MagicMock()
mock_client4.run_query.return_value = []

with mock.patch.object(Neo4jClient, "get_instance", return_value=mock_client4):
    get_graph_data(document_id="doc-001")

# Both calls (nodes + edges) should have passed document_id param
calls = mock_client4.run_query.call_args_list
for call in calls:
    params = call.args[1] if len(call.args) > 1 else call.kwargs.get("params", {})
    assert "document_id" in (params or {}), f"document_id not passed to query: {call}"
print("  [OK] document_id param passed to both node and edge queries")

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: _clean_cypher_response — strips prefixes and fences
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 6: _clean_cypher_response ===")
from graph.cypher_generator import _clean_cypher_response

cases = [
    # (input,                                                expected_contains)
    ("MATCH (n) RETURN n.name",                             "MATCH"),
    ("Cypher: MATCH (n) RETURN n.name",                     "MATCH"),
    ("```cypher\nMATCH (n) RETURN n.name\n```",             "MATCH"),
    ("```\nMATCH (n) RETURN n.name\n```",                   "MATCH"),
    ("Query: MATCH (n) RETURN n.name\nSome explanation",    "MATCH"),
]

for raw, expected_contains in cases:
    result = _clean_cypher_response(raw)
    assert expected_contains in result, f"Expected '{expected_contains}' in '{result}'"
    print(f"  [OK] Cleaned: '{result}'")

# ─────────────────────────────────────────────────────────────────────────────
# Test 7: _looks_like_cypher — basic validation
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 7: _looks_like_cypher ===")
from graph.cypher_generator import _looks_like_cypher

assert _looks_like_cypher("MATCH (n) RETURN n") is True
assert _looks_like_cypher("MATCH (n:Person) WHERE n.name = 'Sam' RETURN n.name") is True
assert _looks_like_cypher("") is False
assert _looks_like_cypher("I cannot answer this question.") is False
assert _looks_like_cypher("MATCH (n)") is False          # no RETURN
assert _looks_like_cypher("SELECT * FROM nodes") is False
print("  [OK] Valid Cypher detected correctly")
print("  [OK] Invalid/empty strings correctly rejected")

# ─────────────────────────────────────────────────────────────────────────────
# Test 8: generate_cypher — happy path (mocked Gemini)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 8: generate_cypher — happy path (mocked) ===")
from graph.cypher_generator import generate_cypher
from llm.gemini_client import GeminiClient

expected_cypher = "MATCH (a)-[:CREATED]->(b) WHERE toLower(b.name) = toLower('GPT-4') RETURN a.name AS creator"

with mock.patch.object(GeminiClient, "get_instance") as mock_get:
    mock_llm = mock.MagicMock()
    mock_llm.generate_text.return_value = expected_cypher
    mock_get.return_value = mock_llm

    result = generate_cypher("Who created GPT-4?")

assert result == expected_cypher, f"Got: {result}"
print(f"  [OK] Generated Cypher: '{result}'")

# ─────────────────────────────────────────────────────────────────────────────
# Test 9: generate_cypher — invalid LLM response → fallback
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 9: generate_cypher — invalid response → fallback ===")

with mock.patch.object(GeminiClient, "get_instance") as mock_get:
    mock_llm = mock.MagicMock()
    mock_llm.generate_text.return_value = "I cannot generate a Cypher query for this."
    mock_get.return_value = mock_llm

    result = generate_cypher("Who created GPT-4?")

# Should fall back to the default query
assert "MATCH" in result and "RETURN" in result, f"Fallback Cypher invalid: {result}"
print(f"  [OK] Fallback Cypher used: '{result}'")

# ─────────────────────────────────────────────────────────────────────────────
# Test 10: generate_cypher — empty question → fallback
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 10: generate_cypher — empty question → fallback ===")
result = generate_cypher("")
assert "MATCH" in result and "RETURN" in result
print(f"  [OK] Empty question returns fallback: '{result}'")

print()
print("=" * 60)
print("All graph tests passed ✓")
