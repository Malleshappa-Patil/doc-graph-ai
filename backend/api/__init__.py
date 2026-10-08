# This file marks api/ as a Python package.
# Each module defines a FastAPI APIRouter that is included in main.py.
#
# Usage in main.py:
#   from api import upload, graph, chat
#   app.include_router(upload.router, prefix="/api")
#   app.include_router(graph.router,  prefix="/api")
#   app.include_router(chat.router,   prefix="/api")
