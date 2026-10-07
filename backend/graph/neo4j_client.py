"""
graph/neo4j_client.py
────────────────────────────────────────────────────────────────────────────────
Manages the Neo4j database driver — the single entry point for all database
operations in this application.

HOW THE NEO4J PYTHON DRIVER WORKS:
  The official `neo4j` Python driver uses a two-level abstraction:

  1. Driver  — the top-level object. Created ONCE, lives for the app lifetime.
               Manages a connection pool internally. Think of it like a
               database engine object — expensive to create, reuse it.

  2. Session — a short-lived unit of work. Opened per operation, closed
               immediately after. Think of it like a database cursor.
               Sessions are cheap — create/close them freely.

  Usage pattern:
      driver = GraphDatabase.driver(uri, auth=(user, password))

      with driver.session(database="neo4j") as session:
          result = session.run("MATCH (n) RETURN n LIMIT 5")
          records = [dict(record) for record in result]

      driver.close()  # at app shutdown

SINGLETON PATTERN:
  We use the same lazy singleton pattern as GeminiClient.
  One driver for the entire app lifetime → efficient connection pooling.

CONNECTION POOLING:
  The Neo4j driver manages a pool of TCP connections internally.
  Default pool size is 100 connections. Each session.run() borrows a
  connection from the pool and returns it when done.
  No manual connection management needed.

DESIGN DECISIONS:
  - verify_connectivity() called in __init__ → fail fast at startup
    if Neo4j is unreachable, rather than failing on first query.
  - All Cypher execution goes through the session context manager
    (with driver.session()) → guarantees session is always closed.
────────────────────────────────────────────────────────────────────────────────
"""

import logging

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError

from config import get_settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """
    Singleton wrapper around the Neo4j Python driver.

    USAGE:
        client = Neo4jClient.get_instance()

        # Run a read query
        results = client.run_query("MATCH (n) RETURN n.name LIMIT 5")

        # Run a write query (MERGE, CREATE)
        client.run_query("MERGE (n:Person {name: $name})", {"name": "Sam"})

        # Health check
        is_ok = client.health_check()
    """

    _instance: "Neo4jClient | None" = None

    def __init__(self) -> None:
        """
        Creates and verifies the Neo4j driver connection.
        Called only ONCE by get_instance().

        Raises:
            AuthError:            If username/password is wrong.
            ServiceUnavailable:   If Neo4j is not running or unreachable.
        """
        settings = get_settings()

        logger.info("Connecting to Neo4j at: %s", settings.neo4j_uri)

        # GraphDatabase.driver() creates the driver with connection pool.
        # auth= takes a tuple of (username, password).
        self._driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            # max_connection_pool_size: max simultaneous DB connections.
            # 50 is more than enough for a single-app setup.
            max_connection_pool_size=50,
        )

        # verify_connectivity() sends a test packet to Neo4j to confirm
        # the connection works. Raises ServiceUnavailable if it can't reach it.
        # WHY: Fail fast at startup instead of failing on the first query.
        try:
            self._driver.verify_connectivity()
            logger.info("Neo4j connection verified successfully.")
        except (ServiceUnavailable, AuthError) as exc:
            self._driver.close()
            raise exc

    @classmethod
    def get_instance(cls) -> "Neo4jClient":
        """
        Returns the shared Neo4jClient instance, creating it on first call.

        Always use this — do NOT call Neo4jClient() directly.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def run_query(
        self,
        cypher: str,
        params: dict | None = None,
        database: str = "neo4j",
    ) -> list[dict]:
        """
        Executes a Cypher query and returns the results as a list of dicts.

        This is the single method for ALL database operations — both reads
        (MATCH) and writes (MERGE, CREATE, DELETE).

        Args:
            cypher (str):
                The Cypher query string. Can contain parameter placeholders
                with $ prefix, e.g. "MERGE (n:Person {name: $name})".

            params (dict | None):
                Query parameters. Matched to $placeholder names in the query.
                Example: {"name": "Sam Altman", "type": "Person"}
                DEFAULT: None (treated as empty dict internally).

                WHY PARAMETERS (not f-strings)?
                  Using f-strings to insert values is a Cypher injection risk.
                  Parameters are escaped and handled safely by the driver.
                  Always use params, never string formatting for user data.

            database (str):
                Neo4j database name. Default is "neo4j" (the default DB).
                Change this if you use multiple databases.

        Returns:
            list[dict]:
                Each dict is one result row, with column names as keys.
                Example: [{"n.name": "OpenAI", "n.type": "Organization"}]
                Returns [] if the query matched nothing.

        Raises:
            neo4j.exceptions.CypherSyntaxError: If the Cypher is invalid.
            neo4j.exceptions.ServiceUnavailable: If the DB goes offline.

        Example:
            results = client.run_query(
                "MATCH (n:Person {name: $name}) RETURN n.name",
                {"name": "Sam Altman"}
            )
            # → [{"n.name": "Sam Altman"}]
        """
        if params is None:
            params = {}

        logger.debug("Executing Cypher: %s | Params: %s", cypher[:200], params)

        # The `with` block opens a session and guarantees it's closed
        # even if an exception occurs.
        with self._driver.session(database=database) as session:
            result = session.run(cypher, params)

            # result is a lazy cursor — we eagerly convert to dicts here
            # while the session is still open (session closes on __exit__).
            # After the `with` block closes, the cursor is invalid.
            records = [dict(record) for record in result]

        logger.debug("Query returned %d record(s)", len(records))
        return records

    def health_check(self) -> bool:
        """
        Returns True if Neo4j is reachable and responding, False otherwise.

        Used by the GET /health API endpoint to report service status.

        Returns:
            bool: True if connection is healthy, False otherwise.
        """
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("Neo4j health check failed: %s", exc)
            return False

    def close(self) -> None:
        """
        Closes the driver and releases all connection pool resources.

        Call this at application shutdown (e.g. FastAPI lifespan shutdown event).
        Not calling this may cause connection pool warnings in logs.
        """
        logger.info("Closing Neo4j driver.")
        self._driver.close()
        Neo4jClient._instance = None
