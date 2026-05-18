"""Merkle leaf + tree helpers matching SportsAMMV2RiskManager._computeMerkleLeaf."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eth_abi.packed import encode_packed
from web3 import Web3

from agent.exchange.overtime.game_id import normalize_game_id


@dataclass
class MarketLeafInput:
    game_id: str
    sport_id: int
    type_id: int
    maturity: int
    status: int
    line: int
    player_id: int
    odds: list[int]  # 1e18-scaled implied weights, index = position
    combined_positions: list[list[tuple[int, int, int]]] = field(default_factory=list)


def implied_to_odd_wei(implied: float) -> int:
    return int(implied * 10**18)


def compute_merkle_leaf(input_data: MarketLeafInput) -> bytes:
    """Match contracts-v2 SportsAMMV2RiskManager._computeMerkleLeaf (abi.encodePacked)."""
    game_id = bytes.fromhex(normalize_game_id(input_data.game_id)[2:])
    packed = encode_packed(
        ["bytes32", "uint16", "uint16", "uint256", "uint8", "int256", "uint256", "uint256[]"],
        [
            game_id,
            input_data.sport_id,
            input_data.type_id,
            input_data.maturity,
            input_data.status,
            input_data.line,
            input_data.player_id,
            input_data.odds,
        ],
    )
    for side_positions in input_data.combined_positions:
        for type_id, position, line in side_positions:
            packed += encode_packed(
                ["uint16", "uint8", "int256"],
                [type_id, position, line],
            )
    return Web3.keccak(packed)


def build_sorted_merkle_tree(leaves: list[bytes]) -> tuple[bytes, dict[bytes, list[bytes]]]:
    """Sorted-pair merkle tree (merkletreejs: sortLeaves, sortPairs). Returns root, leaf->proof."""
    if not leaves:
        raise ValueError("no leaves")
    sorted_leaves = sorted(leaves)
    layers: list[list[bytes]] = [sorted_leaves]
    while len(layers[-1]) > 1:
        layer = layers[-1]
        nxt: list[bytes] = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else layer[i]
            pair = sorted([left, right])
            nxt.append(Web3.keccak(pair[0] + pair[1]))
        layers.append(nxt)
    root = layers[-1][0]

    proofs: dict[bytes, list[bytes]] = {}

    def walk(layer_idx: int, idx: int, path: list[bytes]) -> None:
        if layer_idx == 0:
            proofs[layers[0][idx]] = path.copy()
            return
        layer = layers[layer_idx]
        sibling_idx = idx + 1 if idx % 2 == 0 else idx - 1
        if sibling_idx < len(layer):
            path.append(layer[sibling_idx])
        parent_idx = idx // 2
        walk(layer_idx - 1, parent_idx, path)

    for i, leaf in enumerate(layers[0]):
        walk(len(layers) - 1, i, [])

    return root, proofs


def aggregate_subgraph_rows(rows: list[dict[str, Any]]) -> list[MarketLeafInput]:
    """Group flat subgraph sides into market leaves (one odds[] per market key)."""
    buckets: dict[tuple[str, int, int, int, int, int, int], dict[int, int]] = {}
    meta: dict[tuple[str, int, int, int, int, int, int], dict[str, Any]] = {}

    for row in rows:
        game_id = normalize_game_id(str(row["gameId"]))
        key = (
            game_id,
            int(row["sportId"]),
            int(row["typeId"]),
            int(row["maturity"]),
            int(row["status"]),
            int(row["line"]),
            int(row["playerId"]),
        )
        position = int(row["position"])
        odd_wei = int(row["odd"])
        buckets.setdefault(key, {})[position] = odd_wei
        meta[key] = {
            "game_id": game_id,
            "sport_id": key[1],
            "type_id": key[2],
            "maturity": key[3],
            "status": key[4],
            "line": key[5],
            "player_id": key[6],
        }

    leaves: list[MarketLeafInput] = []
    for key, odds_map in buckets.items():
        m = meta[key]
        max_pos = max(odds_map.keys())
        odds = [odds_map.get(i, 0) for i in range(max_pos + 1)]
        leaves.append(
            MarketLeafInput(
                game_id=m["game_id"],
                sport_id=m["sport_id"],
                type_id=m["type_id"],
                maturity=m["maturity"],
                status=m["status"],
                line=m["line"],
                player_id=m["player_id"],
                odds=odds,
            )
        )
    return leaves


def trade_data_for_position(
    leaf: MarketLeafInput,
    position: int,
    proof: list[bytes],
) -> dict[str, Any]:
    return {
        "gameId": leaf.game_id,
        "sportId": leaf.sport_id,
        "typeId": leaf.type_id,
        "maturity": leaf.maturity,
        "status": leaf.status,
        "line": leaf.line,
        "playerId": leaf.player_id,
        "odds": leaf.odds,
        "merkleProof": [f"0x{p.hex()}" if not isinstance(p, str) else p for p in proof],
        "position": position,
        "combinedPositions": [[] for _ in leaf.odds],
    }
