"""
llm/answer_generator.py
────────────────────────────────────────────────────────────────────────────────
Converts raw Neo4j graph query results into natural language answers.

WHERE THIS FITS IN THE Q&A PIPELINE:

  User question (NL)
       │
       ▼
  [cypher_generator.py]  ← generates Cypher query from the question
       │
       ▼
  [graph_query.py]       ← executes Cypher, returns raw Neo4j results
       │
       ▼
  [answer_generator.py]  ← THIS FILE — turns raw results into a readable answer
       │
       ▼
  Human-readable answer string

WHY IS THIS STEP NEEDED?
  Neo4j returns results as Python dicts (or lists of dicts). For example:

    [
        {"n.name": "Sam Altman", "r": "CEO_OF", "m.name": "OpenAI"},
        {"n.name": "Greg Brockman", "r": "CO_FOUNDER_OF", "m.name": "OpenAI"}
    ]

  That's not something you'd show directly to a user. This module sends that
  raw data to Gemini with the original question, and Gemini produces a clean
  answer like:

    "Sam Altman is the CEO of OpenAI. Greg Brockman is a Co-Founder."

DESIGN DECISION — Why Gemini for this step (not string templates)?
  String templates are brittle:
    - "The answer is {result[0]['n.name']}" breaks if the result is empty.
    - Can't handle multiple result rows naturally.
    - Can't handle "no results found" gracefully.

  Gemini handles all these cases naturally in natural language.
────────────────────────────────────────────────────────────────────────────────
"""

import json
import logging

from llm.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


# ── Prompt template for answer generation ─────────────────────────────────────
# This prompt is intentionally explicit about the format of graph_results
# so Gemini understands it's receiving structured data, not free text.

ANSWER_GENERATION_PROMPT = """You are a helpful assistant that answers questions based on knowledge graph query results.

The user asked this question:
{question}

A Cypher query was executed against a Neo4j knowledge graph and returned these results:
{graph_results}

Instructions:
- Answer the question clearly and concisely using ONLY the information in the graph results.
- If the graph results are empty or contain no relevant information, say: "I could not find information about that in the knowledge graph."
- Do NOT make up information that is not in the graph results.
- Write in complete sentences. Be conversational but factual.
- If multiple results exist, summarize them naturally (e.g. "OpenAI created GPT-3, GPT-4, and Sora.").

Answer:"""


def generate_answer(question: str, graph_results: list[dict]) -> str:
    """
    Converts Neo4j graph query results into a natural language answer.

    Args:
        question (str):
            The original natural language question from the user.
            Example: "Who created GPT-4?"

        graph_results (list[dict]):
            The raw results returned by Neo4j after executing a Cypher query.
            This is a list of dictionaries, where each dict is one result row.

            Example:
            [
                {"creator": "OpenAI", "product": "GPT-4"},
                {"creator": "OpenAI", "product": "GPT-3"}
            ]

            An empty list [] means the query found nothing.

    Returns:
        str: A natural language answer to the user's question.
             Example: "GPT-4 was created by OpenAI."

    Raises:
        RuntimeError: If the Gemini API fails after all retries
                      (propagated from GeminiClient.generate_text).

    Example usage (from the /chat API endpoint):
        results = graph_query.execute(cypher_query)
        answer = generate_answer(
            question="Who created GPT-4?",
            graph_results=results
        )
        return {"answer": answer}
    """
    logger.info(
        "Generating answer for question: '%s' with %d graph result(s)",
        question,
        len(graph_results),
    )

    # Format graph_results as a readable JSON string for the prompt.
    # json.dumps with indent=2 makes it easy for Gemini to read.
    # If the list is empty, we still pass "[]" — the prompt handles that case.
    formatted_results = json.dumps(graph_results, indent=2, default=str)
    # NOTE: default=str handles Neo4j-specific types (e.g. datetime, Node objects)
    # that aren't JSON-serializable by default.

    # Build the final prompt by inserting the question and results
    prompt = ANSWER_GENERATION_PROMPT.format(
        question=question,
        graph_results=formatted_results,
    )

    logger.debug("Answer generation prompt:\n%s", prompt)

    # Call Gemini and return the plain text response
    client = GeminiClient.get_instance()
    answer = client.generate_text(prompt)

    logger.info("Answer generated successfully (%d chars)", len(answer))
    return answer
