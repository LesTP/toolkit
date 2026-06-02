import json
from datetime import datetime

from toolkit.gateway import Gateway, GatewayConfig, OutboundMessage, PlatformConfig


def _log_platform(
    log_path: str, *, output_formats: list[str] | None = None
) -> PlatformConfig:
    return PlatformConfig(
        name="log",
        adapter_type="log",
        credentials={},
        params={"log_path": log_path},
        output_formats=output_formats or ["text"],
    )


def _gateway(
    log_path: str,
    *,
    listen: bool = True,
    output_formats: list[str] | None = None,
) -> Gateway:
    return Gateway(
        GatewayConfig(
            platforms=[_log_platform(log_path, output_formats=output_formats)],
            default_platform="log",
            listen=listen,
        ),
        lambda _: None,
        lambda _: None,
    )


def _read_records(log_path) -> list[dict]:
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]


def test_log_adapter_creates_file_and_appends_records(tmp_path) -> None:
    log_path = tmp_path / "nested" / "gateway.jsonl"
    gateway = _gateway(str(log_path))

    first = gateway.send(OutboundMessage(content="first", platform="log"))
    second = gateway.send(OutboundMessage(content="second", platform="log"))

    assert first.message_id == "log-1"
    assert second.message_id == "log-2"
    assert [record["content"] for record in _read_records(log_path)] == [
        "first",
        "second",
    ]


def test_log_adapter_serializes_message_metadata(tmp_path) -> None:
    log_path = tmp_path / "gateway.jsonl"
    gateway = _gateway(str(log_path), output_formats=["text", "markdown"])

    gateway.send(
        OutboundMessage(
            content="markdown body",
            platform="log",
            format="markdown",
            reply_to="in-1",
            intent_tag="synthesis",
            metadata={"source": "generator", "confidence": 0.91},
        )
    )

    record = _read_records(log_path)[0]
    assert datetime.fromisoformat(record["timestamp"])
    assert record["platform"] == "log"
    assert record["message_id"] == "log-1"
    assert record["content"] == "markdown body"
    assert record["format"] == "markdown"
    assert record["reply_to"] == "in-1"
    assert record["intent_tag"] == "synthesis"
    assert record["metadata"] == {"source": "generator", "confidence": 0.91}


def test_log_adapter_listener_has_no_inbound_side_effects(tmp_path) -> None:
    log_path = tmp_path / "gateway.jsonl"
    gateway = _gateway(str(log_path))

    gateway.start_listener()
    gateway.stop_listener()

    assert not log_path.exists()
    assert gateway._listening_platforms == set()
