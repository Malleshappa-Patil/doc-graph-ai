"""
api/upload.py
────────────────────────────────────────────────────────────────────────────────
FastAPI router for the document upload endpoint.

ENDPOINT:
  POST /api/upload

WHAT IT DOES:
  1. Accepts a PDF file via multipart form upload.
  2. Validates the file is a PDF (by MIME type and extension).
  3. Generates a UUID as the document_id.
  4. Saves the file as `{upload_dir}/{document_id}.pdf`.
  5. Returns the document_id so the client can trigger graph building.

WHY UUID FOR DOCUMENT ID?
  A UUID is:
    - Globally unique — no collision risk even across restarts.
    - Opaque — doesn't leak file path or name info to the client.
    - Used as the filename on disk and as the foreign key in Neo4j
      (stored in node.document_ids lists).

FILE NAMING CONVENTION:
  Uploaded files are stored as: uploads/{uuid}.pdf
  The original filename is NOT used for storage because:
    - It may contain spaces, unicode, or path-traversal characters.
    - Two users could upload a file with the same name.
  The original name is preserved in the response for display purposes.

RESPONSE:
  {
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "filename":    "openai_report.pdf",
    "message":     "File uploaded successfully. Use document_id to build the graph."
  }
────────────────────────────────────────────────────────────────────────────────
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from config import get_settings

logger = logging.getLogger(__name__)

# APIRouter is FastAPI's way of grouping related endpoints.
# Think of it like a Flask Blueprint.
# All routes defined here are registered with a prefix in main.py.
router = APIRouter(tags=["Upload"])


# ── Response model ─────────────────────────────────────────────────────────────
class UploadResponse(BaseModel):
    """
    Response returned after a successful file upload.

    Fields:
        document_id (str): UUID identifying this document.
                           Use this in POST /build-graph/{document_id}.
        filename (str):    The original filename (for display only).
        message (str):     Human-readable success message.
    """
    document_id: str
    filename: str
    message: str


# ── Constants ──────────────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".pdf"}
ALLOWED_MIME_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF document",
    description=(
        "Uploads a PDF file and saves it for knowledge graph extraction. "
        "Returns a document_id to use with POST /build-graph/{document_id}."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="PDF file to upload"),
) -> UploadResponse:
    """
    Upload a PDF document.

    - Validates the file is a PDF (extension + content-type).
    - Saves it to the configured upload directory.
    - Returns a unique document_id for subsequent graph building.

    Args:
        file (UploadFile):
            FastAPI's UploadFile wraps the multipart upload.
            Provides:
              - file.filename  → original filename from the client
              - file.content_type → MIME type declared by the client
              - await file.read() → full file bytes

    Raises:
        400 Bad Request: If the file is not a PDF or exceeds size limit.
        500 Internal Server Error: If saving the file fails.
    """
    settings = get_settings()

    # ── Validate: file extension ──────────────────────────────────────────────
    original_name = file.filename or "unknown.pdf"
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PDF files are supported. Got: '{extension}'",
        )

    # ── Validate: MIME type ───────────────────────────────────────────────────
    # content_type is what the client declared — not fully trustworthy,
    # but a useful first filter alongside the extension check.
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid content type: '{file.content_type}'. Expected 'application/pdf'.",
        )

    # ── Read file content ─────────────────────────────────────────────────────
    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read uploaded file.",
        ) from exc

    # ── Validate: file size ───────────────────────────────────────────────────
    file_size_bytes = len(content)
    if file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File too large: {file_size_bytes / 1024 / 1024:.1f} MB. "
                f"Maximum allowed: {MAX_FILE_SIZE_MB} MB."
            ),
        )

    # ── Validate: basic PDF magic bytes ──────────────────────────────────────
    # A real PDF starts with the bytes: %PDF
    # This is a stronger check than the extension or MIME type.
    if not content.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not appear to be a valid PDF (missing PDF header).",
        )

    # ── Generate document_id and save ─────────────────────────────────────────
    document_id = str(uuid.uuid4())
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    save_path = upload_dir / f"{document_id}.pdf"

    try:
        save_path.write_bytes(content)
        logger.info(
            "File saved: %s → %s (%d bytes)",
            original_name, save_path, file_size_bytes,
        )
    except Exception as exc:
        logger.error("Failed to save file to %s: %s", save_path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file.",
        ) from exc

    return UploadResponse(
        document_id=document_id,
        filename=original_name,
        message=(
            f"File uploaded successfully ({file_size_bytes / 1024:.1f} KB). "
            f"Use document_id to build the knowledge graph."
        ),
    )
