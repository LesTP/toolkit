# ARCH: Gateway

> **Provenance:** Extracted from Phosphene's `gateway/` module on 2026-06-02. Public API and behavior unchanged. Phosphene's `ARCH_gateway.md` now redirects here.

## Purpose
Multi-platform message bus for both inbound and outbound communication. Wraps toolkit/telegram_client (and future platform adapters) behind a uniform interface. Inbound: receives human messages and platform signals (reactions, replies), dispatches to a consumer-supplied callback. Outbound: delivers content to the appropriate platform in the correct format. The Gateway is platform-agnostic and project-agnostic — consumers wire their own message handlers and content sources.

## Public API

### Types

```python
@dataclass
class GatewayConfig:
    platforms: list[PlatformConfig]                 # one per connected platform
    default_platform: str                           # platform name for unprompted output delivery
    listen: bool = True                             # whether to listen for inbound messages

@dataclass
class PlatformConfig:
    name: str                                       # identifier: "telegram", "whatsapp", "twitter", "log"
    adapter_type: str                               # adapter implementation to use (same as name, typically)
    credentials: dict                               # platform-specific auth (bot tokens, API keys)
    params: dict = field(default_factory=dict)      # platform-specific settings (chat_id, channel_id, etc.)
    enabled: bool = True
    output_formats: list[str] = field(default_factory=lambda: ["text"])
                                                    # supported output formats: "text", "markdown", "thread", "telegraph"

@dataclass
class InboundMessage:
    content: str                                    # message text
    platform: str                                   # originating platform name
    message_id: str                                 # platform-assigned ID of THIS message (for threading replies via OutboundMessage.reply_to)
    sender: str                                     # platform-specific sender identifier
    timestamp: datetime
    reply_to: str | None = None                     # message_id this replies to (if threaded)
    reactions: list[str] | None = None              # emoji reactions (for feedback signals)
    raw: dict | None = None                         # platform-specific raw payload (for adapter-specific handling)

@dataclass
class OutboundMessage:
    content: str                                    # text content to deliver
    platform: str                                   # target platform name
    format: str = "text"                            # "text", "markdown", "thread", "telegraph"
    reply_to: str | None = None                     # message_id to reply to (if conversational)
    intent_tag: str | None = None                   # from GeneratorOutput — for feedback attribution
    metadata: dict = field(default_factory=dict)    # platform-specific delivery options

@dataclass
class DeliveryResult:
    success: bool
    platform: str
    message_id: str | None                          # platform-assigned message ID (for threading, feedback tracking)
    error: str | None = None

@dataclass
class FeedbackSignal:
    platform: str
    message_id: str                                 # the message that received feedback
    signal_type: str                                # "reaction", "reply", "forward", "ignore"
    value: str | None = None                        # reaction emoji, reply text, etc.
    sender: str
    timestamp: datetime
```

### Constructor

- **Signature:** `Gateway(config: GatewayConfig, on_message: Callable[[InboundMessage], None], on_feedback: Callable[[FeedbackSignal], None])`
- **Parameters:**
  - config: GatewayConfig — platform connections and settings
  - on_message: callback invoked when a human message is received. Typically wired to `orchestrator.trigger("respond", {"message": msg})`.
  - on_feedback: callback invoked when a feedback signal is received (reaction, reply). Typically wired to the Feedback Collector.
- **Errors:**
  - `PlatformConfigError` — unknown adapter_type, missing credentials, or duplicate platform names

### start_listener

- **Signature:** `start_listener() -> None`
- **Parameters:** none
- **Returns:** None. Starts background polling/webhook listeners for all enabled platforms. Non-blocking — runs in a background thread or async loop.
- **Errors:**
  - `PlatformConnectionError` — failed to connect to a platform

### stop_listener

- **Signature:** `stop_listener() -> None`
- **Parameters:** none
- **Returns:** None. Stops all listeners gracefully.

### send

- **Signature:** `send(message: OutboundMessage) -> DeliveryResult`
- **Parameters:**
  - message: OutboundMessage — content, target platform, format, optional reply threading
- **Returns:** DeliveryResult — success/failure, platform-assigned message_id for feedback tracking
- **Errors:**
  - `PlatformNotFoundError` — target platform not configured
  - `FormatNotSupportedError` — requested format not in platform's `output_formats`
  - `DeliveryError` — platform API call failed (network, auth, rate limit). Included in DeliveryResult, not raised.

### send_to_default

- **Signature:** `send_to_default(content: str, format: str = "text", intent_tag: str | None = None) -> DeliveryResult`
- **Parameters:**
  - content: str — text to deliver
  - format: str — output format
  - intent_tag: str | None — from GeneratorOutput, stored in DeliveryResult for feedback attribution
- **Returns:** DeliveryResult
- **Errors:** same as `send`

Convenience method for unprompted output delivery (generation, free-play). Uses `config.default_platform`.

## Platform Adapters

Each adapter translates between the Gateway's uniform types and a platform's specific API. Adding a new platform is additive — implement the adapter interface, register the adapter_type.

### telegram

Wraps toolkit/telegram_client. Primary platform.

- **credentials:** `{"bot_token": str}`
- **params:** `{"chat_id": str}` — the human-facing chat for conversation and output delivery
- **Inbound:** polls for new messages via toolkit/telegram_client. Detects reactions via message edits/reactions API.
- **Outbound formats:**
  - `"text"` — plain text message
  - `"markdown"` — MarkdownV2 via toolkit/telegram_client formatting
  - `"telegraph"` — long content published to Telegraph, link sent to chat (via toolkit/telegram_client overflow)
  - `"thread"` — reply to a specific message_id (for conversational responses)

### log

Local-only adapter for development and debugging. No external API.

- **credentials:** none
- **params:** `{"log_path": str}` — file path for output log
- **Inbound:** none (log adapter is output-only)
- **Outbound:** writes content to a local log file with timestamp and metadata. Always succeeds.

### Future adapters (not implemented yet)

- **whatsapp** — WhatsApp Business API or linked device bridge
- **twitter** — post tweets, receive mentions/replies
- **mastodon** — ActivityPub-based posting and monitoring

## Inputs

- **OutboundMessage** — from the Output Router, carrying formatted content for a specific platform.
- **GatewayConfig** — platform credentials, settings, default delivery target.
- **Callbacks** — `on_message` and `on_feedback` wired by the Orchestrator at construction.

## Outputs

- **InboundMessage** — dispatched to the Orchestrator via `on_message` callback, triggering a `respond` activation.
- **FeedbackSignal** — dispatched to the Feedback Collector via `on_feedback` callback.
- **DeliveryResult** — returned to the Output Router after each `send`, includes `message_id` for feedback tracking.

## State

- **Listener state:** background threads/async tasks for each platform's inbound polling. In-memory, started/stopped with `start_listener`/`stop_listener`.
- **Message ID mapping:** maps Gateway-internal message IDs to platform-specific IDs for feedback attribution. In-memory, bounded (recent messages only — older mappings expire).
- No persistent state. Platform connections are stateless (re-established on restart).

## Usage Example

```python
from gateway import Gateway, GatewayConfig, PlatformConfig, OutboundMessage

def handle_message(msg):
    print(f"[{msg.platform}] {msg.sender}: {msg.content}")
    orchestrator.trigger("respond", {"message": msg})

def handle_feedback(signal):
    print(f"Feedback: {signal.signal_type} on {signal.message_id}")
    feedback_collector.process(signal)

gw = Gateway(
    config=GatewayConfig(
        platforms=[
            PlatformConfig(
                name="telegram",
                adapter_type="telegram",
                credentials={"bot_token": "123:ABC..."},
                params={"chat_id": "987654321"},
                output_formats=["text", "markdown", "telegraph", "thread"],
            ),
            PlatformConfig(
                name="log",
                adapter_type="log",
                credentials={},
                params={"log_path": "./output.log"},
                output_formats=["text"],
            ),
        ],
        default_platform="telegram",
    ),
    on_message=handle_message,
    on_feedback=handle_feedback,
)

gw.start_listener()

# Output Router sends generated content
result = gw.send(OutboundMessage(
    content="The Zettelkasten insight keeps returning from different angles...",
    platform="telegram",
    format="markdown",
    intent_tag="synthesis",
))
print(f"Delivered: {result.message_id}")

# Or use the convenience method for unprompted output
result = gw.send_to_default("A thought from free play...", intent_tag="free_play")
```
