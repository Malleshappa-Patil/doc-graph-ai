# This file marks llm/ as a Python package.
# It re-exports the two main objects used by other modules.
#
# Other modules can do:
#   from llm import gemini_client, generate_answer
#   from llm.gemini_client import GeminiClient

from llm.gemini_client import GeminiClient
from llm.answer_generator import generate_answer

__all__ = ["GeminiClient", "generate_answer"]
