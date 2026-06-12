"""Broker interface. PaperBroker is the default; live brokers implement
the same protocol so the agent and risk manager don't care which is wired in."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Fill:
    symbol: str
    side: str
    qty: float
    price: float
    value: float


class Broker(Protocol):
    name: str

    def execute_order(
        self, symbol: str, side: str, qty: float, rationale: str
    ) -> Fill: ...
