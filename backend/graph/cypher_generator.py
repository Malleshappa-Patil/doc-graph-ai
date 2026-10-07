"""
graph/cypher_generator.py
────────────────────────────────────────────────────────────────────────────────
Converts natural language questions into Cypher queries using Gemini.

WHERE THIS FITS IN THE Q&A PIPELINE:

  User: "Who created GPT-4?"
       │
       ▼
  [cypher_generator.py]  ← THIS FILE
       │  Cypher string: "MATCH (a)-[:CREATED]->(b {name:'Gpt-4'}) RETURN a.name"
       ▼
  [graph_query.execute_cypher()]
       │  Raw results: [{"a.name": "Openai"}]
       ▼
  [answer_generator.generate_answer()]
       │  "GPT-4 was created by OpenAI."
       ▼
  User sees the answer

WHY GEMINI FOR CYPHER GENERATION?
  Writing Cypher from natural language is non-trivial:
    "Who is the CEO of OpenAI?" → MATCH (p)-[:CEO_OF]->(o {name:'Openai'}) RETURN p.name
  Gemini understands both the question's intent AND the graph schema,
  and produces the correct Cypher pattern.

PROMPT DESIGN:
  The prompt includes:
    1. The full graph schema (labels + relationship types)
    2. Several worked examples (few-shot prompting)
    3. The user's question
    4. Strict instruction: return ONLY the Cypher query

  FEW-SHOT EXAMPLES are critical here. They teach Gemini:
    - How our node properties are structured (always `name`)
    - How to handle case differences (Title Case names in the graph)
    - How to write `RETURN` clauses that are informative

CYPHER VALIDATION:
  We do minimal validation — check that the returned string:
    - Is non-empty
    - Contains "MATCH" or "RETURN" (basic sanity check)
  We don't parse/validate the full Cypher syntax (that would require
  a Cypher parser). Invalid Cypher will fail at execution time with a
  clear error from Neo4j.
────────────────────────────────────────────────────────────────────────────────
"""

import logging

from llm.gemini_client import GeminiClient
from schemas.entities import COMMON_ENTITY_TYPES
from schemas.relationships import COMMON_RELATIONSHIP_TYPES

logger = logging.getLogger(__name__)


# ── Cypher generation prompt ──────────────────────────────────────────────────
# {node_labels}         → comma-separated list of node label types
# {relationship_types}  → comma-separated list of relationship types
# {question}            → the user's natural language question

CYPHER_GENERATION_PROMPT = """You are a Neo4j Cypher expert. Convert the user's natural language question into a Cypher query.

Graph Schema:
- Node labels: {node_labels}
- All nodes have a `name` property (Title Case, e.g. "Openai", "Sam Altman", "Gpt-4")
- Relationship types: {relationship_types}

Rules:
- Write a MATCH query that retrieves the answer to the question.
- Use case-insensitive matching for names: use `toLower(n.name) = toLower($name)` pattern when filtering.
- Always include a RETURN clause that returns meaningful column names.
- Return ONLY the Cypher query. No explanation, no markdown, no backticks.
- If you cannot write a meaningful Cypher query, return exactly: MATCH (n) RETURN n.name LIMIT 10

Examples:

Question: Who created GPT-4?
Cypher: MATCH (a)-[:CREATED]->(b) WHERE toLower(b.name) = toLower('GPT-4') RETURN a.name AS creator, b.name AS product

Question: What did OpenAI create?
Cypher: MATCH (a)-[:CREATED]->(b) WHERE toLower(a.name) = toLower('OpenAI') RETURN a.name AS creator, b.name AS product

Question: Who is the CEO of OpenAI?
Cypher: MATCH (p)-[:CEO_OF]->(o) WHERE toLower(o.name) = toLower('OpenAI') RETURN p.name AS ceo, o.name AS organization

Question: What technologies does OpenAI use?
Cypher: MATCH (a)-[:USES]->(t:Technology) WHERE toLower(a.name) = toLower('OpenAI') RETURN a.name AS entity, t.name AS technology

Question: Where is OpenAI located?
Cypher: MATCH (a)-[:LOCATED_IN]->(l) WHERE toLower(a.name) = toLower('OpenAI') RETURN a.name AS entity, l.name AS location

Question: Who works for OpenAI?
Cypher: MATCH (p)-[:WORKS_FOR]->(o) WHERE toLower(o.name) = toLower('OpenAI') RETURN p.name AS person, o.name AS organization

Question: Show all entities related to GPT-4
Cypher: MATCH (a)-[r]-(b) WHERE toLower(a.name) = toLower('GPT-4') RETURN a.name AS entity, type(r) AS relation, b.name AS related_entity

Question: {question}
Cypher:"""


def generate_cypher(question: str) -> str:
    """
    Converts a natural language question into a Neo4j Cypher query.

    Args:
        question (str):
            The user's natural language question.
            Example: "Who created GPT-4?"
            Example: "What companies are located in San Francisco?"

    Returns:
        str: A Cypher query string ready to be executed against Neo4j.
             Example: "MATCH (a)-[:CREATED]->(b) WHERE ... RETURN a.name"

             Falls back to "MATCH (n) RETURN n.name LIMIT 10" if:
               - The LLM returns an empty response
               - The response doesn't look like a Cypher query

    Raises:
        RuntimeError: If Gemini API fails after all retries.

    Example:
        cypher = generate_cypher("Who created GPT-4?")
        results = execute_cypher(cypher)
        answer = generate_answer("Who created GPT-4?", results)
    """
    if not question or not question.strip():
        logger.warning("generate_cypher received empty question — returning fallback")
        return "MATCH (n) RETURN n.name LIMIT 10"

    logger.info("Generating Cypher for question: '%s'", question)

    # Build the prompt with the current schema
    prompt = CYPHER_GENERATION_PROMPT.format(
        node_labels=", ".join(COMMON_ENTITY_TYPES),
        relationship_types=", ".join(COMMON_RELATIONSHIP_TYPES),
        question=question.strip(),
    )

    # Call Gemini — we want plain text (not JSON) here
    client = GeminiClient.get_instance()
    raw_response = client.generate_text(prompt)

    # Clean the response
    cypher = _clean_cypher_response(raw_response)

    # Basic validation
    if not _looks_like_cypher(cypher):
        logger.warning(
            "Generated Cypher doesn't look valid. Raw: '%s'. Using fallback.",
            raw_response[:200],
        )
        return "MATCH (n) RETURN n.name LIMIT 10"

    logger.info("Generated Cypher: %s", cypher)
    return cypher


def _clean_cypher_response(raw: str) -> str:
    """
    Cleans the raw Gemini response to extract just the Cypher query.

    Gemini sometimes:
      - Adds "Cypher:" prefix (even though we told it not to)
      - Adds markdown fences (```cypher ... ```)
      - Adds trailing commentary after the query

    Args:
        raw (str): Raw text from Gemini.

    Returns:
        str: The cleaned Cypher query string.
    """
    import re

    text = raw.strip()

    # Strip markdown code fences: ```cypher ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:cypher)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Strip "Cypher:" prefix if Gemini added it
    text = re.sub(r"^(?:Cypher|Query)\s*:\s*", "", text, flags=re.IGNORECASE).strip()

    # Take only the first line if there are multiple lines
    # (Gemini sometimes adds explanation after the query)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        # Find the line that starts with MATCH — that's our query
        for line in lines:
            if line.upper().startswith("MATCH"):
                return line

    return text


def _looks_like_cypher(query: str) -> bool:
    """
    Basic sanity check that the string looks like a Cypher query.

    Checks for the presence of key Cypher keywords.
    Does NOT parse or validate Cypher syntax.

    Args:
        query (str): The candidate Cypher string.

    Returns:
        bool: True if it looks like Cypher, False otherwise.
    """
    if not query:
        return False
    upper = query.upper()
    return "MATCH" in upper and "RETURN" in upper
