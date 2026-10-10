"""
main.py
────────────────────────────────────────────────────────────────────────────────
FastAPI application entry point.

THIS FILE IS RESPONSIBLE FOR:
  1. Creating the FastAPI app instance with metadata (title, version, docs URL).
  2. Configuring CORS so the Streamlit frontend can call the API.
  3. Setting up structured logging for the entire backend.
  4. Registering a lifespan handler (startup + shutdown events).
  5. Including all API routers (upload, graph, chat).
  6. Exposing the GET /health endpoint.

HOW FASTAPI STARTS:
  You run the app with uvicorn:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

  uvicorn → loads main.py → calls `create_application()` → returns `app`
  → starts the ASGI server → listens for HTTP requests

LIFESPAN (startup / shutdown):
  FastAPI uses a context manager (`@asynccontextmanager`) to run code at
  startup and shutdown. This replaces the older `@app.on_event("startup")`
  decorator pattern.

  At STARTUP:
    - Ensures the uploads/ directory exists.
    - Verifies the Neo4j connection (fail fast if unreachable).

  At SHUTDOWN:
    - Gracefully closes the Neo4j driver and its connection pool.

CORS (Cross-Origin Resource Sharing):
  The Streamlit frontend runs on http://localhost:8501.
  The FastAPI backend runs on http://localhost:8000.
  These are different origins → the browser blocks requests by default.
  We add CORSMiddleware to allow the frontend to call the API.

FOLDER STRUCTURE REMINDER:
  backend/
  ├── api/
  │   ├── upload.py       → POST /api/upload
  │   ├── graph.py        → POST /api/build-graph, GET /api/graph
  │   └── chat.py         → POST /api/chat
  ├── ingestion/          → pdf_parser, text_cleaner
  ├── extraction/         → entity_extractor, relationship_extractor
  ├── graph/              → neo4j_client, graph_builder, graph_query, cypher_generator
  ├── llm/                → gemini_client, answer_generator
  ├── schemas/            → entities, relationships
  ├── config.py           → pydantic settings
  └── main.py             ← THIS FILE
────────────────────────────────────────────────────────────────────────────────
"""

import logging
import logging.config
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings


# ── Logging setup ──────────────────────────────────────────────────────────────
# Configure structured logging BEFORE importing anything else that logs.
# This ensures all loggers (including from libraries) respect our format.
def configure_logging(log_level: str = "INFO") -> None:
    """
    Configures application-wide logging.

    Format: timestamp | level | module:line | message

    All loggers in this codebase use `logging.getLogger(__name__)`, so
    they inherit this root configuration automatically.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR. Default INFO.
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),  # print to console
        ],
        force=True,  # override any existing handlers (e.g. from imported libs)
    )

    # Silence noisy third-party loggers
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ── Lifespan handler ───────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager — runs startup and shutdown logic.

    STARTUP (code before `yield`):
      1. Configure logging.
      2. Ensure the uploads/ directory exists.
      3. Verify Neo4j connectivity (fail fast).

    SHUTDOWN (code after `yield`):
      4. Close the Neo4j driver cleanly.

    The `yield` is where FastAPI serves requests — it pauses here while
    the app is running, then resumes after shutdown is triggered.
    """
    # ── STARTUP ───────────────────────────────────────────────────────────────
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("=" * 60)
    logger.info("Starting Doc-Graph-AI backend...")
    logger.info("Environment : %s", settings.app_env)
    logger.info("Gemini model: %s", settings.gemini_model)
    logger.info("Neo4j URI   : %s", settings.neo4j_uri)
    logger.info("=" * 60)

    # Ensure uploads directory exists
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Uploads directory ready: %s", upload_dir.resolve())

    # Verify Neo4j connection at startup
    # WHY: Better to fail here with a clear message than to fail
    # silently on the first request minutes later.
    try:
        from graph.neo4j_client import Neo4jClient
        client = Neo4jClient.get_instance()
        if client.health_check():
            logger.info("Neo4j connection verified.")
        else:
            logger.warning(
                "Neo4j health check returned False. "
                "Graph operations may fail. Check NEO4J_URI and credentials."
            )
    except Exception as exc:
        logger.error(
            "Could not connect to Neo4j at startup: %s\n"
            "Ensure Neo4j is running and NEO4J_URI/credentials are correct.\n"
            "The app will start, but /build-graph and /chat will fail.",
            exc,
        )

    logger.info("Backend startup complete. Listening for requests...")

    # ── Hand control to FastAPI (serve requests) ───────────────────────────────
    yield

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    logger.info("Shutting down Doc-Graph-AI backend...")

    try:
        from graph.neo4j_client import Neo4jClient
        if Neo4jClient._instance is not None:
            Neo4jClient._instance.close()
            logger.info("Neo4j driver closed.")
    except Exception as exc:
        logger.warning("Error closing Neo4j driver: %s", exc)

    logger.info("Shutdown complete.")


# ── App factory ────────────────────────────────────────────────────────────────
def create_application() -> FastAPI:
    """
    Creates and configures the FastAPI application.

    Returns:
        FastAPI: The fully configured application instance.

    WHY A FACTORY FUNCTION?
      Instead of creating `app = FastAPI()` at module level, we use a factory.
      Benefits:
        - Easier to test (can create fresh app instances in tests).
        - Keeps module-level code minimal (no side effects on import).
        - Standard pattern for production FastAPI apps.
    """
    settings = get_settings()

    app = FastAPI(
        title="Doc-Graph-AI API",
        description=(
            "A Knowledge Graph application that extracts entities and relationships "
            "from PDF documents and answers natural language questions using Neo4j and Gemini."
        ),
        version="1.0.0",
        # Swagger UI at /docs — useful during development
        docs_url="/docs",
        # ReDoc at /redoc — alternative API docs UI
        redoc_url="/redoc",
        # OpenAPI schema at /openapi.json
        openapi_url="/openapi.json",
        # Wire up startup/shutdown events
        lifespan=lifespan,
    )

    # ── CORS Middleware ────────────────────────────────────────────────────────
    # Allow the Streamlit frontend (port 8501) to call this API (port 8000).
    # In development, we allow all origins. In production, restrict this.
    #
    # allow_origins=["*"]                  → allow any origin (dev-friendly)
    # allow_methods=["*"]                  → allow GET, POST, PUT, DELETE, etc.
    # allow_headers=["*"]                  → allow all request headers
    # allow_credentials=True               → allow cookies/auth headers
    origins = (
        ["*"]
        if settings.app_env == "development"
        else [
            "http://localhost:8501",          # Streamlit local
            "http://frontend:8501",           # Streamlit in Docker
        ]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Register API routers ───────────────────────────────────────────────────
    # Each router is defined in api/upload.py, api/graph.py, api/chat.py.
    # prefix="/api" means all endpoints are under /api/...
    # e.g. POST /api/upload, POST /api/build-graph/{id}, POST /api/chat
    from api import upload, graph, chat

    app.include_router(upload.router, prefix="/api")
    app.include_router(graph.router,  prefix="/api")
    app.include_router(chat.router,   prefix="/api")

    # ── Health check endpoint ──────────────────────────────────────────────────
    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        description="Returns the status of the API and Neo4j connection.",
    )
    async def health_check() -> JSONResponse:
        """
        Health check endpoint.

        Returns:
            200: {"status": "ok", "neo4j": true/false}

        This is called by Docker health checks, load balancers, and
        monitoring tools to verify the service is running.
        """
        from graph.neo4j_client import Neo4jClient

        neo4j_ok = False
        try:
            neo4j_ok = Neo4jClient.get_instance().health_check()
        except Exception:
            pass

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "neo4j": neo4j_ok,
                "version": "1.0.0",
            },
        )

    # ── Root endpoint ──────────────────────────────────────────────────────────
    @app.get("/", tags=["Health"], summary="API root")
    async def root() -> dict:
        """Returns a welcome message and links to the API docs."""
        return {
            "message": "Doc-Graph-AI API",
            "docs":    "/docs",
            "health":  "/health",
        }

    return app


# ── Application instance ───────────────────────────────────────────────────────
# This is the object uvicorn imports when you run:
#   uvicorn main:app --reload
#
# We call create_application() here so `app` is available at module level.
app = create_application()
