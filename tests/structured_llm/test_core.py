"""Tests for toolkit.structured_llm."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from toolkit.structured_llm import (
    Example,
    StructuredResult,
    load_prompt,
    load_schema,
    parse_json_response,
    structured_call,
    structured_complete,
    validate_json_schema,
)


FIXTURES_DIR = Path(__file__).with_name("fixtures")


def test_parse_json_response_valid_object():
    assert parse_json_response('{"name": "Ada", "score": 3}') == {
        "name": "Ada",
        "score": 3,
    }


def test_parse_json_response_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_json_response("{bad")


def test_parse_json_response_rejects_non_object():
    with pytest.raises(ValueError, match="must be an object"):
        parse_json_response("[1, 2, 3]")


def test_parse_json_response_strips_json_code_fence():
    fenced = '```json\n{"status": "ok"}\n```'
    assert parse_json_response(fenced) == {"status": "ok"}


def test_parse_json_response_strips_plain_code_fence():
    fenced = '```\n{"x": 1}\n```'
    assert parse_json_response(fenced) == {"x": 1}


def test_parse_json_response_rejects_prose_with_embedded_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_json_response('Here is the JSON: {"status": "ok"}')


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        (
            "r1_reasoned.txt",
            {
                "sentiment": "neutral",
                "topics": ["pricing", "performance", "UI"],
                "summary": "The pricing is fair and performance is excellent, but the user interface is outdated.",
            },
        ),
        (
            "r1_raw.txt",
            {
                "sentiment": "neutral",
                "topics": ["release speed", "onboarding documentation"],
                "summary": "Praised the new release's speed but criticized confusing onboarding documentation.",
            },
        ),
        (
            "r1_extract.txt",
            {
                "sentiment": "neutral",
                "topics": ["checkout", "support"],
                "summary": "Criticizes the slow and buggy checkout process but praises the friendly and responsive support team.",
            },
        ),
    ],
)
def test_parse_json_response_current_fixture_successes(fixture_name, expected):
    assert parse_json_response((FIXTURES_DIR / fixture_name).read_text(encoding="utf-8")) == expected


def test_parse_json_response_current_fixture_fenced_prose_fails():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_json_response((FIXTURES_DIR / "r1_fenced.txt").read_text(encoding="utf-8"))


def test_validate_json_schema_passes():
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {"status": {"const": "ok"}},
    }

    validate_json_schema({"status": "ok"}, schema)


def test_validate_json_schema_formats_path_and_label():
    schema = {
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "properties": {
                    "promises": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "status": {"enum": ["pending", "fulfilled"]},
                            },
                        },
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError) as exc_info:
        validate_json_schema(
            {"data": {"promises": [{"status": "done"}]}},
            schema,
            label="State patch failed validation",
        )

    message = str(exc_info.value)
    assert message.startswith("State patch failed validation: data.promises.0.status:")
    assert "'done' is not one of" in message


def test_validate_json_schema_without_path_uses_message():
    schema = {"type": "object", "required": ["name"]}

    with pytest.raises(ValueError, match="'name' is a required property"):
        validate_json_schema({}, schema)


def test_load_prompt_reads_text(tmp_path):
    path = tmp_path / "prompt.md"
    path.write_text("Use strict JSON.", encoding="utf-8")

    assert load_prompt(path) == "Use strict JSON."


def test_load_schema_reads_json_object(tmp_path):
    schema = {"type": "object"}
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")

    assert load_schema(path) == schema


def test_load_schema_rejects_invalid_json(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        load_schema(path)


def test_load_schema_rejects_non_object(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must be an object"):
        load_schema(path)


class SyncFakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class AsyncFakeClient(SyncFakeClient):
    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_structured_complete_accepts_sync_client():
    async def _run():
        client = SyncFakeClient('{"ok": true}')
        messages = [{"role": "user", "content": "Return JSON."}]

        response = await structured_complete(client, {"temperature": 0}, "commodity", messages)

        assert response == '{"ok": true}'
        assert client.calls == [
            {
                "messages": messages,
                "config": {"temperature": 0},
                "tier": "commodity",
            }
        ]

    asyncio.run(_run())


def test_structured_complete_accepts_async_client():
    async def _run():
        client = AsyncFakeClient('{"ok": true}')

        response = await structured_complete(client, {}, "quality", [])

        assert response == '{"ok": true}'

    asyncio.run(_run())


def test_structured_complete_rejects_non_text_response():
    async def _run():
        client = SyncFakeClient({"content": "not plain text"})

        with pytest.raises(ValueError, match="plain text"):
            await structured_complete(client, {}, "commodity", [])

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# structured_call tests
# ---------------------------------------------------------------------------

SIMPLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status"],
    "properties": {
        "status": {"enum": ["ok", "error"]},
        "detail": {"type": "string"},
    },
}


class SequentialFakeClient:
    """Returns responses from a list, one per call."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_structured_call_success_on_first_attempt():
    async def _run():
        client = SyncFakeClient('{"status": "ok"}')
        result = await structured_call(
            client, {}, "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="What is the status?",
        )
        assert result.success
        assert result.data == {"status": "ok"}
        assert result.retries == 0
        assert result.error is None

    asyncio.run(_run())


def test_structured_call_leaves_config_unchanged_when_json_mode_off():
    async def _run():
        client = SyncFakeClient('{"status": "ok"}')
        config = {"temperature": 0.2}

        result = await structured_call(
            client,
            config,
            "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="What is the status?",
        )

        assert result.success
        assert client.calls[0]["config"] is config
        assert "json_mode" not in client.calls[0]["config"]
        assert config == {"temperature": 0.2}

    asyncio.run(_run())


def test_structured_call_adds_json_mode_to_config_when_enabled():
    async def _run():
        client = SyncFakeClient('{"status": "ok"}')
        config = {"temperature": 0.2}

        result = await structured_call(
            client,
            config,
            "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="What is the status?",
            json_mode=True,
        )

        assert result.success
        assert client.calls[0]["config"] is not config
        assert client.calls[0]["config"]["json_mode"] is True
        assert config == {"temperature": 0.2}

    asyncio.run(_run())


def test_structured_call_adds_json_mode_to_dataclass_config_when_enabled():
    """json_mode=True with a dataclass config must use dataclasses.replace, not dict()."""
    import dataclasses

    @dataclasses.dataclass
    class FakeConfig:
        temperature: float = 0.5
        json_mode: bool = False

    async def _run():
        client = SyncFakeClient('{"status": "ok"}')
        config = FakeConfig(temperature=0.5)

        result = await structured_call(
            client,
            config,
            "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="What is the status?",
            json_mode=True,
        )

        assert result.success
        sent_config = client.calls[0]["config"]
        assert sent_config is not config
        assert isinstance(sent_config, FakeConfig)
        assert sent_config.json_mode is True
        assert config.json_mode is False

    asyncio.run(_run())


def test_structured_call_retries_on_validation_failure():
    async def _run():
        client = SequentialFakeClient([
            '{"status": "bad"}',       # fails enum validation
            '{"status": "ok"}',        # passes
        ])
        result = await structured_call(
            client, {}, "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="What is the status?",
            max_retries=1,
        )
        assert result.success
        assert result.data == {"status": "ok"}
        assert result.retries == 1
        assert len(client.calls) == 2
        # The retry message should contain the validation error.
        retry_messages = client.calls[1]["messages"]
        assert any("failed validation" in m["content"] for m in retry_messages)

    asyncio.run(_run())


def test_structured_call_fails_after_exhausting_retries():
    async def _run():
        client = SyncFakeClient('{"status": "bad"}')  # always invalid
        result = await structured_call(
            client, {}, "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="What is the status?",
            max_retries=1,
        )
        assert not result.success
        assert result.data is None
        assert result.retries == 1
        assert result.error is not None
        assert "bad" in result.error or "not one of" in result.error

    asyncio.run(_run())


def test_structured_call_no_retries():
    async def _run():
        client = SyncFakeClient('not json')
        result = await structured_call(
            client, {}, "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="go",
            max_retries=0,
        )
        assert not result.success
        assert result.retries == 0

    asyncio.run(_run())


def test_structured_call_includes_examples_in_prompt():
    async def _run():
        client = SyncFakeClient('{"status": "ok"}')
        result = await structured_call(
            client, {}, "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="Return JSON.",
            user_prompt="go",
            examples=[
                {"input": "Is it ok?", "output": {"status": "ok"}},
                Example(input="Is it bad?", output={"status": "error"}),
            ],
        )
        assert result.success
        # Verify examples were in the system prompt.
        system_msg = client.calls[0]["messages"][0]["content"]
        assert "Example 1:" in system_msg
        assert "Example 2:" in system_msg
        assert '"status": "ok"' in system_msg
        assert "Is it bad?" in system_msg

    asyncio.run(_run())


def test_structured_call_schema_in_system_prompt():
    async def _run():
        client = SyncFakeClient('{"status": "ok"}')
        await structured_call(
            client, {}, "commodity",
            schema=SIMPLE_SCHEMA,
            system_prompt="You are a helper.",
            user_prompt="go",
        )
        system_msg = client.calls[0]["messages"][0]["content"]
        assert "JSON Schema" in system_msg
        assert '"status"' in system_msg

    asyncio.run(_run())
