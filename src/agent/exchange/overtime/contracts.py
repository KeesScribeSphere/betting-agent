"""Web3 contract helpers for Sports AMM V2."""

from __future__ import annotations

from typing import Any

from eth_account import Account
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

# Minimal ABI fragments
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

SPORTS_AMM_V2_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "gameId", "type": "bytes32"},
                    {"name": "sportId", "type": "uint16"},
                    {"name": "typeId", "type": "uint16"},
                    {"name": "maturity", "type": "uint256"},
                    {"name": "status", "type": "uint8"},
                    {"name": "line", "type": "int256"},
                    {"name": "playerId", "type": "uint256"},
                    {"name": "position", "type": "uint8"},
                    {"name": "buyInAmount", "type": "uint256"},
                    {"name": "totalQuote", "type": "uint256"},
                    {"name": "slippage", "type": "uint256"},
                    {"name": "collateral", "type": "address"},
                ],
                "name": "_tradeData",
                "type": "tuple",
            }
        ],
        "name": "trade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


class OvertimeContracts:
    """On-chain reads and writes for one chain."""

    def __init__(
        self,
        rpc_urls: list[str],
        chain_id: int,
        sports_amm_address: str,
        usdc_address: str,
        private_key: str | None = None,
    ) -> None:
        self.chain_id = chain_id
        self.rpc_urls = rpc_urls
        self.sports_amm_address = sports_amm_address
        self.usdc_address = usdc_address
        self._private_key = private_key
        self._w3: AsyncWeb3 | None = None
        self._account = Account.from_key(private_key) if private_key else None

    async def _web3(self) -> AsyncWeb3:
        if self._w3 is None:
            last_error: Exception | None = None
            for url in self.rpc_urls:
                try:
                    w3 = AsyncWeb3(AsyncHTTPProvider(url))
                    if await w3.is_connected():
                        self._w3 = w3
                        return w3
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            raise ConnectionError(f"No RPC available: {last_error}")
        return self._w3

    async def get_eth_balance(self, address: str) -> int:
        w3 = await self._web3()
        return await w3.eth.get_balance(w3.to_checksum_address(address))

    async def get_usdc_balance(self, address: str) -> int:
        w3 = await self._web3()
        usdc = w3.eth.contract(
            address=w3.to_checksum_address(self.usdc_address),
            abi=ERC20_ABI,
        )
        return await usdc.functions.balanceOf(w3.to_checksum_address(address)).call()

    async def ensure_usdc_allowance(self, amount: int) -> str | None:
        if not self._account:
            return None
        w3 = await self._web3()
        owner = self._account.address
        usdc = w3.eth.contract(
            address=w3.to_checksum_address(self.usdc_address),
            abi=ERC20_ABI,
        )
        spender = w3.to_checksum_address(self.sports_amm_address)
        current = await usdc.functions.allowance(owner, spender).call()
        if current >= amount:
            return None
        tx = await usdc.functions.approve(spender, amount).build_transaction(
            await self._build_base_tx(w3, owner)
        )
        return await self._send_tx(w3, tx)

    async def trade(self, trade_data: tuple[Any, ...]) -> str:
        if not self._account:
            raise RuntimeError("Private key required for trade")
        w3 = await self._web3()
        amm = w3.eth.contract(
            address=w3.to_checksum_address(self.sports_amm_address),
            abi=SPORTS_AMM_V2_ABI,
        )
        tx = await amm.functions.trade(trade_data).build_transaction(
            await self._build_base_tx(w3, self._account.address)
        )
        return await self._send_tx(w3, tx)

    async def _build_base_tx(self, w3: AsyncWeb3, from_address: str) -> dict[str, Any]:
        nonce = await w3.eth.get_transaction_count(from_address)
        return {
            "from": from_address,
            "nonce": nonce,
            "chainId": self.chain_id,
        }

    async def _send_tx(self, w3: AsyncWeb3, tx: dict[str, Any]) -> str:
        if not self._account:
            raise RuntimeError("Private key required")
        signed = self._account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.get("status") != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")
        return tx_hash.hex()
