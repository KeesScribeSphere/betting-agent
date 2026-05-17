from agent.exchange.overtime.rest import market_to_quotes, normalize_markets_payload


def test_normalize_list_markets():
    data = [{"gameId": "0xabc", "sport": "Soccer", "type": "winner", "isOpen": True, "odds": []}]
    assert len(normalize_markets_payload(data)) == 1


def test_market_to_quotes_implied_prob():
    market = {
        "gameId": "0xabc",
        "sport": "Soccer",
        "leagueName": "EPL",
        "type": "winner",
        "typeId": 0,
        "isOpen": True,
        "homeTeam": "A",
        "awayTeam": "B",
        "odds": [
            {"decimal": 2.0, "normalizedImplied": 0.5},
            {"decimal": 2.0, "normalizedImplied": 0.5},
        ],
    }
    quotes = market_to_quotes("base", 8453, market)
    assert len(quotes) == 2
    assert quotes[0].implied_prob == 0.5
