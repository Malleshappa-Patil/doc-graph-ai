"""
utils/api_client.py
────────────────────────────────────────────────────────────────────────────────
Centralised HTTP client for all calls to the FastAPI backend.

WHY A SEPARATE FILE FOR API CALLS?
  All pages (Upload, Graph, Chat) need to call the backend.
  Keeping calls here means:
    - One place to change the base URL
    - Consistent error handling and response parsing
    - Pages stay clean (just call functions, don't build URLs)
────────────────────────────────────────────────────────────────────────────────
"""

import requests

# ── Base URL ──────────────────────────────────────────────────────────────────
# The FastAPI backend runs on port 8000 by default.
# Change this if you deploy to a different host.
API_BASE = "http://localhost:8000/api"
BASE     = "http://localhost:8000"

# ── Request timeout (seconds) ─────────────────────────────────────────────────
# Build-graph can take 30-60s for large PDFs (multiple Gemini calls).
UPLOAD_TIMEOUT      = 30
BUILD_GRAPH_TIMEOUT = 300   # 5 min — large docs with many chunks
CHAT_TIMEOUT        = 60
DEFAULT_TIMEOUT     = 15


def health_check() -> dict:
    """GET /health — check if backend + Neo4j are alive."""
    try:
        r = requests.get(f"{BASE}/health", timeout=DEFAULT_TIMEOUT)
        return r.json()
    except Exception as exc:
        return {"status": "error", "neo4j": False, "error": str(exc)}


def upload_pdf(file_bytes: bytes, filename: str) -> dict:
    """
    POST /api/upload — upload a PDF file.

    Args:
        file_bytes: Raw bytes of the PDF file.
        filename:   Original filename (e.g. "report.pdf").

    Returns:
        {"document_id": "...", "filename": "...", "message": "..."}
        or {"error": "..."} on failure.
    """
    try:
        r = requests.post(
            f"{API_BASE}/upload",
            files={"file": (filename, file_bytes, "application/pdf")},
            timeout=UPLOAD_TIMEOUT,
        )
        if r.ok:
            return r.json()
        return {"error": r.json().get("detail", r.text)}
    except Exception as exc:
        return {"error": str(exc)}


def build_graph(document_id: str) -> dict:
    """
    POST /api/build-graph/{document_id}
    Triggers the full ingestion + extraction + graph build pipeline.

    Returns:
        {"nodes_merged": N, "relationships_merged": M, ...}
        or {"error": "..."} on failure.
    """
    try:
        r = requests.post(
            f"{API_BASE}/build-graph/{document_id}",
            timeout=BUILD_GRAPH_TIMEOUT,
        )
        if r.ok:
            return r.json()
        return {"error": r.json().get("detail", r.text)}
    except Exception as exc:
        return {"error": str(exc)}


def get_graph(document_id: str | None = None) -> dict:
    """
    GET /api/graph or GET /api/graph/{document_id}

    Returns:
        {"nodes": [...], "edges": [...], "total_nodes": N, "total_edges": M}
        or {"error": "..."} on failure.
    """
    try:
        url = f"{API_BASE}/graph/{document_id}" if document_id else f"{API_BASE}/graph"
        r = requests.get(url, timeout=DEFAULT_TIMEOUT)
        if r.ok:
            return r.json()
        return {"error": r.json().get("detail", r.text)}
    except Exception as exc:
        return {"error": str(exc)}


def chat(question: str) -> dict:
    """
    POST /api/chat — ask a natural language question.

    Returns:
        {"answer": "...", "cypher": "...", "graph_results": [...], "question": "..."}
        or {"error": "..."} on failure.
    """
    try:
        r = requests.post(
            f"{API_BASE}/chat",
            json={"question": question},
            timeout=CHAT_TIMEOUT,
        )
        if r.ok:
            return r.json()
        return {"error": r.json().get("detail", r.text)}
    except Exception as exc:
        return {"error": str(exc)}
