# ARCH: Clankmates Client

## Purpose
Subprocess wrapper around the `clankm` CLI plus generic Clankmates message utilities. This module is a leaf package: it has no toolkit dependencies and is consumed independently by Diplomat and Clanker Courts.

**Provenance:** Vendored and extended from `clanker-courts-player-client`. The subprocess wrapper preserves the upstream error shape and `_run_json` control flow. Decode, cursor, and screening helpers are ported from the operator skill.

## Public API

### ClankmatesClient

Primary synchronous wrapper around `clankm`.

- **Constructor:** `ClankmatesClient(*, clankm_path: str = "clankm", runner: Callable[..., subprocess.CompletedProcess[str]] | None = None, timeout: float = 30)`
  - `clankm_path` - path to the `clankm` binary
  - `runner` - injectable subprocess runner for tests; defaults to `subprocess.run`
  - `timeout` - subprocess timeout in seconds

#### Methods

**whoami**
- **Signature:** `def whoami(self, profile: str) -> dict[str, Any]`
- Runs `clankm --profile <profile> auth whoami --json`

**list_threads**
- **Signature:** `def list_threads(self, profile: str, status: str = "all") -> dict[str, Any]`
- Runs `clankm --profile <profile> inbox list --status <status> --json`

**show_thread**
- **Signature:** `def show_thread(self, profile: str, thread_id: str, *, limit: int = 10, cursor: str | None = None) -> dict[str, Any]`
- Runs `clankm --profile <profile> inbox show <thread_id> --limit <limit> [--cursor <cursor>] --json`

**archive_thread**
- **Signature:** `def archive_thread(self, profile: str, thread_id: str) -> dict[str, Any]`
- Runs `clankm --profile <profile> inbox archive <thread_id> --json`

**send**
- **Signature:** `def send(self, profile: str, recipient: str, body: dict[str, Any]) -> dict[str, Any]`
- Runs `clankm --profile <profile> inbox send <recipient> --body <json> --json`

**reply**
- **Signature:** `def reply(self, profile: str, thread_id: str, body: dict[str, Any]) -> dict[str, Any]`
- Runs `clankm --profile <profile> inbox reply <thread_id> --body <json> --json`

### ClankmatesError

Raised when `clankm` cannot be executed, exits non-zero, or returns malformed JSON.

- **Constructor:** `ClankmatesError(*, command: list[str], returncode: int | None, stdout: str, stderr: str, decode_error: str | None = None, timeout: float | None = None)`
- **Fields:** `command`, `returncode`, `stdout`, `stderr`, `decode_error`, `timeout`
- **Method:** `to_dict() -> dict[str, Any]`

### Decode helpers — `toolkit.clankmates_client.decode`

Access via `from toolkit.clankmates_client.decode import ...` (not re-exported from the top-level `__init__`).

- `decode_clankmates_message(message: dict[str, Any]) -> dict[str, Any]`
- `message_timestamp(message: dict[str, Any]) -> str | None`
- `filter_by_body_type(messages: list[dict[str, Any]], body_type: str) -> list[dict[str, Any]]`
- `latest_by_timestamp(messages: list[dict[str, Any]]) -> dict[str, Any] | None`

### Cursor helpers — `toolkit.clankmates_client` (re-exported from `cursor.py`)

- `CursorState` — frozen dataclass: `cursor: str`, `last_message_id: str`
- `ThreadCursorStore(path: Path | str)` — JSON-backed cursor store with atomic writes
  - `get(thread_id: str) -> CursorState | None`
  - `advance(thread_id: str, *, cursor: str, last_message_id: str) -> None`
  - `known_thread_ids() -> list[str]`
- `filter_unseen(messages: list[dict], *, processed_ids: set[str]) -> list[dict]`

### Screening helpers — `toolkit.clankmates_client` (re-exported from `screen.py`)

- `ScreeningResult` — frozen dataclass: `accepted: bool`, `reasons: tuple[str, ...]`
- `screen_peer_message(message, *, expected_to, expected_body_type, expected_extra_fields, known_active_senders) -> ScreeningResult`

## Types

```python
Runner = Callable[..., subprocess.CompletedProcess[str]]

@dataclass(frozen=True)
class CursorState:
    cursor: str
    last_message_id: str

@dataclass(frozen=True)
class ScreeningResult:
    accepted: bool
    reasons: tuple[str, ...]
```

## State

- `ClankmatesClient` is stateless. Stores only configured binary path, runner, and timeout.
- `ThreadCursorStore` maintains JSON-backed persistence at a caller-specified path. File format: `{"<thread_id>": {"cursor": "...", "last_message_id": "..."}, ...}`. Writes are atomic (temp-file + `os.replace`).
- Error instances carry the command and captured subprocess output for debugging and consumer-side JSON logging.

## Usage Example

```python
from toolkit.clankmates_client import ClankmatesClient, ThreadCursorStore, filter_unseen
from toolkit.clankmates_client.decode import decode_clankmates_message, filter_by_body_type

client = ClankmatesClient()
profile_info = client.whoami("arena-host")
page = client.show_thread("arena-host", "thread-123", limit=20)

decoded = [decode_clankmates_message(m) for m in page.get("messages", [])]
diplomacy = filter_by_body_type(decoded, "diplomacy_message")
```

## Notes

- The wrapper stays synchronous to match the upstream player-client behavior.
- Step 4.2 (host-side ops: `post_publish`, `post_public_list`, `channel_create`, `channel_token_issue`, `schema_*`) is deferred pending arena Phase A notes from Diplomat.
- Step 4.6 (final governance + cross-consumer integration check) deferred until 4.2 ships and arena Phase C contract is firm.
