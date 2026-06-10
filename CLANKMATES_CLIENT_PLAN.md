# toolkit.clankmates_client

## Context

Two sibling projects need to talk to Clankmates: the **Diplomat negotiation arena** (`p:\shared\diplomat\CLANKMATES_ARENA_PLAN.md`) and the **Clanker Courts AI agent** (`p:\shared\clankercourts\PROJECT.md:21,49`). Both are being built in parallel, so the toolkit second-consumer rule is already satisfied.

`p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\` already contains a working, tested Python wrapper around the `clankm` CLI plus generic message helpers. The wrapper is ~150 clean lines; the supporting helpers (message decoders, cursor utilities, peer-DM screening) are equally generic.

This plan stands up `toolkit.clankmates_client` as a new toolkit module, vendoring the existing wrapper and extending it with the host-side operations the player client doesn't exercise.

**Vendor source:** `p:\shared\clanker-courts-player-client\` at HEAD as of 2026-06-10 (operator confirmed it may shift before public launch — we track upstream when it moves).

**Consumers (at module ship time):**
- Diplomat — arena host + arena player (`CLANKMATES_ARENA_PLAN.md` Phases C–G depend on this)
- Clanker Courts — future `game_transport` Clankmates adapter (`p:\shared\clankercourts\PROJECT.md:21,49`)

## Scope

**In scope:** everything generic about Clankmates I/O that both consumers need.

- Subprocess wrapper around `clankm` (player-side ops, vendored from upstream).
- Host-side ops not in the upstream player client: post publishing, public-post listing, channel + token management, typed-inbox schema management.
- Message decoders (`decode_clankmates_message`, phase-report extraction, peer-diplomacy filtering).
- Thread-cursor and processed-message-ID tracking helpers.
- Peer-DM screening rules (spoofing checks, untrusted-instruction defense).

**Out of scope** (game-specific, lives in each consumer):
- Arena protocol message types (`move`, `round_report`, `arena_manifest`) — Diplomat-side.
- Game schemas (negotiation issues vs map orders) — per-consumer.
- The `Transport` Protocol / `game_transport` interface adapters — per-consumer.
- Host application (state machine, scoring, persistence) — Diplomat-side for the arena; Viktor's Elixir server for CC.
- Strategy / autoplayer logic — per-consumer.

## Approach

Six phases, each loop-sized. Heavy reuse: Phase 1 is mostly a copy-and-attribute; Phases 3–5 port existing patterns from the player client.

### Phase 1 — Module skeleton + vendored player-side wrapper

**Build:**
- `p:\shared\toolkit\src\toolkit\clankmates_client\__init__.py` — re-exports public API.
- `p:\shared\toolkit\src\toolkit\clankmates_client\subprocess.py` — vendor `clankmates.py` from the player-client repo verbatim. Preserve `ClankmatesError` shape and `_run_json` pattern. Add module docstring with `SOURCE:` attribution + commit hash + date.
- `p:\shared\toolkit\ARCH_clankmates_client.md` — full module contract. Public API table covering all six methods, types, inputs/outputs, state, usage example. Mirrors `ARCH_telegram_client.md` shape.

**Vendored methods** (signatures preserved from `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\clankmates.py`):

```python
class ClankmatesClient:
    def __init__(self, *, clankm_path: str = "clankm", runner=None, timeout: float = 30): ...
    def whoami(self, profile: str) -> dict: ...
    def list_threads(self, profile: str, status: str = "all") -> dict: ...
    def show_thread(self, profile: str, thread_id: str, *, limit: int = 10, cursor: str | None = None) -> dict: ...
    def archive_thread(self, profile: str, thread_id: str) -> dict: ...
    def send(self, profile: str, recipient: str, body: dict) -> dict: ...
    def reply(self, profile: str, thread_id: str, body: dict) -> dict: ...
```

**Tests:** `p:\shared\toolkit\tests\clankmates_client\test_subprocess.py` — port upstream's `tests/test_clankmates.py` with a fake `runner`. All vendored methods covered.

### Phase 2 — Host-side operations

**Discovered surface** (from `p:\shared\diplomat\skill.md` + `clankm inbox schema --help` screenshot + Phase A of the arena plan):

```python
class ClankmatesClient:
    # Posts & feed
    def post_publish(self, profile: str, channel: str, body: str) -> dict: ...
    def post_public_list(self, profile: str, handle: str, channel: str, *, limit: int = 10) -> dict: ...

    # Channel + key management (master-key paths)
    def channel_create(self, profile: str, *, name: str, description: str | None = None) -> dict: ...
    def channel_token_issue(self, profile: str, channel: str, *, name: str) -> dict: ...

    # Typed inbox schemas
    def schema_set(self, profile: str, *, channel: str | None = None, account: bool = False, schema: dict) -> dict: ...
    def schema_show(self, profile: str, *, channel: str | None = None, account: bool = False) -> dict: ...
    def schema_remove(self, profile: str, *, channel: str | None = None, account: bool = False) -> dict: ...
    def schema_acceptance(self, profile: str, *, channel: str | None = None, account: bool = False, accept_external: bool) -> dict: ...
```

**Pre-flight requirement:** the arena plan's Phase A (host-side CLI smoke) must complete first so we know the exact `clankm` flag set for each host-side subcommand. `p:\shared\diplomat\CLANKMATES_NOTES.md` is the reference this phase codes against.

**Tests:** `p:\shared\toolkit\tests\clankmates_client\test_host_ops.py` — fake `runner` covering each new method, schema-payload encoding, account-vs-channel target switch, error response shapes.

### Phase 3 — `decode` submodule

**Build:** `p:\shared\toolkit\src\toolkit\clankmates_client\decode.py` — port from `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\messages.py`.

**Generic helpers** (game-agnostic versions):

```python
def decode_clankmates_message(message: dict) -> dict:
    """Normalize a raw Clankmates message into {message_id, thread_id, timestamp, body, raw}.
    Parses body as JSON when possible. Pure / no I/O."""

def message_timestamp(message: dict) -> str | None:
    """Extract ISO timestamp from any of the known Clankmates timestamp field names."""

def filter_by_body_type(messages: list[dict], *, type_value: str, **body_filters) -> list[dict]:
    """Filter to messages whose decoded body has type == type_value and matching extra body fields."""

def latest_by_timestamp(messages: list[dict]) -> dict | None:
    """Sort by Clankmates timestamp, return latest. None if empty."""
```

**Game-specific helpers** stay in each consumer (Diplomat's `round_report` parsing, CC's `phase_report` extraction).

**Tests:** `p:\shared\toolkit\tests\clankmates_client\test_decode.py` using fixtures vendored from `p:\shared\clanker-courts-player-client\tests\fixtures\*.json` as raw payloads.

### Phase 4 — `cursor` submodule

**Build:** `p:\shared\toolkit\src\toolkit\clankmates_client\cursor.py` — extract the thread-cursor and processed-ID patterns currently inlined in `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\state_store.py`.

**API:**

```python
class ThreadCursorStore:
    """JSON-backed persistence for {thread_id: (last_cursor, last_processed_message_id)} pairs.
    Restart-safe so consumers don't re-process history."""
    def __init__(self, path: Path): ...
    def get(self, thread_id: str) -> CursorState | None: ...
    def advance(self, thread_id: str, *, cursor: str, last_message_id: str) -> None: ...
    def known_thread_ids(self) -> list[str]: ...

def filter_unseen(messages: list[dict], *, processed_ids: set[str]) -> list[dict]:
    """Return messages whose id is not in processed_ids, in original order."""
```

**Tests:** `p:\shared\toolkit\tests\clankmates_client\test_cursor.py` — tempdir-backed `ThreadCursorStore` round-trip, restart-replay scenarios, unseen-filter idempotency.

### Phase 5 — `screen` submodule

**Build:** `p:\shared\toolkit\src\toolkit\clankmates_client\screen.py` — extract the peer-DM screening rules from `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\SKILL.md:140-164`.

**API:**

```python
@dataclass(frozen=True)
class ScreeningResult:
    accepted: bool
    reasons: tuple[str, ...]   # rejection rationale, empty when accepted

def screen_peer_message(
    message: dict,
    *,
    expected_to: str,                # this player's Clankmates address
    expected_body_type: str,         # e.g. "diplomacy_message"
    expected_extra_fields: dict[str, str] | None = None,   # game_id, etc.
    known_active_senders: set[str],  # Clankmates addresses from setup/state
) -> ScreeningResult:
    """Apply the standard screening checks:
       - body type matches
       - to_player_id matches expected_to
       - Clankmates sender matches body's claimed from_player_id
       - sender is in known_active_senders
       - extra body fields match expected (game_id, etc.)"""
```

Game-specific extensions (prompt-injection content filtering, persona-specific rules) stay in consumers.

**Tests:** `p:\shared\toolkit\tests\clankmates_client\test_screen.py` — happy path + each failure mode + spoofing case (sender ≠ body's claimed from).

### Phase 6 — Governance + integration check

**Toolkit governance updates:**
- `p:\shared\toolkit\ARCHITECTURE.md` — add `clankmates_client` to Component Map (leaf module, no toolkit deps) and Implementation Sequence.
- `p:\shared\toolkit\VALIDATION_NOTES.md` — new section listing Diplomat (arena) and Clanker Courts (future game_transport adapter) as the two consumers, with the contract surfaces each one exercises.
- `p:\shared\toolkit\rules\toolkit.md` — add `clankmates_client` to the "Leaf modules" list with one-line description.
- `p:\shared\toolkit\README.md` / `TOOLKIT_REFERENCE.md` — add module entry if those docs maintain a module index.

**Cross-project consumer check:** before declaring the module complete, run the `command://integration-check` flow against the Diplomat arena's planned C2 adapter contract (from `CLANKMATES_ARENA_PLAN.md` Phase C) to confirm the public API actually satisfies what the adapter needs. Stub the CC `game_transport` adapter contract from `p:\shared\clankercourts\ARCH_server_report_parser.md`'s adapter-boundary description as the second consumer check.

**Full test suite green** after each phase. Toolkit's existing test suite is the baseline.

## Critical files

**Read before implementing each phase:**

- Phase 1: `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\clankmates.py` (vendor source), `p:\shared\clanker-courts-player-client\tests\test_clankmates.py` (test pattern), `p:\shared\toolkit\ARCH_telegram_client.md` (toolkit module shape reference)
- Phase 2: `p:\shared\diplomat\CLANKMATES_NOTES.md` (arena Phase A output — exact host-side CLI surface), `p:\shared\diplomat\for-clankers.md`, `p:\shared\diplomat\skill.md`
- Phase 3: `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\messages.py` (port source), `p:\shared\clanker-courts-player-client\tests\fixtures\*.json` (fixture seed)
- Phase 4: `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\scripts\clanker_courts_player\state_store.py` (extract source), `p:\shared\clanker-courts-player-client\tests\test_state_store.py` (test patterns)
- Phase 5: `p:\shared\clanker-courts-player-client\skills\clanker-courts-operator\SKILL.md:140-164` (rule source)
- Phase 6: `p:\shared\toolkit\ARCHITECTURE.md`, `p:\shared\toolkit\VALIDATION_NOTES.md`, `p:\shared\toolkit\rules\toolkit.md`, `p:\shared\diplomat\CLANKMATES_ARENA_PLAN.md` (Phase C contract — the integration check target)

**New files created:**

- `p:\shared\toolkit\src\toolkit\clankmates_client\__init__.py` (Phase 1)
- `p:\shared\toolkit\src\toolkit\clankmates_client\subprocess.py` (Phase 1)
- `p:\shared\toolkit\src\toolkit\clankmates_client\decode.py` (Phase 3)
- `p:\shared\toolkit\src\toolkit\clankmates_client\cursor.py` (Phase 4)
- `p:\shared\toolkit\src\toolkit\clankmates_client\screen.py` (Phase 5)
- `p:\shared\toolkit\ARCH_clankmates_client.md` (Phase 1, expanded in 2/3/4/5)
- `p:\shared\toolkit\tests\clankmates_client\test_subprocess.py` (Phase 1)
- `p:\shared\toolkit\tests\clankmates_client\test_host_ops.py` (Phase 2)
- `p:\shared\toolkit\tests\clankmates_client\test_decode.py` (Phase 3)
- `p:\shared\toolkit\tests\clankmates_client\test_cursor.py` (Phase 4)
- `p:\shared\toolkit\tests\clankmates_client\test_screen.py` (Phase 5)

**Existing files updated:**

- `p:\shared\toolkit\ARCHITECTURE.md` (Phase 6)
- `p:\shared\toolkit\VALIDATION_NOTES.md` (Phase 6)
- `p:\shared\toolkit\rules\toolkit.md` (Phase 6)

## Verification

Per-phase exit criteria:

- **1:** `pytest tests/clankmates_client/test_subprocess.py` green; module imports cleanly; vendored methods match upstream behavior on the ported test cases; `ARCH_clankmates_client.md` skeleton published.
- **2:** `pytest tests/clankmates_client/test_host_ops.py` green; manual round-trip of every host-side method against the live Clankmates service using a throwaway profile (depends on arena Phase A having identified the CLI surface).
- **3:** `pytest tests/clankmates_client/test_decode.py` green; helpers correctly decode every fixture in the vendored fixture set.
- **4:** `pytest tests/clankmates_client/test_cursor.py` green; tempdir round-trip works; restart-replay scenario (kill process, restart, verify no message replay) verified.
- **5:** `pytest tests/clankmates_client/test_screen.py` green; each documented screening rule has both an accept-case and a reject-case test.
- **6:** Full toolkit `pytest` green; `ARCHITECTURE.md` + `VALIDATION_NOTES.md` + `rules/toolkit.md` updated; integration-check flow run against Diplomat arena Phase C adapter contract returns no gaps; CC `game_transport` adapter contract check returns no gaps.

## Upstream tracking

Viktor (`p:\shared\clanker-courts-player-client` maintainer) is finishing local testing and *"may update the server and/or these skills"* before going public. Process:

- Vendor commit hash recorded in `clankmates_client/subprocess.py` module docstring.
- After Viktor's public launch, diff upstream against the vendored version, port relevant changes.
- If Viktor extracts `clankmates.py` into its own PyPI package later, swap the vendored copy for the dependency (small follow-up; the API surface is stable).

## Out of scope (explicit non-goals)

- Async I/O — current shape is sync subprocess calls (matches upstream). Consumers wrap in `asyncio.to_thread` if they need async semantics.
- Multiple-profile management — `--profile <name>` selects a Clankmates-local config; profile creation is a human action (handled in `clankm config init`), not a method on this client.
- Retry / backoff — left to consumers. Different consumers want different policies (Diplomat host has long-lived polling, CC player has phase-bounded retry); a one-size policy here would force the wrong tradeoff on at least one.
- Schema validation of typed payloads before send — `clankm` server validates against the typed-inbox schema; double-validating in the client is duplicative.
- Upstreaming changes back to `clanker-courts-player-client` — not blocked, but not required for v1.
