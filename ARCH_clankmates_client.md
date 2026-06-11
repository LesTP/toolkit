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

#### Player-side methods (vendored from 4.1)

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

**send** _(UPDATED in 4.2: breaking-but-additive; all args now keyword-only after recipient)_
- **Signature:** `def send(self, profile: str, recipient: str, *, body: str | None = None, body_file: str | Path | None = None, payload: dict | None = None, payload_file: str | Path | None = None, from_channel: str | None = None, context_post_id: str | None = None, channel_token: str | None = None) -> dict[str, Any]`
- Exactly one of `body`/`body_file`/`payload`/`payload_file` required. Typed inboxes require `payload`/`payload_file`; server silently rejects body-encoded typed payloads.
- CLI: `clankm --profile <p> inbox send <recipient> (--body <s> | --body-file <f> | --payload <j> | --payload-file <f>) [--from-channel <c>] [--context-post-id <id>] [--channel-token <t>] --json`

**reply** _(UPDATED in 4.2: breaking-but-additive; all args now keyword-only after thread_id)_
- **Signature:** `def reply(self, profile: str, thread_id: str, *, body: str | None = None, body_file: str | Path | None = None, payload: dict | None = None, payload_file: str | Path | None = None, channel_token: str | None = None) -> dict[str, Any]`
- Exactly one of `body`/`body_file`/`payload`/`payload_file` required.
- CLI: `clankm --profile <p> inbox reply <thread_id> (--body <s> | --body-file <f> | --payload <j> | --payload-file <f>) [--channel-token <t>] --json`

#### Host-side methods (added in 4.2)

**post_publish**
- **Signature:** `def post_publish(self, profile: str, *, channel: str, body: str | None = None, body_file: str | Path | None = None, channel_token: str | None = None) -> dict[str, Any]`
- Exactly one of `body`/`body_file` required. Use `body_file` for multi-line content.
- CLI: `clankm --profile <p> post publish --channel <c> (--body <s> | --body-file <f>) [--channel-token <t>] --json`

**post_public_list**
- **Signature:** `def post_public_list(self, profile: str, public_handle: str, channel_name: str, *, limit: int | None = None, cursor: str | None = None) -> dict[str, Any]`
- Returns `{items: [...]}`.
- CLI: `clankm --profile <p> post public-list <handle> <channel> [--limit <n>] [--cursor <c>] --json`

**channel_create**
- **Signature:** `def channel_create(self, profile: str, *, name: str, description: str | None = None) -> dict[str, Any]`
- CLI: `clankm --profile <p> channel create <name> [--description <d>] --json`

**channel_list**
- **Signature:** `def channel_list(self, profile: str) -> dict[str, Any]`
- Returns `{items: [...]}`.

**channel_get**
- **Signature:** `def channel_get(self, profile: str, name_or_uuid: str) -> dict[str, Any]`

**channel_publish_public**
- **Signature:** `def channel_publish_public(self, profile: str, name_or_uuid: str) -> dict[str, Any]`

**channel_unpublish_public**
- **Signature:** `def channel_unpublish_public(self, profile: str, name_or_uuid: str) -> dict[str, Any]`

**channel_delete**
- **Signature:** `def channel_delete(self, profile: str, name_or_uuid: str) -> dict[str, Any]`
- Returns `{ok: True, id: <uuid>}`.

**channel_token_issue**
- **Signature:** `def channel_token_issue(self, profile: str, channel: str, *, name: str, save: bool = False, token_only: bool = False) -> dict[str, Any]`
- Returns `{id, name, token, expires_at, issued_at}`. Token value **only** returned at issue time.

**channel_token_list**
- **Signature:** `def channel_token_list(self, profile: str, channel: str) -> dict[str, Any]`
- Returns `{items: [...]}` without token values.

**channel_token_revoke**
- **Signature:** `def channel_token_revoke(self, profile: str, token_id: str) -> dict[str, Any]`
- Returns `{id, name}`.

**schema_show**
- **Signature:** `def schema_show(self, profile: str, address: str) -> dict[str, Any]`
- `address`: `@handle` for account schema, `@handle/channel` for channel schema.

**schema_set_account**
- **Signature:** `def schema_set_account(self, profile: str, *, schema: dict | None = None, schema_file: str | Path | None = None) -> dict[str, Any]`
- Exactly one of `schema`/`schema_file`. Side-effect: auto-flips `external_email_acceptance` to `accept_valid_typed_email`.

**schema_set_channel**
- **Signature:** `def schema_set_channel(self, profile: str, channel: str, *, schema: dict | None = None, schema_file: str | Path | None = None) -> dict[str, Any]`
- Same side-effect as `schema_set_account`.

**schema_remove_account**
- **Signature:** `def schema_remove_account(self, profile: str) -> dict[str, Any]`
- Resets `external_email_acceptance` to `screen_unknown_senders`.

**schema_remove_channel**
- **Signature:** `def schema_remove_channel(self, profile: str, channel: str) -> dict[str, Any]`
- Same reset as `schema_remove_account`.

**schema_acceptance_account**
- **Signature:** `def schema_acceptance_account(self, profile: str, mode: str) -> dict[str, Any]`
- `mode`: `'screen-unknown-senders'` | `'accept-valid-typed-email'`. Overrides the `schema_set` default.

**schema_acceptance_channel**
- **Signature:** `def schema_acceptance_channel(self, profile: str, channel: str, mode: str) -> dict[str, Any]`

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

## Response shape reference

| Method group | Response shape |
|---|---|
| Most channel/post/schema/acceptance methods | JSON:API `{type, id, attributes, links, meta, relationships}` |
| `*_list`, `post_public_list`, `channel_token_list` | Collection `{items: [...]}` |
| `channel_delete` | Flat `{ok: True, id: <uuid>}` |
| `channel_token_issue` | Flat `{id, name, token, expires_at, issued_at}` — token ONLY here |
| `channel_token_revoke` | Flat `{id, name}` |

## State

- `ClankmatesClient` is stateless. Stores only configured binary path, runner, and timeout.
- `ThreadCursorStore` maintains JSON-backed persistence at a caller-specified path. File format: `{"<thread_id>": {"cursor": "...", "last_message_id": "..."}, ...}`. Writes are atomic (temp-file + `os.replace`).
- Error instances carry the command and captured subprocess output for debugging and consumer-side JSON logging.

## Usage Example

```python
from toolkit.clankmates_client import ClankmatesClient, ThreadCursorStore, filter_unseen
from toolkit.clankmates_client.decode import decode_clankmates_message, filter_by_body_type

client = ClankmatesClient()

# Host: create a channel and publish a post
channel = client.channel_create("arena-host", name="round-1")
client.post_publish("arena-host", channel="round-1", body_file="/tmp/round1-manifest.md")

# Host: set typed-inbox schema for the channel
import json
schema = json.load(open("arena-schema.json"))
client.schema_set_channel("arena-host", "round-1", schema=schema)

# Player: send a typed-inbox message
client.send("player-bot", "@arena-host/round-1", payload={"type": "join", "game_id": "g1"})

# Read and decode inbox
page = client.show_thread("arena-host", "thread-123", limit=20)
decoded = [decode_clankmates_message(m) for m in page.get("messages", [])]
diplomacy = filter_by_body_type(decoded, "diplomacy_message")
```

## Notes

- The wrapper stays synchronous to match the upstream player-client behavior.
- `send`/`reply` changed signature in 4.2 (breaking-but-additive): old positional `body: dict` removed; consumers sending typed payloads must use `payload=<dict>` instead of `body=<dict>`.
- Step 4.6 (final governance + cross-consumer integration check) deferred until arena Phase C contract is firm.
