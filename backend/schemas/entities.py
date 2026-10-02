"""
schemas/entities.py
────────────────────────────────────────────────────────────────────────────────
Defines the data shapes (Pydantic models) for entities extracted from documents.

WHY PYDANTIC?
  Pydantic enforces types at runtime. If Gemini returns bad JSON or a field
  with the wrong type, Pydantic raises a clear ValidationError instead of
  silently breaking things downstream.

DESIGN DECISION — open `str` instead of rigid `Literal[...]`:
  The original plan listed 6 entity types (Person, Organization, ...).
  In practice, a document about chemistry might have "Compound" or "Element".
  A legal document might have "Law" or "Court".
  By using `str`, Gemini can discover entity types naturally from any document.
  We still document the common/well-known types so the LLM prompt guides it.
────────────────────────────────────────────────────────────────────────────────
"""

from pydantic import BaseModel, Field


# ── Well-known entity types (for documentation + prompt guidance) ─────────────
# These are suggestions sent to Gemini in the prompt.
# Gemini may return other types — and that's perfectly fine.
COMMON_ENTITY_TYPES = [
    "Person",
    "Organization",
    "Product",
    "Technology",
    "Location",
    "Concept",
    "Event",
    "Law",
    "Date",
]


class Entity(BaseModel):
    """
    Represents a single entity extracted from a document.

    Fields:
        name (str):  The entity's canonical name, e.g. "OpenAI", "Elon Musk".
                     Will be title-cased before storing in Neo4j to prevent
                     duplicates from casing differences ("openai" vs "OpenAI").

        type (str):  The entity's semantic type, e.g. "Organization", "Person".
                     Not restricted to a fixed list — Gemini may return types
                     beyond the common set when the document warrants it.
    """

    name: str = Field(
        ...,
        description="The canonical name of the entity (title-cased).",
        examples=["OpenAI", "Elon Musk", "Python"],
    )
    type: str = Field(
        ...,
        description=(
            "Semantic type of the entity. Common types: "
            + ", ".join(COMMON_ENTITY_TYPES)
            + ". Other types are allowed."
        ),
        examples=["Organization", "Person", "Technology"],
    )

    def normalized_name(self) -> str:
        """
        Returns the entity name in Title Case.

        WHY: Neo4j MERGE matches nodes by exact string equality.
        "openai" and "OpenAI" would be treated as two different nodes.
        Normalizing to title-case at the schema level ensures consistency
        before anything hits the database.

        Example:
            Entity(name="openAI", type="Organization").normalized_name()
            → "Openai"   (simple title case)
        """
        return self.name.strip().title()


class EntityList(BaseModel):
    """
    Wraps a list of Entity objects.

    This is the top-level model that Gemini's JSON output is parsed into.

    Expected Gemini JSON output shape:
    {
        "entities": [
            {"name": "OpenAI", "type": "Organization"},
            {"name": "GPT-4",  "type": "Product"}
        ]
    }

    Usage:
        raw_json = gemini_response_text          # e.g. '{"entities": [...]}'
        entity_list = EntityList.model_validate_json(raw_json)
        for entity in entity_list.entities:
            print(entity.name, entity.type)
    """

    entities: list[Entity] = Field(
        default_factory=list,
        description="List of entities extracted from the document chunk.",
    )

    def unique(self) -> "EntityList":
        """
        Removes duplicate entities (same name + type, case-insensitive).

        WHY: When a document is chunked, the same entity often appears in
        multiple chunks. We deduplicate here before sending to Neo4j,
        reducing unnecessary MERGE operations.

        Returns:
            A new EntityList with duplicates removed.
        """
        seen: set[tuple[str, str]] = set()
        unique_entities: list[Entity] = []

        for entity in self.entities:
            key = (entity.name.lower(), entity.type.lower())
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        return EntityList(entities=unique_entities)
