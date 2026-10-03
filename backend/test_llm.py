"""
test_llm.py
────────────────────────────────────────────────────────────────────────────────
Syntax and logic tests for the llm/ module.
These tests do NOT make real API calls and do NOT require a .env file.
────────────────────────────────────────────────────────────────────────────────
"""
import sys
import json
import unittest.mock as mock

sys.path.insert(0, ".")

# ── Test 1: Config class structure (no .env required) ─────────────────────────
print("=== Test 1: Config class structure ===")
import types

with open("config.py") as f:
    src = f.read()

config_mod = types.ModuleType("config_mod")
# Prevent the lazy singleton from being called during import
src_no_call = src.replace("_settings_instance = Settings()", "pass  # skipped in test")
exec(compile(src_no_call, "config.py", "exec"), config_mod.__dict__)

Settings = config_mod.Settings
fields = list(Settings.model_fields.keys())
print("  [OK] Settings class loaded")
print("  Fields:", fields)
assert "gemini_api_key"  in fields
assert "neo4j_uri"       in fields
assert "neo4j_password"  in fields
assert "gemini_model"    in fields
assert "upload_dir"      in fields
print("  [OK] All required fields present")

# ── Test 2: Markdown fence stripping ─────────────────────────────────────────
print()
print("=== Test 2: Markdown fence stripping ===")

# Patch google.genai so GeminiClient can be imported without a real API key
with mock.patch.dict("sys.modules", {
    "google": mock.MagicMock(),
    "google.genai": mock.MagicMock(),
    "google.genai.types": mock.MagicMock(),
}):
    # Also patch get_settings to avoid .env requirement
    with mock.patch("config.get_settings") as mock_settings:
        mock_settings.return_value = mock.MagicMock(
            gemini_api_key="test-key",
            gemini_model="gemini-1.5-flash",
        )
        from llm.gemini_client import GeminiClient

cases = [
    ('{"a": 1}',                            '{"a": 1}'),
    ('```json\n{"a": 1}\n```',              '{"a": 1}'),
    ('```\n{"a": 1}\n```',                  '{"a": 1}'),
    ('`{"a": 1}`',                          '{"a": 1}'),
    ('  ```json\n{"a": 1}\n```  ',          '{"a": 1}'),
    ('```json\n{"entities": []}\n```',      '{"entities": []}'),
]

all_pass = True
for i, (raw, expected) in enumerate(cases, 1):
    result = GeminiClient._strip_markdown_fences(raw)
    ok = result == expected
    if not ok:
        all_pass = False
    print(f"  [{'OK' if ok else 'FAIL'}] Case {i}: {repr(result)}")

# ── Test 3: generate_json parses fenced JSON ──────────────────────────────────
print()
print("=== Test 3: generate_json parses fenced JSON ===")

GeminiClient._instance = None
fenced_json = '```json\n{"entities": [{"name": "OpenAI", "type": "Organization"}]}\n```'

with mock.patch.object(GeminiClient, "generate_text", return_value=fenced_json):
    # get_instance won't call __init__ since we set _instance manually
    GeminiClient._instance = mock.MagicMock(spec=GeminiClient)
    GeminiClient._instance.generate_text = mock.MagicMock(return_value=fenced_json)
    GeminiClient._instance.generate_json = GeminiClient.generate_json.__get__(
        GeminiClient._instance, GeminiClient
    )
    GeminiClient._instance._strip_markdown_fences = GeminiClient._strip_markdown_fences

    result = GeminiClient._instance.generate_json("prompt")
    assert isinstance(result, dict),                       "Result should be dict"
    assert result["entities"][0]["name"] == "OpenAI",      "Wrong entity name"
    print("  [OK] generate_json parses fenced JSON into dict correctly")

GeminiClient._instance = None

# ── Test 4: Answer generator prompt ──────────────────────────────────────────
print()
print("=== Test 4: Answer generator prompt ===")
from llm.answer_generator import ANSWER_GENERATION_PROMPT

question = "Who created GPT-4?"
results  = [{"creator": "OpenAI", "product": "GPT-4"}]
prompt   = ANSWER_GENERATION_PROMPT.format(
    question=question,
    graph_results=json.dumps(results, indent=2),
)
assert question    in prompt
assert "OpenAI"    in prompt
assert "Answer:"   in prompt
print("  [OK] Prompt contains question, graph results, and Answer label")

# ── Test 5: generate_answer end-to-end (mocked) ───────────────────────────────
print()
print("=== Test 5: generate_answer end-to-end (mocked) ===")
from llm.answer_generator import generate_answer

# Mock GeminiClient.get_instance in the module where it is called.
# answer_generator.py does: from llm.gemini_client import GeminiClient
# so we patch 'llm.answer_generator.GeminiClient.get_instance'.
mock_client = mock.MagicMock()
mock_client.generate_text.return_value = "GPT-4 was created by OpenAI."

with mock.patch("llm.answer_generator.GeminiClient.get_instance",
                return_value=mock_client):
    answer = generate_answer(
        question="Who created GPT-4?",
        graph_results=[{"creator": "OpenAI", "product": "GPT-4"}],
    )
    assert answer == "GPT-4 was created by OpenAI.", f"Got: {answer}"
    print(f"  [OK] Answer: '{answer}'")

print()
print("=" * 50)
print("All tests passed ✓" if all_pass else "Some fence tests FAILED ✗")
