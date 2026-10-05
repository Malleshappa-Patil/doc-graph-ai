"""
extraction/prompts.py
────────────────────────────────────────────────────────────────────────────────
All Gemini prompt templates for entity and relationship extraction.

WHY A SEPARATE FILE FOR PROMPTS?
  Prompts are effectively the "configuration" of your LLM pipeline.
  They need to be tuned, tested, and iterated on independently from the
  Python logic. Keeping them in one file means:
    - You can tune prompts without touching business logic
    - You can A/B test different prompt versions
    - It's easy to review what the LLM is being asked to do

PROMPT DESIGN PRINCIPLES USED HERE:
  1. Role assignment        — "You are a knowledge graph expert..."
                              Primes the model to reason in the right mode.
  2. Clear output format    — Exact JSON schema shown with examples.
                              Gemini follows concrete examples better than
                              abstract descriptions.
  3. Hard constraints       — "Return ONLY valid JSON" / "No explanation"
                              Prevents Gemini from adding commentary that
                              breaks JSON parsing.
  4. Open types             — We list common types as examples but explicitly
                              say other types are allowed. This lets Gemini
                              surface domain-specific entities/relationships.
  5. Grounded relationships — The relationship prompt receives the already-
                              extracted entity list. This grounds Gemini in
                              the actual entities rather than hallucinating
                              new ones.
────────────────────────────────────────────────────────────────────────────────
"""

from schemas.entities import COMMON_ENTITY_TYPES
from schemas.relationships import COMMON_RELATIONSHIP_TYPES

# ── Placeholders used in templates ────────────────────────────────────────────
# {text}              → the raw text chunk to analyse
# {entity_types}      → comma-separated list of common entity type names
# {entities_json}     → JSON array of already-extracted entities (for grounding)
# {relationship_types}→ comma-separated list of common relationship type names


ENTITY_EXTRACTION_PROMPT = """You are a knowledge graph expert specializing in named entity recognition.

Your task is to extract ALL meaningful entities from the following text.

Common entity types include: {entity_types}
You MAY use other entity types if the text clearly warrants them (e.g. "Law", "Event", "Chemical", "Country").

Rules:
- Extract every distinct entity mentioned, even if it appears multiple times.
- Use the most specific type that fits (prefer "Person" over "Concept" for a named individual).
- Entity names should be in their canonical, full form (e.g. "United States" not "US").
- Do NOT extract generic words or common nouns (e.g. do not extract "company" or "system").
- Return ONLY valid JSON. No explanation, no markdown, no extra text.

Output format (strict):
{{
  "entities": [
    {{"name": "EntityName", "type": "EntityType"}},
    {{"name": "AnotherEntity", "type": "EntityType"}}
  ]
}}

If no entities are found, return: {{"entities": []}}

Text to analyse:
\"\"\"
{text}
\"\"\""""


RELATIONSHIP_EXTRACTION_PROMPT = """You are a knowledge graph expert specializing in relation extraction.

Your task is to extract meaningful relationships between entities in the following text.

Known entities already extracted from this text:
{entities_json}

Common relationship types include: {relationship_types}
You MAY use other relationship types in UPPER_SNAKE_CASE if they better describe the connection
(e.g. "ACQUIRED", "CITED_BY", "GOVERNED_BY", "INVESTED_IN").

Rules:
- Only extract relationships between entities from the "Known entities" list above.
- Do NOT invent entities not present in the list.
- Each relationship must have a clear directional meaning: source → relation → target.
- Relationship types must be in UPPER_SNAKE_CASE (e.g. "WORKS_FOR", "CEO_OF").
- A relationship should be extractable from the text — do not infer or hallucinate.
- Return ONLY valid JSON. No explanation, no markdown, no extra text.

Output format (strict):
{{
  "relationships": [
    {{"source": "EntityA", "target": "EntityB", "relation": "RELATION_TYPE"}},
    {{"source": "EntityC", "target": "EntityD", "relation": "RELATION_TYPE"}}
  ]
}}

If no relationships are found, return: {{"relationships": []}}

Text to analyse:
\"\"\"
{text}
\"\"\""""


def build_entity_prompt(text: str) -> str:
    """
    Builds the final entity extraction prompt by inserting the text chunk
    and the list of common entity types.

    Args:
        text (str): A cleaned text chunk from text_cleaner.chunk_text().

    Returns:
        str: The complete prompt string ready to send to Gemini.

    Example:
        prompt = build_entity_prompt("Sam Altman is the CEO of OpenAI.")
        # → Full prompt with entity types and the text inserted
    """
    entity_types_str = ", ".join(COMMON_ENTITY_TYPES)
    return ENTITY_EXTRACTION_PROMPT.format(
        entity_types=entity_types_str,
        text=text,
    )


def build_relationship_prompt(text: str, entities_json: str) -> str:
    """
    Builds the final relationship extraction prompt by inserting the text
    chunk and the JSON array of already-extracted entities.

    WHY PASS ENTITIES IN?
      Grounding the relationship prompt in the known entity list prevents
      Gemini from hallucinating new entity names that don't match what's
      in the graph. It also helps Gemini focus on real connections rather
      than surface-level co-occurrence.

    Args:
        text (str):
            A cleaned text chunk from text_cleaner.chunk_text().

        entities_json (str):
            A JSON string representing the list of extracted entities.
            Example: '[{"name": "OpenAI", "type": "Organization"}, ...]'

    Returns:
        str: The complete prompt string ready to send to Gemini.
    """
    relationship_types_str = ", ".join(COMMON_RELATIONSHIP_TYPES)
    return RELATIONSHIP_EXTRACTION_PROMPT.format(
        entities_json=entities_json,
        relationship_types=relationship_types_str,
        text=text,
    )
