from agent.exchange.overtime.merkle import MarketLeafInput, aggregate_subgraph_rows, compute_merkle_leaf


def test_aggregate_subgraph_rows_builds_odds_array():
    rows = [
        {
            "gameId": "0x" + "ab" * 32,
            "sportId": 1,
            "typeId": 10,
            "maturity": 2000000000,
            "status": 0,
            "line": 0,
            "playerId": 0,
            "position": 0,
            "odd": str(int(0.4 * 1e18)),
        },
        {
            "gameId": "0x" + "ab" * 32,
            "sportId": 1,
            "typeId": 10,
            "maturity": 2000000000,
            "status": 0,
            "line": 0,
            "playerId": 0,
            "position": 1,
            "odd": str(int(0.6 * 1e18)),
        },
    ]
    leaves = aggregate_subgraph_rows(rows)
    assert len(leaves) == 1
    assert len(leaves[0].odds) == 2
    assert compute_merkle_leaf(leaves[0])  # does not raise
