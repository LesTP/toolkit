"""Tests for toolkit.structured_llm."""

from __future__ import annotations

import asyncio
import json

import pytest

from toolkit.structured_llm import (
    load_prompt,
    load_schema,
    parse_json_response,
    structured_complete,
    validate_json_schema,
)


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
