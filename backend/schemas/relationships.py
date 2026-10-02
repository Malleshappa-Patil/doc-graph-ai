"""
schemas/relationships.py
────────────────────────────────────────────────────────────────────────────────
Defines the data shapes (Pydantic models) for relationships extracted from docs.

HOW RELATIONSHIPS WORK IN A KNOWLEDGE GRAPH:
  A relationship is a directed edge between two entity nodes:

        (source) ──[relation]──▶ (target)

  Example:
        (OpenAI) ──[CREATED]──▶ (GPT-4)
        (Sam Altman) ──[CEO_OF]──▶ (OpenAI)

DESIGN DECISION — open `str` instead of rigid `Literal[...]`:
  Relationship types depend heavily on the document domain:
    - Business docs   → ACQUIRED, MERGED_WITH, INVESTED_IN
    - Research papers → CITES, EXTENDS, CONTRADICTS
    - Legal docs      → GOVERNS, ENFORCES, APPLIES_TO
  Using `str` allows Gemini to surface domain-specific relationships naturally.
  Well-known types are listed as guidance in the extraction prompt.
────────────────────────────────────────────────────────────────────────────────
"""

from pydantic import BaseModel, Field


# ── Well-known relationship types (for documentation + prompt guidance) ───────
# These are suggestions sent to Gemini in the prompt.
# Gemini may return other types — and that's perfectly fine.
COMMON_RELATIONSHIP_TYPES = [
    "CREATED",
    "WORKS_FOR",
    "CEO_OF",
    "USES",
    "LOCATED_IN",
    "RELATED_TO",
    "FOUNDED",
    "ACQUIRED",
    "PART_OF",
    "CITED_BY",
]


class Relationship(BaseModel):
    """
    Represents a single directional relationship between two entities.

    Fields:
        source (str):   The name of the entity where the relationship starts.
                        Must match an entity name that exists (or will exist) in
                        the Neo4j graph.

        target (str):   The name of the entity where the relationship ends.
                        Same constraint as source.

        relation (str): The type/label of the relationship.
                        Written in UPPER_SNAKE_CASE by convention (Neo4j standard).
                        e.g. "CREATED", "CEO_OF", "WORKS_FOR"

    Example (in graph terms):
        Relationship(source="OpenAI", target="GPT-4", relation="CREATED")
        → (OpenAI)-[:CREATED]→(GPT-4)
    """

    source: str = Field(
        ...,
        description="Name of the source entity (start of the relationship).",
        examples=["OpenAI", "Elon Musk"],
    )
    target: str = Field(
        ...,
        description="Name of the target entity (end of the relationship).",
        examples=["GPT-4", "Tesla"],
    )
    relation: str = Field(
        ...,
        description=(
            "Relationship type in UPPER_SNAKE_CASE. Common types: "
            + ", ".join(COMMON_RELATIONSHIP_TYPES)
            + ". Other types are allowed when they better describe the relationship."
        ),
        examples=["CREATED", "CEO_OF", "USES"],
    )

    def normalized_relation(self) -> str:
        """
        Returns the relationship type in UPPER_SNAKE_CASE.

        WHY: Neo4j relationship types are case-sensitive. "created" and
        "CREATED" are different relationship types. Normalizing to upper-case
        ensures consistency.

        Example:
            Relationship(..., relation="created").normalized_relation()
            → "CREATED"
        """
        return self.relation.strip().upper().replace(" ", "_")

    def normalized_source(self) -> str:
        """Returns the source entity name in Title Case (matches Entity.normalized_name)."""
        return self.source.strip().title()

    def normalized_target(self) -> str:
        """Returns the target entity name in Title Case (matches Entity.normalized_name)."""
        return self.target.strip().title()


class RelationshipList(BaseModel):
    """
    Wraps a list of Relationship objects.

    This is the top-level model that Gemini's JSON output is parsed into.

    Expected Gemini JSON output shape:
    {
        "relationships": [
            {"source": "OpenAI",    "target": "GPT-4",   "relation": "CREATED"},
            {"source": "Sam Altman","target": "OpenAI",  "relation": "CEO_OF"}
        ]
    }

    Usage:
        raw_json = gemini_response_text
        rel_list = RelationshipList.model_validate_json(raw_json)
        for rel in rel_list.relationships:
            print(rel.source, rel.relation, rel.target)
    """

    relationships: list[Relationship] = Field(
        default_factory=list,
        description="List of relationships extracted from the document chunk.",
    )

    def unique(self) -> "RelationshipList":
        """
        Removes duplicate relationships (same source + relation + target,
        case-insensitive).

        WHY: Just like entities, the same relationship can be mentioned in
        multiple chunks. Deduplication here prevents redundant Neo4j MERGEs.

        Returns:
            A new RelationshipList with duplicates removed.
        """
        seen: set[tuple[str, str, str]] = set()
        unique_rels: list[Relationship] = []

        for rel in self.relationships:
            key = (
                rel.source.lower(),
                rel.relation.lower(),
                rel.target.lower(),
            )
            if key not in seen:
                seen.add(key)
                unique_rels.append(rel)

        return RelationshipList(relationships=unique_rels)
