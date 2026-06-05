# ARCH: Coaching

## Purpose

Tag-based operator-input parser. Reads lines like `PRIORITY: secure alliance`
or `/preview` and returns either a typed `CoachingEvent` (tag → routed to a
consumer-defined queue with a canonical type) or a `Command` (slash-command
name + parsed args). Tag vocabulary and command list are loaded from a YAML
config so consumers can extend the surface without code changes.

**Provenance:** Extracted from Diplomat's `modules/coaching` in 2026-06-05.
Second-consumer rule satisfied by Clanker Courts (incoming).

## Public API

### TaggedCoachingParser

```python
class TaggedCoachingParser:
    def __init__(self, routes_path: str | Path) -> None
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> TaggedCoachingParser
    def parse(self, raw_input: str) -> CoachingEvent | Command
```

- `__init__(routes_path)` — loads YAML config from disk. Lazy-imports `yaml`;
  raises `ImportError` if PyYAML is not installed.
- `from_config(config)` — dependency-free constructor for callers that
  pre-parse their own config (JSON, env vars, hand-built dict). Does not
  require PyYAML.
- `parse(raw_input)` — classifies one input string. Returns `Command` when
  the input starts with a known slash command; otherwise returns
  `CoachingEvent`. Tag matching is case-insensitive. Unknown tags, malformed
  tag prefixes, and untagged free text all fall through to the `default`
  route with the default `coaching_type`. Unknown slash commands are
  returned as `CoachingEvent` (default route) so they aren't silently
  dropped.

### load_routes_config

```python
def load_routes_config(routes_path: str | Path) -> dict[str, Any]
```

YAML loader exposed for callers that want to inspect or transform the
config before constructing a parser. Lazy-imports `yaml`; raises a clear
`ImportError` with installation guidance if PyYAML is missing.

## Types

```python
@dataclass(frozen=True)
class CoachingEvent:
    coaching_type: str       # canonical tag name (e.g. "PRIORITY", "FREE")
    content: str             # text after the tag prefix (or full text if untagged)
    route: str               # consumer-defined route id

@dataclass(frozen=True)
class Command:
    name: str                # slash command without leading "/"
    args: dict[str, Any]     # {} for most; {"text": ...} for /edit

@dataclass(frozen=True)
class RouteRule:
    coaching_type: str
    route: str
```

## Configuration

YAML config shape:

```yaml
tags:
  <TAG_NAME>:
    route: <consumer-defined-route-id>
    coaching_type: <canonical-name>
  default:                 # required — used for untagged / unknown-tag input
    route: ...
    coaching_type: ...

commands:
  - /<command_name>
  - ...
```

Concrete example (Diplomat):

```yaml
tags:
  PRIORITY:
    route: coaching_queue
    coaching_type: PRIORITY
  INTEL:
    route: state_updater
    coaching_type: INTEL
  default:
    route: coaching_queue
    coaching_type: FREE

commands:
  - /preview
  - /approve
  - /edit
  - /block
```

The `default` entry in `tags` is required. Tags are matched
case-insensitively. Routes are opaque strings — the parser does not
interpret them; consumers route on them.

## Inputs

- Raw operator-input string (one per `parse()` call).
- YAML config file (or pre-parsed dict) defining tag routes + command list,
  loaded once at construction.

## Outputs

- `CoachingEvent` or `Command` per `parse()` call.

Consumer is responsible for dispatching on the result:

- `Command` → dispatch to the consumer's command handler.
- `CoachingEvent` with `route=<X>` → forward to whatever consumer-defined
  pipeline `<X>` identifies (e.g. a state-updater for "INTEL"-style notes,
  a context queue for free-form coaching).

## State

None. `TaggedCoachingParser` is a pure parsing object; the routing table is
loaded once at construction. No I/O after init.

## Usage Example

```python
from toolkit.coaching import TaggedCoachingParser, CoachingEvent, Command

# Construct from YAML (requires pyyaml)
parser = TaggedCoachingParser("config/coaching_routes.yaml")

# Or from a pre-parsed dict (no pyyaml dependency required)
parser = TaggedCoachingParser.from_config({
    "tags": {
        "default": {"route": "coaching_queue", "coaching_type": "FREE"},
        "INTEL":   {"route": "state_updater",  "coaching_type": "INTEL"},
    },
    "commands": ["/preview", "/edit"],
})

# Tagged coaching
result = parser.parse("PRIORITY: Secure alliance with Beta before round 5")
# -> CoachingEvent(coaching_type="PRIORITY",
#                  content="Secure alliance with Beta before round 5",
#                  route="coaching_queue")

# INTEL routes to state updater
result = parser.parse("INTEL: Alpha broke promise to Gamma in round 3")
# -> CoachingEvent(coaching_type="INTEL", content="...", route="state_updater")

# Slash command
result = parser.parse("/preview")
# -> Command(name="preview", args={})

# /edit captures trailing text
result = parser.parse("/edit: Soften the tone in the second paragraph")
# -> Command(name="edit", args={"text": "Soften the tone in the second paragraph"})

# Unknown tag falls through to default
result = parser.parse("MOOD: too soft")
# -> CoachingEvent(coaching_type="FREE", content="MOOD: too soft",
#                  route="coaching_queue")

# Untagged is default-routed free coaching
result = parser.parse("Be careful with Delta")
# -> CoachingEvent(coaching_type="FREE", content="Be careful with Delta",
#                  route="coaching_queue")

# Dispatch pattern
match result:
    case Command(name=name, args=args):
        handle_command(name, args)
    case CoachingEvent(route="state_updater", content=text):
        update_state_from_intel(text)
    case CoachingEvent(route="coaching_queue", coaching_type=tag, content=text):
        queue_for_next_response(tag, text)
```

## Errors

- `__init__` raises `ValueError` if the YAML config is missing required
  sections (`tags`, `tags.default`, `commands`) or contains malformed
  entries.
- `__init__` raises `ValueError` if the routes file cannot be read.
- `load_routes_config` raises `ImportError` if PyYAML is not installed
  (with guidance to use `from_config()` instead).
- `parse()` never raises; unrecognised input returns a `CoachingEvent` on
  the default route.

## Dependencies

- None at import time.
- PyYAML lazy-imported only inside `load_routes_config` (and therefore by
  the path-based `__init__`). The `from_config(dict)` constructor has no
  PyYAML dependency.

## Consumer notes

Consumers typically:

1. Define a routes YAML alongside their config files.
2. Construct the parser at startup.
3. Wire the result of `parse()` into their event/command dispatcher.
4. Use the `coaching_type` field as the canonical tag (suitable for storage,
   filtering, audit).

The parser is intentionally domain-free. Operational policy — how often to
coach, what the route consumers do with `CoachingEvent`s, how `Command`s
modify the agent's state — lives in the consumer.
