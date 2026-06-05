from __future__ import annotations

import pytest

from toolkit.coaching import (
    CoachingEvent,
    Command,
    RouteRule,
    TaggedCoachingParser,
    load_routes_config,
)


# Mirrors the canonical Diplomat coaching_routes.yaml shape but kept inline
# so the toolkit tests have no cross-project dependency.
DEFAULT_ROUTES_YAML = """
tags:
  PRIORITY:
    route: coaching_queue
    coaching_type: PRIORITY
  CONSTRAINT:
    route: coaching_queue
    coaching_type: CONSTRAINT
  INTEL:
    route: state_updater
    coaching_type: INTEL
  TONE:
    route: coaching_queue
    coaching_type: TONE
  WATCH:
    route: coaching_queue
    coaching_type: WATCH
  default:
    route: coaching_queue
    coaching_type: FREE

commands:
  - /preview
  - /approve
  - /edit
  - /block
  - /status
  - /state
""".strip()


@pytest.fixture
def routes_path(tmp_path):
    path = tmp_path / "routes.yaml"
    path.write_text(DEFAULT_ROUTES_YAML, encoding="utf-8")
    return path


@pytest.fixture
def parser(routes_path):
    return TaggedCoachingParser(routes_path)


def test_public_exports_include_parser_and_result_types():
    import toolkit.coaching as coaching

    assert coaching.CoachingEvent is CoachingEvent
    assert coaching.Command is Command
    assert coaching.RouteRule is RouteRule
    assert coaching.TaggedCoachingParser is TaggedCoachingParser


def test_load_routes_config_returns_mapping(routes_path):
    config = load_routes_config(routes_path)

    assert "tags" in config
    assert "commands" in config


def test_parser_loads_tag_routes_and_commands_from_config(parser):
    assert parser.default_route == RouteRule(
        coaching_type="FREE",
        route="coaching_queue",
    )
    assert parser.tag_routes["INTEL"] == RouteRule(
        coaching_type="INTEL",
        route="state_updater",
    )
    assert "/preview" in parser.commands
    assert "/edit" in parser.commands


def test_from_config_constructs_without_yaml_loader():
    # Verifies the no-YAML path: caller passes an already-parsed dict.
    config = {
        "tags": {
            "default": {"route": "coaching_queue", "coaching_type": "FREE"},
            "INTEL": {"route": "state_updater", "coaching_type": "INTEL"},
        },
        "commands": ["/preview"],
    }

    parsed = TaggedCoachingParser.from_config(config)

    assert parsed.default_route == RouteRule(
        coaching_type="FREE",
        route="coaching_queue",
    )
    assert parsed.tag_routes["INTEL"] == RouteRule(
        coaching_type="INTEL",
        route="state_updater",
    )
    assert "/preview" in parsed.commands
    assert parsed.parse("INTEL: hello") == CoachingEvent(
        coaching_type="INTEL",
        content="hello",
        route="state_updater",
    )


def test_tagged_coaching_uses_configured_route_and_canonical_type(parser):
    result = parser.parse("priority: Secure alliance with Beta")

    assert result == CoachingEvent(
        coaching_type="PRIORITY",
        content="Secure alliance with Beta",
        route="coaching_queue",
    )


def test_intel_routes_to_state_updater(parser):
    result = parser.parse("INTEL: Alpha broke promise to Gamma")

    assert result == CoachingEvent(
        coaching_type="INTEL",
        content="Alpha broke promise to Gamma",
        route="state_updater",
    )


def test_untagged_empty_unknown_and_malformed_inputs_are_free_coaching(parser):
    assert parser.parse("Be careful with Delta") == CoachingEvent(
        coaching_type="FREE",
        content="Be careful with Delta",
        route="coaching_queue",
    )
    assert parser.parse("  ") == CoachingEvent(
        coaching_type="FREE",
        content="",
        route="coaching_queue",
    )
    assert parser.parse("MOOD: too soft") == CoachingEvent(
        coaching_type="FREE",
        content="MOOD: too soft",
        route="coaching_queue",
    )
    assert parser.parse("PRIORITY secure Beta") == CoachingEvent(
        coaching_type="FREE",
        content="PRIORITY secure Beta",
        route="coaching_queue",
    )


def test_known_commands_return_command_objects(parser):
    assert parser.parse("/preview") == Command(name="preview", args={})
    assert parser.parse("/STATUS") == Command(name="status", args={})


def test_edit_command_accepts_colon_or_space_text(parser):
    assert parser.parse("/edit: Soften the second paragraph") == Command(
        name="edit",
        args={"text": "Soften the second paragraph"},
    )
    assert parser.parse("/edit Soften the second paragraph") == Command(
        name="edit",
        args={"text": "Soften the second paragraph"},
    )


def test_unknown_slash_command_is_free_coaching(parser):
    assert parser.parse("/unknown") == CoachingEvent(
        coaching_type="FREE",
        content="/unknown",
        route="coaching_queue",
    )


def test_parser_rejects_missing_required_config_sections(tmp_path):
    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text("tags: {}\ncommands: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="requires mapping: default"):
        TaggedCoachingParser(routes_path)


def test_parser_rejects_malformed_commands(tmp_path):
    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text(
        """
tags:
  default:
    route: coaching_queue
    coaching_type: FREE
commands:
  - preview
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="slash-prefixed"):
        TaggedCoachingParser(routes_path)
