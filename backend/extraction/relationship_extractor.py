"""
extraction/relationship_extractor.py
────────────────────────────────────────────────────────────────────────────────
Extracts relationships between entities from a text chunk using Gemini.

WHERE THIS FITS IN THE PIPELINE:

  entity_extractor.py → EntityList
                              │
                              ▼
              [relationship_extractor.py]   ← THIS FILE
                              │  RelationshipList
                              ▼
                       [graph_builder.py]  → Neo4j

WHY RELATIONSHIPS NEED THE ENTITY LIST:
  This extractor is called AFTER entity extraction. We pass the already-
  extracted entities into the Gemini prompt. This serves two purposes:

  1. GROUNDING: Gemini can only create relationships between entities it
     has been told about. It won't invent new entity names.
     Example: If we extracted "Sam Altman" and "OpenAI", Gemini will
     create (Sam Altman)-[CEO_OF]->(OpenAI), not (Sam)-[CEO]->(Open AI).

  2. FOCUS: Gemini produces more accurate relationships when it knows
     exactly which entities to link, rather than discovering them again.

ERROR HANDLING STRATEGY:
  Same as entity_extractor.py:
  - Malformed JSON → log warning, return empty RelationshipList.
  - Pydantic validation failure → log warning, return empty.
  - Network/retry failure → re-raise.
────────────────────────────────────────────────────────────────────────────────
"""

import json
import logging

from pydantic import ValidationError

from llm.gemini_client import GeminiClient
from schemas.entities import EntityList
from schemas.relationships import Relationship, RelationshipList
from extraction.prompts import build_relationship_prompt

logger = logging.getLogger(__name__)


def extract_relationships(text: str, entities: EntityList) -> RelationshipList:
    """
    Extracts relationships between known entities from a single text chunk.

    Args:
        text (str):
            A cleaned text chunk (output of text_cleaner.chunk_text()).
            Should be the same chunk that was used to extract `entities`.

        entities (EntityList):
            The entities already extracted from this text chunk.
            These are passed into the Gemini prompt as grounding context.
            If this list is empty, the function returns an empty
            RelationshipList immediately (no point calling Gemini
            if there are no entities to connect).

    Returns:
        RelationshipList:
            A validated, deduplicated list of relationships found in the text.
            Each relationship references entities from the `entities` input.
            Returns RelationshipList(relationships=[]) if:
              - The text is empty
              - The entity list is empty (nothing to connect)
              - Gemini returns no relationships
              - Gemini returns malformed JSON (logged as warning)
              - Pydantic validation fails (logged as warning)

    Example:
        text = "Sam Altman is the CEO of OpenAI, which created GPT-4."
        entities = EntityList(entities=[
            Entity(name="Sam Altman", type="Person"),
            Entity(name="OpenAI",     type="Organization"),
            Entity(name="GPT-4",      type="Product"),
        ])
        result = extract_relationships(text, entities)
        for rel in result.relationships:
            print(rel.source, f"--[{rel.relation}]-->", rel.target)
        # Sam Altman --[CEO_OF]--> OpenAI
        # OpenAI     --[CREATED]--> GPT-4
    """
    # Guard: skip empty text
    if not text or not text.strip():
        logger.debug("extract_relationships received empty text — returning empty list")
        return RelationshipList(relationships=[])

    # Guard: no point asking Gemini for relationships if there are no entities
    if not entities.entities:
        logger.debug("No entities provided — skipping relationship extraction")
        return RelationshipList(relationships=[])

    logger.info(
        "Extracting relationships from chunk (%d chars) with %d entities...",
        len(text),
        len(entities.entities),
    )

    # Step 1: Serialize the entity list as a JSON array for the prompt.
    # We only pass name and type — that's all Gemini needs for grounding.
    entities_json = json.dumps(
        [{"name": e.name, "type": e.type} for e in entities.entities],
        indent=2,
    )

    # Step 2: Build the relationship extraction prompt
    prompt = build_relationship_prompt(text, entities_json)

    # Step 3: Call Gemini
    try:
        client = GeminiClient.get_instance()
        raw_dict = client.generate_json(prompt)

    except ValueError as exc:
        logger.warning(
            "Relationship extraction failed — Gemini returned invalid JSON: %s", exc
        )
        return RelationshipList(relationships=[])

    except RuntimeError as exc:
        logger.error("Relationship extraction failed after all retries: %s", exc)
        raise

    # Step 4: Parse into Pydantic model
    try:
        rel_list = RelationshipList.model_validate(raw_dict)

    except ValidationError as exc:
        logger.warning(
            "Relationship extraction failed — Gemini JSON didn't match schema.\n"
            "Raw dict: %s\nValidation error: %s",
            raw_dict,
            exc,
        )
        return RelationshipList(relationships=[])

    # Step 5: Normalize and filter
    # - Normalize source, target names to Title Case
    # - Normalize relation to UPPER_SNAKE_CASE
    # - Filter out any relationships where source or target isn't in our
    #   known entity set (Gemini sometimes adds entities despite instructions)
    known_names: set[str] = {e.name.lower() for e in entities.entities}

    normalized_rels: list[Relationship] = []
    skipped = 0

    for rel in rel_list.relationships:
        norm_source = rel.normalized_source()
        norm_target = rel.normalized_target()
        norm_relation = rel.normalized_relation()

        # Filter: both endpoints must be in the known entity set
        if norm_source.lower() not in known_names:
            logger.debug(
                "Skipping relationship — source '%s' not in known entities", norm_source
            )
            skipped += 1
            continue

        if norm_target.lower() not in known_names:
            logger.debug(
                "Skipping relationship — target '%s' not in known entities", norm_target
            )
            skipped += 1
            continue

        normalized_rels.append(
            Relationship(
                source=norm_source,
                target=norm_target,
                relation=norm_relation,
            )
        )

    if skipped > 0:
        logger.info("Skipped %d relationship(s) with unknown entities", skipped)

    # Step 6: Deduplicate
    result = RelationshipList(relationships=normalized_rels).unique()

    logger.info(
        "Relationships extracted: %d unique relationship(s) found", len(result.relationships)
    )

    return result


def extract_relationships_from_chunks(
    chunks: list[str],
    entities_per_chunk: list[EntityList],
) -> RelationshipList:
    """
    Extracts and merges relationships from multiple text chunks.

    This is a convenience wrapper for the common case of processing an
    entire document that has been split into chunks.

    Args:
        chunks (list[str]):
            List of text chunks from text_cleaner.chunk_text().

        entities_per_chunk (list[EntityList]):
            Entity list for each chunk — must be the same length as `chunks`.
            Each EntityList should contain the entities extracted from the
            corresponding chunk (not the global entity list).

            WHY PER-CHUNK (not global)?
              Using the global entity list for every chunk would cause Gemini
              to be overwhelmed by entities that don't appear in the current
              chunk. Per-chunk entities keep the grounding tight and accurate.

    Returns:
        RelationshipList:
            All relationships across all chunks, deduplicated.

    Raises:
        ValueError: If chunks and entities_per_chunk have different lengths.
    """
    if not chunks:
        return RelationshipList(relationships=[])

    if len(chunks) != len(entities_per_chunk):
        raise ValueError(
            f"chunks ({len(chunks)}) and entities_per_chunk "
            f"({len(entities_per_chunk)}) must have the same length"
        )

    logger.info("Extracting relationships from %d chunk(s)...", len(chunks))

    all_relationships: list[Relationship] = []

    for i, (chunk, entities) in enumerate(zip(chunks, entities_per_chunk), start=1):
        logger.info("Processing chunk %d/%d for relationships...", i, len(chunks))
        chunk_result = extract_relationships(chunk, entities)
        all_relationships.extend(chunk_result.relationships)

    # Deduplicate across all chunks
    merged = RelationshipList(relationships=all_relationships).unique()

    logger.info(
        "Total unique relationships across %d chunk(s): %d",
        len(chunks),
        len(merged.relationships),
    )

    return merged
