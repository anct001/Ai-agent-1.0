from jarvis.alerts import check_alerts
from jarvis.config import Settings


def _settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path)
    s.alert_position_drawdown_pct = 15.0
    s.alert_portfolio_drawdown_pct = 10.0
    s.alert_daily_move_pct = 5.0
    return s


def _snapshot(equity=100_000.0, positions=None):
    return {"equity": equity, "cash": equity, "positions": positions or []}


def test_no_alerts_when_healthy(tmp_path):
    snap = _snapshot(
        positions=[
            {"symbol": "NVDA", "price": 105.0, "avg_cost": 100.0, "unrealized_pnl_pct": 5.0}
        ]
    )
    assert check_alerts(snap, [], _settings(tmp_path)) == []


def test_position_drawdown_alert(tmp_path):
    snap = _snapshot(
        positions=[
            {"symbol": "ARKK", "price": 80.0, "avg_cost": 100.0, "unrealized_pnl_pct": -20.0}
        ]
    )
    alerts = check_alerts(snap, [], _settings(tmp_path))
    assert len(alerts) == 1
    assert alerts[0]["key"] == "pos_drawdown:ARKK"
    assert "20.0%" in alerts[0]["title"]


def test_portfolio_drawdown_alert(tmp_path):
    history = [
        {"date": "2026-06-01", "equity": 120_000.0},
        {"date": "2026-06-02", "equity": 118_000.0},
    ]
    alerts = check_alerts(_snapshot(equity=105_000.0), history, _settings(tmp_path))
    assert any(a["key"] == "portfolio_drawdown" for a in alerts)
    dd = next(a for a in alerts if a["key"] == "portfolio_drawdown")
    assert dd["severity"] == "critical"


def test_daily_move_alert(tmp_path):
    history = [{"date": "2026-06-11", "equity": 100_000.0}]
    alerts = check_alerts(_snapshot(equity=94_000.0), history, _settings(tmp_path))
    assert any(a["key"].startswith("daily_move") for a in alerts)

    # Small moves stay quiet.
    calm = check_alerts(_snapshot(equity=99_000.0), history, _settings(tmp_path))
    assert not any(a["key"].startswith("daily_move") for a in calm)
