"""
test_main.py
────────────────────────────────────────────────────────────────────────────────
Smoke tests for main.py — verifies app creation, route registration,
and root/health endpoints without starting Neo4j or Gemini.
────────────────────────────────────────────────────────────────────────────────
"""
import sys
import os
import unittest.mock as mock

sys.path.insert(0, ".")

# Set dummy env vars before any settings are loaded
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("NEO4J_PASSWORD", "test-pass")

# Mock Neo4j driver so the lifespan startup doesn't fail
with mock.patch("neo4j.GraphDatabase.driver") as mock_driver:
    mock_driver.return_value.verify_connectivity.return_value = None
    mock_driver.return_value.session.return_value.__enter__ = mock.MagicMock()
    mock_driver.return_value.session.return_value.__exit__ = mock.MagicMock(return_value=False)

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app, raise_server_exceptions=True)

# ─────────────────────────────────────────────────────────────────────────────
print("=== Test 1: GET / — root endpoint ===")
response = client.get("/")
assert response.status_code == 200, f"Expected 200, got {response.status_code}"
body = response.json()
assert "message" in body,   "Missing 'message'"
assert "docs"    in body,   "Missing 'docs'"
assert "health"  in body,   "Missing 'health'"
print(f"  [OK] Root: {body}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 2: GET /health — health endpoint ===")

with mock.patch("graph.neo4j_client.Neo4jClient.get_instance") as mock_get:
    mock_client = mock.MagicMock()
    mock_client.health_check.return_value = True
    mock_get.return_value = mock_client

    response = client.get("/health")

assert response.status_code == 200, f"Expected 200, got {response.status_code}"
body = response.json()
assert body["status"]  == "ok",   f"Expected 'ok', got: {body}"
assert "neo4j"         in body,   "Missing 'neo4j' key"
assert "version"       in body,   "Missing 'version' key"
print(f"  [OK] Health: {body}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 3: All expected routes are registered ===")

# The most reliable way to check registered routes is via the OpenAPI schema,
# which FastAPI generates from ALL registered routes including nested routers.
schema_response = client.get("/openapi.json")
assert schema_response.status_code == 200
registered_paths = set(schema_response.json()["paths"].keys())

expected_routes = [
    "/api/upload",
    "/api/build-graph/{document_id}",
    "/api/graph",
    "/api/graph/{document_id}",
    "/api/chat",
]

for route in expected_routes:
    assert route in registered_paths, (
        f"Missing route: '{route}' | Found in schema: {sorted(registered_paths)}"
    )
    print(f"  [OK] Route registered: {route}")

# Also verify root and health exist (they're not in OpenAPI by default but we can GET them)
for path in ["/", "/health"]:
    r = client.get(path)
    assert r.status_code == 200, f"Route {path} returned {r.status_code}"
    print(f"  [OK] Route accessible: {path}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 4: GET /docs — Swagger UI accessible ===")
response = client.get("/docs")
assert response.status_code == 200, f"Expected 200, got {response.status_code}"
print(f"  [OK] Swagger UI available at /docs")

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=== Test 5: GET /openapi.json — schema is valid ===")
response = client.get("/openapi.json")
assert response.status_code == 200
schema = response.json()
assert schema["info"]["title"] == "Doc-Graph-AI API"
assert schema["info"]["version"] == "1.0.0"
assert "/api/upload" in str(schema["paths"])
assert "/api/chat"   in str(schema["paths"])
print(f"  [OK] OpenAPI schema valid: title='{schema['info']['title']}', version='{schema['info']['version']}'")
print(f"  [OK] Endpoints in schema: {list(schema['paths'].keys())}")

print()
print("=" * 60)
print("All main.py tests passed ✓")
