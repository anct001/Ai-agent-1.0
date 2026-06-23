import json

import pytest

from jarvis.config import RiskLimits
from jarvis.memory import Journal
from jarvis.portfolio import Portfolio
from jarvis.risk import RiskManager
from jarvis.toolkit import Toolkit, anthropic_tools, openai_tools


def test_schemas_share_tools_minus_web_search():
    a_names = {
        t.get("name") for t in anthropic_tools(include_web_search=True)
    }
    o_names = {t["function"]["name"] for t in openai_tools()}
    assert "web_search" in a_names
    assert "web_search" not in o_names
    # Every local tool exists on the Anthropic side too.
    assert o_names == a_names - {"web_search"}


def test_anthropic_without_web_search():
    names = {t["name"] for t in anthropic_tools(include_web_search=False)}
    assert "web_search" not in names


def test_openai_schema_shape():
    tool = next(t for t in openai_tools() if t["function"]["name"] == "place_order")
    assert tool["type"] == "function"
    assert "parameters" in tool["function"]
    assert "side" in tool["function"]["parameters"]["properties"]


class _StubBroker:
    name = "stub"

    def execute_order(self, symbol, side, qty, rationale):
        from jarvis.brokers.base import Fill

        return Fill(symbol=symbol, side=side, qty=qty, price=100.0, value=qty * 100.0)


@pytest.fixture
def toolkit(tmp_path):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    risk = RiskManager(RiskLimits())
    journal = Journal(tmp_path)
    return Toolkit(portfolio, _StubBroker(), risk, journal)


def test_execute_unknown_tool_raises(toolkit):
    with pytest.raises(ValueError, match="Unknown tool"):
        toolkit.execute("nonexistent", {})


def test_execute_json_wraps_errors(toolkit):
    # Missing required arg -> error captured as JSON, not raised.
    out = json.loads(toolkit.execute_json("get_quote", {}))
    assert "error" in out


def test_record_thesis_roundtrip(toolkit):
    out = json.loads(
        toolkit.execute_json(
            "record_thesis",
            {
                "symbol": "NVDA",
                "thesis": "AI compute demand",
                "conviction": "high",
                "horizon": "3-5 years",
                "invalidation": "Margins collapse",
            },
        )
    )
    assert out["symbol"] == "NVDA"
    assert json.loads(toolkit.execute_json("read_journal", {}))["theses"]
