from jarvis.telegram_bot import (
    approval_keyboard,
    chunk_text,
    format_order,
    format_portfolio,
    parse_callback,
)


def test_chunk_short_text_single():
    assert chunk_text("hello") == ["hello"]


def test_chunk_long_text_respects_limit():
    text = "\n".join("line %d" % i for i in range(5000))
    chunks = chunk_text(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == text


def test_chunk_single_overlong_line():
    chunks = chunk_text("x" * 2500, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == "x" * 2500


def test_approval_keyboard_carries_req_id():
    kb = approval_keyboard("abc123")
    buttons = kb["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "approve:abc123"
    assert buttons[1]["callback_data"] == "deny:abc123"


def test_parse_callback():
    assert parse_callback("approve:xyz") == ("approve", "xyz")
    assert parse_callback("deny:xyz") == ("deny", "xyz")
    assert parse_callback("") == ("", "")


def test_format_order_contains_key_fields():
    text = format_order(
        {
            "side": "buy",
            "qty": 10,
            "symbol": "NVDA",
            "est_price": 100.0,
            "est_value": 1000.0,
            "conviction": "high",
            "rationale": "AI demand",
        }
    )
    assert "BUY 10 NVDA" in text
    assert "AI demand" in text


def test_format_portfolio_empty_and_populated():
    empty = format_portfolio({"equity": 100.0, "cash": 100.0, "trades_today": 0, "positions": []})
    assert "No open positions" in empty
    full = format_portfolio(
        {
            "equity": 1000.0,
            "cash": 500.0,
            "trades_today": 1,
            "positions": [
                {"symbol": "NVDA", "qty": 5, "price": 100.0, "unrealized_pnl": 50.0, "unrealized_pnl_pct": 11.1}
            ],
        }
    )
    assert "NVDA" in full and "🟢" in full
