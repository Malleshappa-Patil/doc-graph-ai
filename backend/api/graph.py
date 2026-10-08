"""
api/graph.py
────────────────────────────────────────────────────────────────────────────────
FastAPI router for graph building and graph retrieval endpoints.

ENDPOINTS:
  POST /api/build-graph/{document_id}
      Runs the full ingestion + extraction + graph build pipeline for a
      previously uploaded document. This is the most important endpoint —
      it's where the PDF becomes a knowledge graph.

  GET /api/graph
      Returns the entire knowledge graph (all nodes + edges).
      Used by the Streamlit visualization page.

  GET /api/graph/{document_id}
      Returns the subgraph contributed by a specific document.
      Useful for "show me what THIS document added to the graph".

THE BUILD-GRAPH PIPELINE:
  1. Locate the uploaded PDF:  uploads/{document_id}.pdf
  2. Parse PDF → raw text (PyMuPDF)
  3. Clean text → remove noise (text_cleaner)
  4. Chunk text → overlapping segments (text_cleaner)
  5. For each chunk:
     a. Extract entities  (Gemini → EntityList)
     b. Extract relationships (Gemini → RelationshipList)
  6. Merge all entities across chunks  (deduplicate)
  7. Merge all relationships across chunks (deduplicate)
  8. MERGE nodes + edges into Neo4j (graph_builder)
  9. Return summary: {nodes_merged, relationships_merged, chunks_processed}
────────────────────────────────────────────────────────────────────────────────
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from config import get_settings
from ingestion.pdf_parser import parse_pdf
from ingestion.text_cleaner import clean_text, chunk_text
from extraction.entity_extractor import extract_entities
from extraction.relationship_extractor import extract_relationships
from graph.graph_builder import build_graph
from graph.graph_query import get_graph_data
from schemas.entities import Entity, EntityList
from schemas.relationships import Relationship, RelationshipList

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Graph"])


# ── Response models ────────────────────────────────────────────────────────────

class BuildGraphResponse(BaseModel):
    """
    Response returned after successfully building a knowledge graph.

    Fields:
        document_id (str):         The document that was processed.
        nodes_merged (int):        Number of entity nodes added/updated in Neo4j.
        relationships_merged (int):Number of relationship edges added/updated.
        chunks_processed (int):    Number of text chunks sent to Gemini.
        message (str):             Human-readable summary.
    """
    document_id: str
    nodes_merged: int
    relationships_merged: int
    chunks_processed: int
    message: str


class GraphDataResponse(BaseModel):
    """
    Response containing the full graph for visualization.

    Fields:
        nodes (list[dict]): Each node has: id, label, type.
        edges (list[dict]): Each edge has: source, target, label.
        total_nodes (int):  Total node count.
        total_edges (int):  Total edge count.
    """
    nodes: list[dict]
    edges: list[dict]
    total_nodes: int
    total_edges: int


# ── POST /build-graph/{document_id} ───────────────────────────────────────────

@router.post(
    "/build-graph/{document_id}",
    response_model=BuildGraphResponse,
    summary="Build knowledge graph from an uploaded document",
    description=(
        "Runs the full pipeline: PDF parsing → text cleaning → chunking → "
        "entity extraction → relationship extraction → Neo4j graph building. "
        "Use the document_id returned by POST /upload."
    ),
)
async def build_graph_endpoint(document_id: str) -> BuildGraphResponse:
    """
    Orchestrates the full ingestion + extraction + graph building pipeline.

    Args:
        document_id (str):
            UUID of the uploaded document (from POST /upload).
            The PDF is expected at: uploads/{document_id}.pdf

    Returns:
        BuildGraphResponse with counts of nodes and relationships merged.

    Raises:
        404: If no uploaded file exists for this document_id.
        422: If the PDF has no extractable text (e.g. scanned image).
        500: If the pipeline fails at any step.
    """
    settings = get_settings()
    pdf_path = Path(settings.upload_dir) / f"{document_id}.pdf"

    # ── Step 0: Locate the file ───────────────────────────────────────────────
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No uploaded document found for document_id: '{document_id}'. "
                   f"Please upload the PDF first via POST /upload.",
        )

    logger.info("Starting graph build for document: %s", document_id)

    # ── Step 1: Parse PDF ─────────────────────────────────────────────────────
    try:
        raw_text = parse_pdf(pdf_path)
    except Exception as exc:
        logger.error("PDF parsing failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF parsing failed: {exc}",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No text could be extracted from this PDF. "
                "It may be a scanned image. Only text-based PDFs are supported."
            ),
        )

    # ── Step 2: Clean and chunk ───────────────────────────────────────────────
    cleaned = clean_text(raw_text)
    chunks = chunk_text(cleaned)

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF was parsed but produced no text chunks after cleaning.",
        )

    logger.info(
        "Document %s: %d chars → %d chunk(s)",
        document_id, len(cleaned), len(chunks),
    )

    # ── Steps 3+4: Extract entities and relationships per chunk ───────────────
    all_entities: list[Entity] = []
    all_relationships: list[Relationship] = []

    for i, chunk in enumerate(chunks, start=1):
        logger.info("Processing chunk %d/%d for document %s...", i, len(chunks), document_id)

        # 3a. Extract entities from this chunk
        chunk_entities = extract_entities(chunk)

        # 3b. Extract relationships using this chunk's entities as grounding
        chunk_relationships = extract_relationships(chunk, chunk_entities)

        all_entities.extend(chunk_entities.entities)
        all_relationships.extend(chunk_relationships.relationships)

    # ── Step 5: Merge and deduplicate across all chunks ───────────────────────
    merged_entities = EntityList(entities=all_entities).unique()
    merged_relationships = RelationshipList(relationships=all_relationships).unique()

    logger.info(
        "Document %s: %d unique entities, %d unique relationships across %d chunks",
        document_id,
        len(merged_entities.entities),
        len(merged_relationships.relationships),
        len(chunks),
    )

    # ── Step 6: Write to Neo4j ────────────────────────────────────────────────
    try:
        summary = build_graph(merged_entities, merged_relationships, document_id)
    except Exception as exc:
        logger.error("Graph building failed for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write graph to Neo4j: {exc}",
        ) from exc

    return BuildGraphResponse(
        document_id=document_id,
        nodes_merged=summary["nodes_merged"],
        relationships_merged=summary["relationships_merged"],
        chunks_processed=len(chunks),
        message=(
            f"Knowledge graph built successfully from {len(chunks)} chunk(s). "
            f"{summary['nodes_merged']} entities and "
            f"{summary['relationships_merged']} relationships stored in Neo4j."
        ),
    )


# ── GET /graph ─────────────────────────────────────────────────────────────────

@router.get(
    "/graph",
    response_model=GraphDataResponse,
    summary="Get the full knowledge graph",
    description="Returns all nodes and edges across all documents for visualization.",
)
async def get_full_graph() -> GraphDataResponse:
    """
    Returns the entire knowledge graph — all nodes and edges.

    Used by the Streamlit graph visualization page to render the graph.

    Returns:
        GraphDataResponse with nodes and edges lists, plus totals.

    Raises:
        500: If the Neo4j query fails.
    """
    try:
        data = get_graph_data()
    except Exception as exc:
        logger.error("Failed to retrieve graph data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve graph from Neo4j: {exc}",
        ) from exc

    return GraphDataResponse(
        nodes=data["nodes"],
        edges=data["edges"],
        total_nodes=len(data["nodes"]),
        total_edges=len(data["edges"]),
    )


# ── GET /graph/{document_id} ───────────────────────────────────────────────────

@router.get(
    "/graph/{document_id}",
    response_model=GraphDataResponse,
    summary="Get the knowledge graph for a specific document",
    description=(
        "Returns only the nodes and edges contributed by a specific document. "
        "Useful for reviewing what a single PDF added to the graph."
    ),
)
async def get_document_graph(document_id: str) -> GraphDataResponse:
    """
    Returns the subgraph for a specific uploaded document.

    Filters the graph to only include nodes whose `document_ids` list
    contains the given document_id.

    Args:
        document_id (str): The UUID of the document to filter by.

    Returns:
        GraphDataResponse with filtered nodes and edges.

    Raises:
        500: If the Neo4j query fails.
    """
    try:
        data = get_graph_data(document_id=document_id)
    except Exception as exc:
        logger.error(
            "Failed to retrieve graph for document %s: %s", document_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve graph from Neo4j: {exc}",
        ) from exc

    return GraphDataResponse(
        nodes=data["nodes"],
        edges=data["edges"],
        total_nodes=len(data["nodes"]),
        total_edges=len(data["edges"]),
    )
