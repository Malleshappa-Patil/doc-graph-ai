"""
graph/graph_builder.py
────────────────────────────────────────────────────────────────────────────────
Stores extracted entities and relationships into Neo4j as a knowledge graph.

THE KEY PATTERN — MERGE (not CREATE):
  In Neo4j, there are two ways to add data:
    CREATE  → Always creates a new node/relationship, even if it already exists.
    MERGE   → Creates only if it doesn't exist; matches if it does.

  We ALWAYS use MERGE. WHY:
    - The same entity ("OpenAI") may appear in multiple chunks of a document.
    - The same entity may appear across multiple uploaded documents.
    - MERGE ensures "OpenAI" is always ONE node in the graph — not duplicates.

  MERGE matching criteria:
    - For nodes:         MERGE (n:Label {name: $name})
                         Matches on BOTH label AND name property.
    - For relationships: MERGE (a)-[:RELATION_TYPE]->(b)
                         Matches on both endpoints AND relationship type.

LABEL SAFETY:
  Node labels in Cypher can't be parameterized (unlike property values).
  You can't write: MERGE (n:$label {name: $name})  ← INVALID Cypher

  Instead we build the label into the query string. This creates an injection
  risk if the label comes from user/LLM input. We mitigate this with
  `_sanitize_label()` which allows only alphanumeric + underscore characters.

DOCUMENT TRACKING:
  Each node gets a `document_ids` property — a list of document IDs that
  mentioned this entity. This lets us:
    - Know which documents contributed to the graph
    - Filter the graph view by document (GET /graph/{document_id})
────────────────────────────────────────────────────────────────────────────────
"""

import logging
import re

from graph.neo4j_client import Neo4jClient
from schemas.entities import EntityList
from schemas.relationships import RelationshipList

logger = logging.getLogger(__name__)

# Allowed characters in a Neo4j label. Everything else is stripped.
_LABEL_PATTERN = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_label(label: str) -> str:
    """
    Sanitizes a Neo4j node label to prevent Cypher injection.

    Neo4j labels are inserted directly into the Cypher string (they can't
    be parameterized). We must ensure they contain only safe characters.

    Rules:
      - Keep alphanumeric characters and underscores.
      - Replace spaces with underscores ("Concept Map" → "Concept_Map").
      - Strip all other characters.
      - Default to "Entity" if the result is empty.

    Args:
        label (str): Raw label string from Gemini (e.g. "Organization", "CEO").

    Returns:
        str: A safe Neo4j label string.

    Examples:
        _sanitize_label("Organization")   → "Organization"
        _sanitize_label("Software Tool")  → "Software_Tool"
        _sanitize_label("CEO & Founder")  → "CEO_Founder"
        _sanitize_label("!!!")            → "Entity"
    """
    # Replace spaces with underscores first
    safe = label.strip().replace(" ", "_")
    # Remove all non-alphanumeric, non-underscore characters
    safe = _LABEL_PATTERN.sub("", safe)
    # Collapse multiple consecutive underscores into one
    safe = re.sub(r"_+", "_", safe).strip("_")
    # Fall back to generic label if nothing remains
    return safe if safe else "Entity"


def build_graph(
    entities: EntityList,
    relationships: RelationshipList,
    document_id: str,
) -> dict[str, int]:
    """
    Stores extracted entities and relationships into Neo4j.

    This is the main function called by the POST /build-graph endpoint.
    It processes a complete EntityList and RelationshipList and MERGEs
    everything into Neo4j.

    Args:
        entities (EntityList):
            All unique entities extracted from the document.
            Each entity becomes a Neo4j node with its type as the label.

        relationships (RelationshipList):
            All unique relationships extracted from the document.
            Each relationship becomes a Neo4j directed edge.

        document_id (str):
            The ID of the uploaded document (UUID string).
            Stored on each node as part of `document_ids` list so we
            can later query which entities came from which document.

    Returns:
        dict[str, int]:
            A summary of what was written:
            {
                "nodes_merged": 42,
                "relationships_merged": 28,
            }

    Example:
        result = build_graph(entities, relationships, document_id="abc-123")
        print(result)
        # → {"nodes_merged": 42, "relationships_merged": 28}
    """
    client = Neo4jClient.get_instance()
    nodes_merged = 0
    relationships_merged = 0

    # ── Step 1: MERGE all entity nodes ───────────────────────────────────────
    logger.info(
        "Merging %d entities into Neo4j (document: %s)...",
        len(entities.entities),
        document_id,
    )

    for entity in entities.entities:
        safe_label = _sanitize_label(entity.type)

        # MERGE the node matching on name + label.
        # ON CREATE → runs only if this is a NEW node:
        #   set document_ids to [document_id]
        # ON MATCH  → runs if the node already exists:
        #   append document_id if not already in the list
        #
        # NOTE: We use $name as a parameter (safe), but the label is
        # built into the string (safe because it's been sanitized above).
        cypher = f"""
            MERGE (n:{safe_label} {{name: $name}})
            ON CREATE SET
                n.document_ids = [$document_id],
                n.created_at   = timestamp()
            ON MATCH SET
                n.document_ids = CASE
                    WHEN $document_id IN n.document_ids
                    THEN n.document_ids
                    ELSE n.document_ids + $document_id
                END
            RETURN n.name AS name
        """

        result = client.run_query(
            cypher,
            {"name": entity.name, "document_id": document_id},
        )

        if result:
            nodes_merged += 1
            logger.debug("Merged node: (%s:%s)", entity.name, safe_label)

    # ── Step 2: MERGE all relationship edges ─────────────────────────────────
    logger.info(
        "Merging %d relationships into Neo4j...",
        len(relationships.relationships),
    )

    for rel in relationships.relationships:
        safe_relation = rel.normalized_relation()

        # MERGE the two endpoint nodes (they should already exist from Step 1,
        # but MERGE here is a safety net in case they were missed).
        # Then MERGE the relationship between them.
        #
        # Why MERGE the endpoints again?
        #   If a relationship refers to an entity that wasn't extracted
        #   (e.g. due to a chunk error), we still want the edge to land
        #   in the graph. MERGE handles this safely.
        cypher = f"""
            MERGE (a {{name: $source}})
            MERGE (b {{name: $target}})
            MERGE (a)-[r:{safe_relation}]->(b)
            ON CREATE SET r.document_ids = [$document_id]
            ON MATCH SET
                r.document_ids = CASE
                    WHEN $document_id IN r.document_ids
                    THEN r.document_ids
                    ELSE r.document_ids + $document_id
                END
            RETURN type(r) AS relation
        """

        result = client.run_query(
            cypher,
            {
                "source": rel.source,
                "target": rel.target,
                "document_id": document_id,
            },
        )

        if result:
            relationships_merged += 1
            logger.debug(
                "Merged relationship: (%s)-[%s]->(%s)",
                rel.source, safe_relation, rel.target,
            )

    summary = {
        "nodes_merged": nodes_merged,
        "relationships_merged": relationships_merged,
    }

    logger.info(
        "Graph build complete — %d nodes, %d relationships merged.",
        nodes_merged,
        relationships_merged,
    )

    return summary
