from jarvis.history import EquityHistory


def test_records_and_normalizes_across_days(tmp_path):
    h = EquityHistory(tmp_path / "hist.json")
    h.record(100_000.0, benchmark=5000.0, on_date="2026-06-01")
    h.record(105_000.0, benchmark=5100.0, on_date="2026-06-02")
    series = h.read()
    assert len(series) == 2
    assert series[0]["equity_idx"] == 100.0
    assert series[1]["equity_idx"] == 105.0
    assert series[1]["benchmark_idx"] == 102.0


def test_same_day_overwrites(tmp_path):
    h = EquityHistory(tmp_path / "hist.json")
    h.record(100_000.0, benchmark=5000.0, on_date="2026-06-01")
    h.record(101_500.0, benchmark=5050.0, on_date="2026-06-01")
    h.record(103_000.0, benchmark=5100.0, on_date="2026-06-02")
    series = h.read()
    assert len(series) == 2
    assert series[0]["equity"] == 101_500.0  # latest same-day snapshot wins


def test_missing_benchmark_kept_from_earlier_record(tmp_path):
    h = EquityHistory(tmp_path / "hist.json")
    h.record(100_000.0, benchmark=5000.0, on_date="2026-06-01")
    h.record(102_000.0, on_date="2026-06-01")  # benchmark fetch failed
    series = h.read()
    assert series[0]["equity"] == 102_000.0
    assert series[0]["benchmark_idx"] == 100.0  # earlier benchmark retained


def test_empty_history(tmp_path):
    h = EquityHistory(tmp_path / "hist.json")
    assert h.read() == []
