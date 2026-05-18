"""On-chain tradeQuote / trade without Overtime REST (merkle proofs built from subgraph)."""

from __future__ import annotations

from typing import Any

from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

from agent.exchange.base import MarketQuote
from agent.exchange.overtime.merkle import (
    MarketLeafInput,
    aggregate_subgraph_rows,
    build_sorted_merkle_tree,
    compute_merkle_leaf,
    trade_data_for_position,
)
from agent.logging_setup import get_logger

log = get_logger(__name__)

# Minimal ABI for tradeQuote + trade (contracts-v2 SportsAMMV2)
TRADE_DATA_COMPONENT = [
    {"name": "gameId", "type": "bytes32"},
    {"name": "sportId", "type": "uint16"},
    {"name": "typeId", "type": "uint16"},
    {"name": "maturity", "type": "uint256"},
    {"name": "status", "type": "uint8"},
    {"name": "line", "type": "int24"},
    {"name": "playerId", "type": "uint24"},
    {"name": "odds", "type": "uint256[]"},
    {"name": "merkleProof", "type": "bytes32[]"},
    {"name": "position", "type": "uint8"},
    {
        "name": "combinedPositions",
        "type": "tuple[][]",
        "components": [
            {"name": "typeId", "type": "uint16"},
            {"name": "position", "type": "uint8"},
            {"name": "line", "type": "int24"},
        ],
    },
]

SPORTS_AMM_V2_QUOTE_ABI = [
    {
        "inputs": [
            {"components": TRADE_DATA_COMPONENT, "name": "_tradeData", "type": "tuple[]"},
            {"name": "_buyInAmount", "type": "uint256"},
            {"name": "_collateral", "type": "address"},
            {"name": "_isLive", "type": "bool"},
        ],
        "name": "tradeQuote",
        "outputs": [
            {"name": "totalQuote", "type": "uint256"},
            {"name": "payout", "type": "uint256"},
            {"name": "fees", "type": "uint256"},
            {"name": "amountsToBuy", "type": "uint256[]"},
            {"name": "buyInAmountInDefaultCollateral", "type": "uint256"},
            {"name": "riskStatus", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"components": TRADE_DATA_COMPONENT, "name": "_tradeData", "type": "tuple[]"},
            {"name": "_buyInAmount", "type": "uint256"},
            {"name": "_expectedQuote", "type": "uint256"},
            {"name": "_additionalSlippage", "type": "uint256"},
            {"name": "_referrer", "type": "address"},
            {"name": "_collateral", "type": "address"},
            {"name": "_isEth", "type": "bool"},
        ],
        "name": "trade",
        "outputs": [{"name": "_createdTicket", "type": "address"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "rootPerGame",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _to_contract_trade_tuple(data: dict[str, Any]) -> tuple[Any, ...]:
    proof = [bytes.fromhex(p[2:]) if isinstance(p, str) else p for p in data["merkleProof"]]
    combined = data.get("combinedPositions") or [[] for _ in data["odds"]]
    combined_tuples = [
        [(cp.get("typeId", cp[0]), cp.get("position", cp[1]), cp.get("line", cp[2])) for cp in side]
        if side and isinstance(side[0], dict)
        else side
        for side in combined
    ]
    game_id = bytes.fromhex(data["gameId"][2:] if data["gameId"].startswith("0x") else data["gameId"])
    return (
        game_id,
        int(data["sportId"]),
        int(data["typeId"]),
        int(data["maturity"]),
        int(data["status"]),
        int(data["line"]),
        int(data["playerId"]),
        [int(o) for o in data["odds"]],
        proof,
        int(data["position"]),
        combined_tuples,
    )


class OnchainTradeClient:
    def __init__(
        self,
        rpc_urls: list[str],
        chain_id: int,
        sports_amm_address: str,
        usdc_address: str,
    ) -> None:
        self.chain_id = chain_id
        self.rpc_urls = rpc_urls
        self.sports_amm_address = sports_amm_address
        self.usdc_address = usdc_address
        self._w3: AsyncWeb3 | None = None

    async def _web3(self) -> AsyncWeb3:
        if self._w3 is None:
            for url in self.rpc_urls:
                w3 = AsyncWeb3(AsyncHTTPProvider(url))
                if await w3.is_connected():
                    self._w3 = w3
                    return w3
            raise ConnectionError("No RPC available")
        return self._w3

    async def build_trade_data(
        self,
        quote: MarketQuote,
        game_market_rows: list[dict[str, Any]],
        position: int | None = None,
    ) -> dict[str, Any]:
        """Build TradeData + merkle proof for one quote from all open markets on the same game."""
        leaves_in = aggregate_subgraph_rows(game_market_rows)
        leaf_hashes = {compute_merkle_leaf(leaf): leaf for leaf in leaves_in}
        root, proofs = build_sorted_merkle_tree(list(leaf_hashes.keys()))

        w3 = await self._web3()
        amm = w3.eth.contract(
            address=w3.to_checksum_address(self.sports_amm_address),
            abi=SPORTS_AMM_V2_QUOTE_ABI,
        )
        on_chain_root = await amm.functions.rootPerGame(
            bytes.fromhex(quote.game_id[2:])
        ).call()
        if on_chain_root != root:
            log.warning(
                "merkle_root_mismatch",
                computed=root.hex(),
                on_chain=on_chain_root.hex(),
                game_id=quote.game_id,
            )

        target_key = (
            quote.game_id,
            quote.sport_id or 0,
            quote.market_type_id,
            int(quote.raw.get("maturity", 0)) if quote.raw else 0,
            quote.status or 0,
            quote.line or 0,
            quote.player_id or 0,
        )
        target_leaf = None
        for leaf in leaves_in:
            if (
                leaf.game_id == target_key[0]
                and leaf.sport_id == target_key[1]
                and leaf.type_id == target_key[2]
                and leaf.maturity == target_key[3]
                and leaf.status == target_key[4]
                and leaf.line == target_key[5]
                and leaf.player_id == target_key[6]
            ):
                target_leaf = leaf
                break
        if target_leaf is None:
            raise ValueError(f"No matching market leaf for game {quote.game_id} {quote.market_type}")

        pos = quote.side_index if position is None else position
        leaf_hash = compute_merkle_leaf(target_leaf)
        proof = proofs.get(leaf_hash)
        if not proof:
            raise ValueError("Merkle proof not found for target leaf")
        return trade_data_for_position(target_leaf, pos, proof)

    async def trade_quote(
        self,
        trade_data: dict[str, Any],
        buy_in_usdc: float,
        collateral_address: str | None = None,
        is_live: bool = False,
    ) -> dict[str, Any]:
        """eth_call tradeQuote — dry-run validation before sending trade()."""
        w3 = await self._web3()
        amm = w3.eth.contract(
            address=w3.to_checksum_address(self.sports_amm_address),
            abi=SPORTS_AMM_V2_QUOTE_ABI,
        )
        buy_in_wei = int(buy_in_usdc * 10**6)
        collateral = w3.to_checksum_address(collateral_address or self.usdc_address)
        trade_tuple = _to_contract_trade_tuple(trade_data)
        result = await amm.functions.tradeQuote([trade_tuple], buy_in_wei, collateral, is_live).call()
        return {
            "totalQuote": result[0],
            "payout": result[1],
            "fees": result[2],
            "amountsToBuy": result[3],
            "buyInAmountInDefaultCollateral": result[4],
            "riskStatus": result[5],
            "tradeData": trade_data,
            "buyInWei": buy_in_wei,
            "collateral": collateral,
        }
