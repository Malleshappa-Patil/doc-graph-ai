"""
llm/gemini_client.py
────────────────────────────────────────────────────────────────────────────────
Core wrapper around the Google Gemini API.

SDK NOTE:
  We use `google-genai` (the new, actively maintained SDK).
  The old `google-generativeai` package is deprecated as of 2025.

  New SDK import:     from google import genai
  Old SDK import:     import google.generativeai as genai  ← deprecated

  Key API differences:
    Old: genai.configure(api_key=...)  then  genai.GenerativeModel(model)
    New: client = genai.Client(api_key=...)  then  client.models.generate_content(...)

RESPONSIBILITIES:
  1. Initialize and configure the Gemini SDK once (singleton).
  2. Send prompts to Gemini and return the response text.
  3. Extract clean JSON from Gemini's response (strips markdown fences).
  4. Retry on transient failures with exponential backoff.
────────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
import re
import time

from google import genai
from google.genai import types as genai_types

from config import get_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1.5


class GeminiClient:
    """
    Singleton wrapper around the Google Gemini SDK (google-genai).

    USAGE:
        client = GeminiClient.get_instance()
        text = client.generate_text("Summarize this: ...")
        data = client.generate_json("Extract entities from: ...")
    """

    _instance: "GeminiClient | None" = None

    def __init__(self) -> None:
        """
        Initializes the Gemini client.
        Called only ONCE by get_instance().
        """
        settings = get_settings()
        logger.info("Initializing Gemini client with model: %s", settings.gemini_model)

        # Create the client — this is the main entry point in the new SDK.
        # All API calls go through this client object.
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

        # GenerateContentConfig controls how Gemini generates responses.
        #   temperature=0.0 → deterministic output (same prompt = same result).
        #                      Crucial for entity/relationship extraction consistency.
        #   max_output_tokens → cap response length.
        self._config = genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=8192,
        )

        logger.info("Gemini client initialized successfully.")

    @classmethod
    def get_instance(cls) -> "GeminiClient":
        """
        Returns the shared GeminiClient instance, creating it on first call.

        Always use this instead of GeminiClient() directly.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def generate_text(self, prompt: str) -> str:
        """
        Sends a prompt to Gemini and returns the response as a plain string.

        Args:
            prompt: The full prompt string to send to Gemini.

        Returns:
            The model's text response as a string.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug("Gemini request attempt %d/%d", attempt, MAX_RETRIES)

                # New SDK call: client.models.generate_content(model, contents, config)
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=self._config,
                )

                # response.text is a convenience property that returns the
                # text from the first candidate's first part.
                result = response.text.strip()
                logger.debug("Gemini response received (%d chars)", len(result))
                return result

            except Exception as exc:
                last_error = exc
                wait_seconds = BACKOFF_BASE * attempt
                logger.warning(
                    "Gemini attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt, MAX_RETRIES, exc, wait_seconds,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait_seconds)

        raise RuntimeError(
            f"Gemini API failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    def generate_json(self, prompt: str) -> dict:
        """
        Sends a prompt to Gemini and parses the response as JSON.

        Handles the case where Gemini wraps its JSON in markdown code fences.

        Args:
            prompt: A prompt that instructs Gemini to return JSON.

        Returns:
            A Python dict parsed from Gemini's JSON response.

        Raises:
            ValueError: If the response cannot be parsed as valid JSON.
            RuntimeError: If all retry attempts fail.
        """
        raw_text = self.generate_text(prompt)
        cleaned = self._strip_markdown_fences(raw_text)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse Gemini response as JSON.\nRaw:\n%s\nCleaned:\n%s",
                raw_text, cleaned,
            )
            raise ValueError(
                f"Gemini returned invalid JSON. "
                f"Parse error: {exc}. "
                f"Raw response (first 500 chars): {raw_text[:500]}"
            ) from exc

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """
        Removes markdown code fences from a string.

        Handles:
          ```json        ```        `{...}`
          {...}          {...}
          ```            ```

        Examples:
            '```json\\n{"a":1}\\n```'  →  '{"a":1}'
            '{"a":1}'                  →  '{"a":1}'
        """
        fence_pattern = re.compile(
            r"^```(?:json)?\s*\n?(.*?)\n?```$",
            re.DOTALL | re.MULTILINE,
        )
        match = fence_pattern.search(text.strip())
        if match:
            return match.group(1).strip()

        inline_pattern = re.compile(r"^`(.*)`$", re.DOTALL)
        match = inline_pattern.search(text.strip())
        if match:
            return match.group(1).strip()

        return text.strip()
