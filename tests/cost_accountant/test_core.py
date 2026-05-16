"""Tests for toolkit.cost_accountant public API and core behavior."""

import json
from datetime import datetime, timezone

import pytest

from toolkit.cost_accountant import (
    DEFAULT_PRICING,
    BatchEstimate,
    BudgetExceededError,
    CallEstimate,
    CostAccountant,
    CostBudget,
    CostReport,
    LedgerEntry,
    ModelPricing,
    OperationBudgetError,
    PerCallBudgetError,
    RateLimitAbortError,
    SessionBudgetError,
    SpendingCapAbortError,
    UnknownModelError,
)
from toolkit.llm_client import (
    LLMAPIError,
    LLMConfig,
    LLMResponse,
    Message,
    ModelTier,
    TokenUsage,
)


MODEL = "claude-sonnet-4-20250514"


def _config(**overrides):
    defaults = dict(
        provider="anthropic",
        api_key="sk-test",
        models={"quality": MODEL, "default": MODEL, "commodity": "claude-haiku-4-5"},
        max_tokens=1000,
        temperature=0.2,
    )
    defaults.update(overrides)
    return LLMConfig(**defaults)


def _budget(**overrides):
    defaults = dict(
        operation_name="test_operation",
        operation_budget_usd=10.0,
        session_budget_usd=20.0,
        per_call_max_usd=5.0,
    )
    defaults.update(overrides)
    return CostBudget(**defaults)


def _response(model=MODEL, input_tokens=20, output_tokens=10):
    return LLMResponse(
        content="ok",
        model=model,
        provider="stub",
        token_usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def _ledger_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


class TestPublicAPI:
    def test_public_imports_available(self):
        assert CostAccountant is not None
        assert CostBudget is not None
        assert ModelPricing is not None
        assert BudgetExceededError is not None

    def test_default_pricing_contains_contract_models(self):
        assert DEFAULT_PRICING["claude-sonnet-4-20250514"] == ModelPricing(3.0, 15.0)
        assert DEFAULT_PRICING["claude-haiku-4-5"] == ModelPricing(0.25, 1.25)

    def test_error_attributes(self):
        error = PerCallBudgetError("too much", 1.25, 1.0)
        assert error.estimated_cost_usd == 1.25
        assert error.budget_usd == 1.0


class TestConstructorAndLedger:
    def test_constructor_creates_parent_and_ledger(self, tmp_path):
        ledger = tmp_path / "nested" / "ledger.jsonl"
        accountant = CostAccountant(ledger)
        assert accountant.ledger_path == ledger
        assert ledger.exists()
        assert ledger.read_text() == ""

    def test_constructor_loads_existing_entries_for_reporting(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        entry = LedgerEntry(
            timestamp="2026-05-16T00:00:00Z",
            operation="loaded",
            model=MODEL,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.1,
            cumulative_session_usd=0.1,
            budget_name="loaded",
            budget_remaining_usd=0.9,
            duration_ms=100,
            success=True,
            error=None,
        )
        ledger.write_text(json.dumps(entry.__dict__) + "\n")

        report = CostAccountant(ledger).report()

        assert report.total_calls == 1
        assert report.by_operation == {"loaded": 0.1}

    def test_custom_pricing_replaces_defaults(self, tmp_path):
        accountant = CostAccountant(
            tmp_path / "ledger.jsonl",
            pricing={"custom": ModelPricing(1.0, 2.0)},
        )
        assert "custom" in accountant.pricing
        assert MODEL not in accountant.pricing


class TestEstimation:
    def test_estimate_cost_returns_breakdown(self, tmp_path):
        estimate = CostAccountant(tmp_path / "ledger.jsonl").estimate_cost(
            MODEL,
            input_tokens=2_000_000,
            expected_output_tokens=1_000_000,
        )
        assert estimate.input_cost_usd == pytest.approx(6.0)
        assert estimate.output_cost_usd == pytest.approx(15.0)
        assert estimate.total_usd == pytest.approx(21.0)

    def test_estimate_cost_unknown_model_raises(self, tmp_path):
        with pytest.raises(UnknownModelError) as exc_info:
            CostAccountant(tmp_path / "ledger.jsonl").estimate_cost("missing", 1)
        assert exc_info.value.model == "missing"

    def test_estimate_batch_returns_call_breakdown(self, tmp_path):
        batch = CostAccountant(tmp_path / "ledger.jsonl").estimate_batch(
            MODEL,
            calls=[
                {"label": "a", "input_chars": 400},
                {"label": "b", "input_chars": 800},
            ],
            expected_output_tokens_per_call=10,
        )
        assert isinstance(batch, BatchEstimate)
        assert [call.label for call in batch.calls] == ["a", "b"]
        assert [call.input_tokens for call in batch.calls] == [100, 200]
        assert batch.total_usd == pytest.approx(
            sum(call.estimated_cost_usd for call in batch.calls)
        )

    def test_estimate_batch_default_label(self, tmp_path):
        batch = CostAccountant(tmp_path / "ledger.jsonl").estimate_batch(
            MODEL,
            calls=[{"input_chars": 4}],
        )
        assert batch.calls == [
            CallEstimate(
                label="",
                input_tokens=1,
                estimated_cost_usd=batch.calls[0].estimated_cost_usd,
            )
        ]

    def test_estimate_input_tokens_sums_message_content(self, tmp_path):
        accountant = CostAccountant(tmp_path / "ledger.jsonl")
        assert accountant._estimate_input_tokens(
            [
                Message(role="system", content="12345"),
                Message(role="user", content="1234567"),
            ]
        ) == 3


class TestComplete:
    def test_complete_calls_llm_and_writes_success_ledger(self, tmp_path, monkeypatch):
        calls = []

        def fake_complete(*, messages, config, tier):
            calls.append((messages, config, tier))
            return _response(input_tokens=20, output_tokens=10)

        monkeypatch.setattr("toolkit.cost_accountant.core.llm_complete", fake_complete)
        ledger = tmp_path / "ledger.jsonl"
        accountant = CostAccountant(ledger)

        response = accountant.complete(
            messages=[Message(role="user", content="hello")],
            config=_config(),
            tier=ModelTier.QUALITY,
            budget=_budget(),
        )

        assert response.content == "ok"
        assert len(calls) == 1
        assert accountant.session_total == pytest.approx(0.00021)
        row = _ledger_lines(ledger)[0]
        assert row["success"] is True
        assert row["cost_usd"] == pytest.approx(0.00021)
        assert row["cumulative_session_usd"] == pytest.approx(accountant.session_total)

    def test_complete_updates_operation_total_for_budget_remaining(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: _response(input_tokens=20, output_tokens=10),
        )
        ledger = tmp_path / "ledger.jsonl"
        accountant = CostAccountant(ledger)
        budget = _budget(operation_budget_usd=1.0)

        accountant.complete(
            messages=[Message(role="user", content="hello")],
            config=_config(),
            tier=ModelTier.QUALITY,
            budget=budget,
        )

        row = _ledger_lines(ledger)[0]
        assert row["budget_remaining_usd"] == pytest.approx(1.0 - 0.00021)

    def test_complete_resolves_string_tier(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: _response(model="claude-haiku-4-5"),
        )
        response = CostAccountant(tmp_path / "ledger.jsonl").complete(
            messages=[Message(role="user", content="hello")],
            config=_config(),
            tier="commodity",
            budget=_budget(),
        )
        assert response.model == "claude-haiku-4-5"

    def test_missing_tier_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Tier"):
            CostAccountant(tmp_path / "ledger.jsonl").complete(
                messages=[Message(role="user", content="hello")],
                config=_config(models={"quality": MODEL}),
                tier=ModelTier.DEFAULT,
                budget=_budget(),
            )

    def test_per_call_budget_error_writes_failure_ledger(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        with pytest.raises(PerCallBudgetError):
            CostAccountant(ledger).complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(per_call_max_usd=0.00001),
            )
        rows = _ledger_lines(ledger)
        assert rows[0]["success"] is False
        assert rows[0]["cost_usd"] == 0.0
        assert "per-call" in rows[0]["error"]

    def test_operation_budget_error(self, tmp_path):
        accountant = CostAccountant(tmp_path / "ledger.jsonl")
        accountant._operation_totals["test_operation"] = 0.02
        with pytest.raises(OperationBudgetError):
            accountant.complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(operation_budget_usd=0.03),
            )

    def test_session_budget_error(self, tmp_path):
        accountant = CostAccountant(tmp_path / "ledger.jsonl")
        accountant._session_total = 0.02
        with pytest.raises(SessionBudgetError):
            accountant.complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(session_budget_usd=0.03),
            )

    def test_rate_limit_status_raises_abort_and_writes_ledger(
        self, tmp_path, monkeypatch
    ):
        def fake_complete(**kwargs):
            raise LLMAPIError("slow down", status_code=429)

        monkeypatch.setattr("toolkit.cost_accountant.core.llm_complete", fake_complete)
        ledger = tmp_path / "ledger.jsonl"

        with pytest.raises(RateLimitAbortError):
            CostAccountant(ledger).complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(),
            )

        assert _ledger_lines(ledger)[0]["success"] is False

    def test_rate_limit_message_raises_abort(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: (_ for _ in ()).throw(LLMAPIError("rate limit hit")),
        )
        with pytest.raises(RateLimitAbortError):
            CostAccountant(tmp_path / "ledger.jsonl").complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(),
            )

    def test_rate_limit_can_pass_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: (_ for _ in ()).throw(LLMAPIError("rate limit hit")),
        )
        with pytest.raises(LLMAPIError):
            CostAccountant(tmp_path / "ledger.jsonl").complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(abort_on_rate_limit=False),
            )

    def test_spending_cap_raises_abort(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: (_ for _ in ()).throw(LLMAPIError("usage limits reached")),
        )
        with pytest.raises(SpendingCapAbortError):
            CostAccountant(tmp_path / "ledger.jsonl").complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(),
            )

    def test_spending_cap_can_pass_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: (_ for _ in ()).throw(LLMAPIError("spending cap reached")),
        )
        with pytest.raises(LLMAPIError):
            CostAccountant(tmp_path / "ledger.jsonl").complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(abort_on_spending_cap=False),
            )

    def test_other_errors_pass_through_after_ledger_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "toolkit.cost_accountant.core.llm_complete",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        ledger = tmp_path / "ledger.jsonl"
        with pytest.raises(RuntimeError, match="boom"):
            CostAccountant(ledger).complete(
                messages=[Message(role="user", content="hello")],
                config=_config(),
                tier=ModelTier.QUALITY,
                budget=_budget(),
            )
        assert _ledger_lines(ledger)[0]["error"] == "boom"


class TestReport:
    def test_report_breaks_down_by_operation_model_and_date(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        entries = [
            LedgerEntry(
                timestamp="2026-05-15T00:00:00Z",
                operation="op1",
                model=MODEL,
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.1,
                cumulative_session_usd=0.1,
                budget_name="op1",
                budget_remaining_usd=1.0,
                duration_ms=100,
                success=True,
                error=None,
            ),
            LedgerEntry(
                timestamp="2026-05-16T00:00:00Z",
                operation="op2",
                model="claude-haiku-4-5",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.2,
                cumulative_session_usd=0.3,
                budget_name="op2",
                budget_remaining_usd=1.0,
                duration_ms=100,
                success=True,
                error=None,
            ),
        ]
        ledger.write_text("".join(json.dumps(entry.__dict__) + "\n" for entry in entries))

        report = CostAccountant(ledger).report()

        assert isinstance(report, CostReport)
        assert report.total_calls == 2
        assert report.total_spend_usd == pytest.approx(0.3)
        assert report.by_operation == {"op1": 0.1, "op2": 0.2}
        assert report.by_model["claude-haiku-4-5"] == 0.2
        assert report.by_date == {"2026-05-15": 0.1, "2026-05-16": 0.2}

    def test_report_since_filters_entries(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            dict(
                timestamp="2026-05-15T00:00:00Z",
                operation="old",
                model=MODEL,
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.1,
                cumulative_session_usd=0.1,
                budget_name="old",
                budget_remaining_usd=1.0,
                duration_ms=100,
                success=True,
                error=None,
            ),
            dict(
                timestamp="2026-05-16T00:00:00Z",
                operation="new",
                model=MODEL,
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.2,
                cumulative_session_usd=0.2,
                budget_name="new",
                budget_remaining_usd=1.0,
                duration_ms=100,
                success=True,
                error=None,
            ),
        ]
        ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))

        report = CostAccountant(ledger).report(
            since=datetime(2026, 5, 16, tzinfo=timezone.utc)
        )

        assert report.total_calls == 1
        assert report.by_operation == {"new": 0.2}

    def test_report_detects_long_duration_and_repeated_failures(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        rows = []
        for index in range(3):
            rows.append(
                dict(
                    timestamp=f"2026-05-16T00:00:0{index}Z",
                    operation="flaky",
                    model=MODEL,
                    input_tokens=1,
                    output_tokens=0,
                    cost_usd=0.0,
                    cumulative_session_usd=0.0,
                    budget_name="flaky",
                    budget_remaining_usd=1.0,
                    duration_ms=61_000 if index == 0 else 100,
                    success=False,
                    error="failed",
                )
            )
        ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))

        anomalies = CostAccountant(ledger).report().anomalies

        assert any("Long duration" in anomaly for anomaly in anomalies)
        assert any("Repeated failures" in anomaly for anomaly in anomalies)

    def test_session_total_resets_on_construction(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text(
            json.dumps(
                dict(
                    timestamp="2026-05-16T00:00:00Z",
                    operation="old",
                    model=MODEL,
                    input_tokens=1,
                    output_tokens=1,
                    cost_usd=0.5,
                    cumulative_session_usd=0.5,
                    budget_name="old",
                    budget_remaining_usd=1.0,
                    duration_ms=100,
                    success=True,
                    error=None,
                )
            )
            + "\n"
        )
        assert CostAccountant(ledger).session_total == 0.0
