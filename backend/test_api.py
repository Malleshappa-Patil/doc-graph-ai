"""
test_api.py
────────────────────────────────────────────────────────────────────────────────
Tests for api/upload.py, api/graph.py, api/chat.py.
Uses FastAPI TestClient — no real Neo4j, Gemini, or file system needed.
────────────────────────────────────────────────────────────────────────────────
"""
import sys
import io
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, ".")

# We need to set dummy env vars before importing anything that reads settings
import os
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("NEO4J_PASSWORD", "test-pass")

from fastapi.testclient import TestClient

# ── Build a minimal FastAPI app for testing ───────────────────────────────────
# We don't import main.py (which would try to connect to Neo4j at startup).
# Instead we build a minimal app that includes only the routers we're testing.
from fastapi import FastAPI
from api import upload, graph, chat

test_app = FastAPI()
test_app.include_router(upload.router, prefix="/api")
test_app.include_router(graph.router,  prefix="/api")
test_app.include_router(chat.router,   prefix="/api")

client = TestClient(test_app)

# ─────────────────────────────────────────────────────────────────────────────
# ── UPLOAD TESTS ──────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

print("=== Test 1: POST /upload — valid PDF ===")

# Create a minimal valid PDF in memory (starts with %PDF)
FAKE_PDF_CONTENT = b"%PDF-1.4 fake pdf content for testing"

with mock.patch("api.upload.get_settings") as mock_cfg, \
     mock.patch("pathlib.Path.mkdir"), \
     mock.patch("pathlib.Path.write_bytes"):

    mock_cfg.return_value = mock.MagicMock(upload_dir="./uploads")

    response = client.post(
        "/api/upload",
        files={"file": ("test_report.pdf", io.BytesIO(FAKE_PDF_CONTENT), "application/pdf")},
    )

assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
body = response.json()
assert "document_id" in body,     "Missing document_id"
assert "filename"    in body,     "Missing filename"
assert body["filename"] == "test_report.pdf"
assert len(body["document_id"]) == 36   # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
print(f"  [OK] Status 201, document_id: {body['document_id']}")
print(f"  [OK] Filename preserved: {body['filename']}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 2: POST /upload — not a PDF (wrong extension) ===")

response = client.post(
    "/api/upload",
    files={"file": ("report.docx", io.BytesIO(b"fake docx content"), "application/msword")},
)
assert response.status_code == 400, f"Expected 400, got {response.status_code}"
assert "PDF" in response.json()["detail"]
print(f"  [OK] 400 returned for .docx file: {response.json()['detail']}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 3: POST /upload — file without PDF header ===")

with mock.patch("api.upload.get_settings") as mock_cfg:
    mock_cfg.return_value = mock.MagicMock(upload_dir="./uploads")

    response = client.post(
        "/api/upload",
        files={"file": ("fake.pdf", io.BytesIO(b"This is not a PDF"), "application/pdf")},
    )

assert response.status_code == 400, f"Expected 400, got {response.status_code}"
assert "valid PDF" in response.json()["detail"] or "PDF header" in response.json()["detail"]
print(f"  [OK] 400 returned for file without %PDF header")

# ─────────────────────────────────────────────────────────────────────────────
# ── GRAPH TESTS ───────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

print()
print("=== Test 4: POST /build-graph — 404 when file not found ===")

response = client.post("/api/build-graph/nonexistent-doc-id")
assert response.status_code == 404, f"Expected 404, got {response.status_code}"
assert "nonexistent-doc-id" in response.json()["detail"]
print(f"  [OK] 404 for missing document_id")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 5: POST /build-graph — successful pipeline (mocked) ===")

from schemas.entities import EntityList, Entity
from schemas.relationships import RelationshipList, Relationship

# Fake PDF path exists
with mock.patch("pathlib.Path.exists", return_value=True), \
     mock.patch("api.graph.parse_pdf", return_value="OpenAI created GPT-4. Sam Altman is CEO."), \
     mock.patch("api.graph.clean_text", side_effect=lambda t: t), \
     mock.patch("api.graph.chunk_text", return_value=["OpenAI created GPT-4. Sam Altman is CEO."]), \
     mock.patch("api.graph.extract_entities", return_value=EntityList(entities=[
         Entity(name="Openai",     type="Organization"),
         Entity(name="Gpt-4",      type="Product"),
         Entity(name="Sam Altman", type="Person"),
     ])), \
     mock.patch("api.graph.extract_relationships", return_value=RelationshipList(relationships=[
         Relationship(source="Openai",     target="Gpt-4",  relation="CREATED"),
         Relationship(source="Sam Altman", target="Openai", relation="CEO_OF"),
     ])), \
     mock.patch("api.graph.build_graph", return_value={
         "nodes_merged": 3, "relationships_merged": 2
     }):

    response = client.post("/api/build-graph/doc-001")

assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
body = response.json()
assert body["document_id"]          == "doc-001"
assert body["nodes_merged"]         == 3
assert body["relationships_merged"] == 2
assert body["chunks_processed"]     == 1
print(f"  [OK] Build graph response: {body}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 6: POST /build-graph — 422 for empty PDF ===")

with mock.patch("pathlib.Path.exists", return_value=True), \
     mock.patch("api.graph.parse_pdf", return_value="   "):

    response = client.post("/api/build-graph/doc-empty")

assert response.status_code == 422, f"Expected 422, got {response.status_code}"
assert "No text" in response.json()["detail"] or "scanned" in response.json()["detail"]
print(f"  [OK] 422 for empty/scanned PDF")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 7: GET /graph — returns nodes and edges ===")

with mock.patch("api.graph.get_graph_data", return_value={
    "nodes": [
        {"id": "Openai",     "label": "Openai",     "type": "Organization"},
        {"id": "Sam Altman", "label": "Sam Altman", "type": "Person"},
    ],
    "edges": [
        {"source": "Sam Altman", "target": "Openai", "label": "CEO_OF"},
    ],
}):
    response = client.get("/api/graph")

assert response.status_code == 200, f"Expected 200, got {response.status_code}"
body = response.json()
assert body["total_nodes"] == 2
assert body["total_edges"] == 1
assert len(body["nodes"])  == 2
assert len(body["edges"])  == 1
print(f"  [OK] GET /graph returned {body['total_nodes']} nodes, {body['total_edges']} edges")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 8: GET /graph/{document_id} — filtered graph ===")

with mock.patch("api.graph.get_graph_data", return_value={
    "nodes": [{"id": "Openai", "label": "Openai", "type": "Organization"}],
    "edges": [],
}) as mock_gd:
    response = client.get("/api/graph/doc-001")

assert response.status_code == 200
body = response.json()
assert body["total_nodes"] == 1
assert body["total_edges"] == 0
# Confirm document_id was passed to get_graph_data
mock_gd.assert_called_once_with(document_id="doc-001")
print(f"  [OK] Filtered graph for doc-001: {body['total_nodes']} node(s)")

# ─────────────────────────────────────────────────────────────────────────────
# ── CHAT TESTS ────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

print()
print("=== Test 9: POST /chat — successful Q&A (mocked) ===")

with mock.patch("api.chat.generate_cypher",
                return_value="MATCH (a)-[:CREATED]->(b) RETURN a.name AS creator"), \
     mock.patch("api.chat.execute_cypher",
                return_value=[{"creator": "Openai"}]), \
     mock.patch("api.chat.generate_answer",
                return_value="GPT-4 was created by OpenAI."):

    response = client.post(
        "/api/chat",
        json={"question": "Who created GPT-4?"},
    )

assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
body = response.json()
assert body["answer"]           == "GPT-4 was created by OpenAI."
assert "MATCH" in body["cypher"]
assert body["graph_results"]    == [{"creator": "Openai"}]
assert body["question"]         == "Who created GPT-4?"
print(f"  [OK] Answer: '{body['answer']}'")
print(f"  [OK] Cypher: '{body['cypher']}'")
print(f"  [OK] Graph results: {body['graph_results']}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 10: POST /chat — question too short → 422 ===")

response = client.post("/api/chat", json={"question": "Hi"})
assert response.status_code == 422, f"Expected 422 (validation), got {response.status_code}"
print(f"  [OK] Short question rejected with 422 (Pydantic min_length=3 enforced)")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 11: POST /chat — Gemini failure → 500 ===")

with mock.patch("api.chat.generate_cypher",
                side_effect=RuntimeError("Gemini API unavailable")):
    response = client.post("/api/chat", json={"question": "Who created GPT-4?"})

assert response.status_code == 500, f"Expected 500, got {response.status_code}"
assert "Cypher" in response.json()["detail"] or "Failed" in response.json()["detail"]
print(f"  [OK] 500 returned on Gemini failure: {response.json()['detail']}")

print()
print("=" * 60)
print("All API tests passed ✓")
