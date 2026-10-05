"""
extraction/entity_extractor.py
────────────────────────────────────────────────────────────────────────────────
Extracts named entities from a text chunk using Google Gemini.

WHERE THIS FITS IN THE PIPELINE:

  PDF text (chunked)
       │
       ▼
  [entity_extractor.py]   ← THIS FILE
       │  EntityList
       ▼
  [relationship_extractor.py]
       │  RelationshipList
       ▼
  [graph_builder.py]      → Neo4j

WHAT THIS FILE DOES:
  1. Takes a text chunk (string) as input.
  2. Builds the entity extraction prompt (from prompts.py).
  3. Sends the prompt to Gemini via GeminiClient.generate_json().
  4. Parses Gemini's JSON response into an EntityList Pydantic model.
  5. Normalizes entity names (title-case) and deduplicates.
  6. Returns the validated, clean EntityList.

ERROR HANDLING STRATEGY:
  - If Gemini returns malformed JSON → log a warning, return empty EntityList.
    WHY: One bad chunk shouldn't crash the entire ingestion job.
    The document will still be partially processed from other chunks.
  - If Pydantic validation fails (unexpected field types) → same: log + empty.
  - All other exceptions propagate up (e.g. network failure after all retries).
────────────────────────────────────────────────────────────────────────────────
"""

import json
import logging

from pydantic import ValidationError

from llm.gemini_client import GeminiClient
from schemas.entities import Entity, EntityList
from extraction.prompts import build_entity_prompt

logger = logging.getLogger(__name__)


def extract_entities(text: str) -> EntityList:
    """
    Extracts named entities from a single text chunk using Gemini.

    Args:
        text (str):
            A cleaned text chunk (output of text_cleaner.chunk_text()).
            Should be non-empty. Empty strings return an empty EntityList.

    Returns:
        EntityList:
            A validated, deduplicated list of entities found in the text.
            Returns EntityList(entities=[]) if:
              - The text is empty
              - Gemini returns no entities
              - Gemini returns malformed JSON (logged as warning)
              - Pydantic validation fails (logged as warning)

    Example:
        text = "Sam Altman is the CEO of OpenAI, which created GPT-4."
        result = extract_entities(text)
        for entity in result.entities:
            print(entity.name, "→", entity.type)
        # Sam Altman → Person
        # OpenAI     → Organization
        # GPT-4      → Product

    Notes:
        - Entity names are normalized to Title Case before return.
        - Duplicates (same name+type, case-insensitive) are removed.
        - This function processes ONE chunk. The caller is responsible for
          iterating over all chunks and merging results.
    """
    # Guard: skip empty input
    if not text or not text.strip():
        logger.debug("extract_entities received empty text — returning empty list")
        return EntityList(entities=[])

    logger.info("Extracting entities from chunk (%d chars)...", len(text))

    # Step 1: Build the prompt
    prompt = build_entity_prompt(text)

    # Step 2: Call Gemini and get the raw JSON dict
    try:
        client = GeminiClient.get_instance()
        raw_dict = client.generate_json(prompt)

    except ValueError as exc:
        # Gemini returned something that isn't valid JSON
        logger.warning(
            "Entity extraction failed — Gemini returned invalid JSON: %s", exc
        )
        return EntityList(entities=[])

    except RuntimeError as exc:
        # All retry attempts failed (network/API issue)
        # Re-raise so the caller can decide whether to abort or continue
        logger.error("Entity extraction failed after all retries: %s", exc)
        raise

    # Step 3: Parse the dict into our Pydantic model
    # EntityList.model_validate(dict) validates field types and structure.
    try:
        entity_list = EntityList.model_validate(raw_dict)

    except ValidationError as exc:
        logger.warning(
            "Entity extraction failed — Gemini JSON didn't match expected schema.\n"
            "Raw dict: %s\nValidation error: %s",
            raw_dict,
            exc,
        )
        return EntityList(entities=[])

    # Step 4: Normalize entity names to title-case
    # WHY: "openai", "OpenAI", "OPENAI" should all become "Openai" so Neo4j
    # MERGE treats them as the same node.
    normalized_entities = [
        Entity(
            name=entity.normalized_name(),
            type=entity.type.strip(),
        )
        for entity in entity_list.entities
    ]

    # Step 5: Deduplicate (same name+type, case-insensitive)
    result = EntityList(entities=normalized_entities).unique()

    logger.info(
        "Entities extracted: %d unique entities found", len(result.entities)
    )

    return result


def extract_entities_from_chunks(chunks: list[str]) -> EntityList:
    """
    Extracts and merges entities from multiple text chunks.

    This is a convenience wrapper for the common case of processing an
    entire document that has been split into chunks.

    Args:
        chunks (list[str]):
            List of text chunks from text_cleaner.chunk_text().

    Returns:
        EntityList:
            A single EntityList with entities from ALL chunks,
            deduplicated across the full set.

    Example:
        chunks = chunk_text(clean_text(parse_pdf("report.pdf")))
        all_entities = extract_entities_from_chunks(chunks)

    Notes:
        - Processes chunks sequentially (not in parallel) to avoid
          rate-limiting on the Gemini API.
        - If one chunk fails JSON parsing, it is skipped (warning logged)
          but processing continues for remaining chunks.
    """
    if not chunks:
        return EntityList(entities=[])

    logger.info("Extracting entities from %d chunk(s)...", len(chunks))

    all_entities: list[Entity] = []

    for i, chunk in enumerate(chunks, start=1):
        logger.info("Processing chunk %d/%d...", i, len(chunks))
        chunk_result = extract_entities(chunk)
        all_entities.extend(chunk_result.entities)

    # Deduplicate across all chunks
    merged = EntityList(entities=all_entities).unique()

    logger.info(
        "Total unique entities across %d chunk(s): %d",
        len(chunks),
        len(merged.entities),
    )

    return merged
