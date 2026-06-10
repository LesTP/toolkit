# ARCH: Clankmates Client

## Purpose
Subprocess wrapper around the `clankm` CLI plus generic Clankmates message utilities. This module is a leaf package: it has no toolkit dependencies and is consumed independently by Diplomat and Clanker Courts.

**Provenance:** Phase 1 vendors the player-side wrapper from `clanker-courts-player-client` and preserves the upstream error shape and `_run_json` control flow. Later phases add the generic decode, cursor, and screening helpers.

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

## Types

```python
Runner = Callable[..., subprocess.CompletedProcess[str]]
```

## State

- No persistent state.
- `ClankmatesClient` stores only the configured binary path, runner, and timeout.
- Error instances carry the command and captured subprocess output for debugging and consumer-side JSON logging.

## Usage Example

```python
from toolkit.clankmates_client import ClankmatesClient

client = ClankmatesClient()
profile_info = client.whoami("arena-host")
thread = client.show_thread("arena-host", "thread-123", limit=20)
```

## Notes

- The wrapper stays synchronous to match the upstream player-client behavior.
- Phase 2 will extend this module with host-side operations.
- Phase 3, 4, and 5 will add `decode.py`, `cursor.py`, and `screen.py` respectively.
