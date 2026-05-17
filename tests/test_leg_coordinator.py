import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.exchange.base import TradeRequest, TradeResult
from agent.strategies.leg_coordinator import LegCoordinator
from agent.storage.repo import Repository


@pytest.mark.asyncio
async def test_leg_coordinator_aborts_on_leg1_failure():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(str(Path(tmp) / "t.db"))
        adapter1 = AsyncMock()
        adapter2 = AsyncMock()
        adapter1.get_quote.return_value = {}
        adapter1.place_trade.return_value = TradeResult(False, None, "base", error="revert")
        legs = LegCoordinator({"base": adapter1, "optimism": adapter2}, repo)
        req = TradeRequest("g1", "winner", 0, 5.0)
        ok = await legs.execute_two_leg("arb1", "base", "optimism", req, req)
        assert ok is False
        adapter2.place_trade.assert_not_called()
