"""AML Monitor — Blockchain API clients for real transaction polling.

Supports BTC, ETH, USDT (ERC20/TRC20), and XMR via public APIs.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.services.transaction_service import ingest_transaction

logger = logging.getLogger(__name__)


# ===========================================================================
# Bitcoin (BTC) - via BlockCypher or public mempool API
# ===========================================================================

class BitcoinClient:
    """BTC blockchain client using public APIs."""

    def __init__(self):
        self.base_url = "https://mempool.space/api"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_recent_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent mempool transactions."""
        try:
            response = await self.client.get(f"{self.base_url}/mempool")
            data = response.json()
            return data.get("recently_seen", [])[:limit]
        except Exception as e:
            logger.error(f"Bitcoin client error: {e}")
            return []

    async def get_block_transactions(self, block_height: Optional[int] = None, limit: int = 25) -> List[Dict[str, Any]]:
        """Get transactions from latest or specified block."""
        try:
            if block_height is None:
                response = await self.client.get(f"{self.base_url}/blocks/tip/hash")
                block_hash = response.text.strip()
                response = await self.client.get(f"{self.base_url}/block/{block_hash}/txs")
            else:
                response = await self.client.get(f"{self.base_url}/block-height/{block_height}/txs")
            data = response.json()
            return data[:limit]
        except Exception as e:
            logger.error(f"Bitcoin block client error: {e}")
            return []

    async def get_transaction_details(self, txid: str) -> Optional[Dict[str, Any]]:
        """Get detailed info for a specific transaction."""
        try:
            response = await self.client.get(f"{self.base_url}/tx/{txid}")
            return response.json()
        except Exception:
            return None

    async def close(self):
        await self.client.aclose()


# ===========================================================================
# Ethereum (ETH) - via Etherscan or public RPC
# ===========================================================================

class EthereumClient:
    """ETH blockchain client using public RPC endpoints."""

    def __init__(self):
        # Public RPC endpoints (free, rate-limited)
        self.rpc_urls = [
            "https://eth.llamarpc.com",
            "https://rpc.ankr.com/eth",
            "https://ethereum.publicnode.com",
        ]
        self.current_rpc = 0
        self.client = httpx.AsyncClient(timeout=30.0)

    def _get_next_rpc(self) -> str:
        url = self.rpc_urls[self.current_rpc]
        self.current_rpc = (self.current_rpc + 1) % len(self.rpc_urls)
        return url

    async def _rpc_call(self, method: str, params: List[Any] = None) -> Optional[Any]:
        """Make a JSON-RPC call."""
        url = self._get_next_rpc()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1,
        }
        try:
            response = await self.client.post(url, json=payload, headers={"Content-Type": "application/json"})
            data = response.json()
            return data.get("result")
        except Exception as e:
            logger.error(f"Ethereum RPC error: {e}")
            return None

    async def get_block_number(self) -> Optional[int]:
        """Get current block number."""
        result = await self._rpc_call("eth_blockNumber")
        if result:
            return int(result, 16)
        return None

    async def get_block_by_number(self, block_number: int, full: bool = True) -> Optional[Dict[str, Any]]:
        """Get block by number."""
        hex_block = hex(block_number)
        result = await self._rpc_call("eth_getBlockByNumber", [hex_block, full])
        return result

    async def get_latest_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get transactions from latest blocks."""
        transactions = []
        current_block = await self.get_block_number()

        if current_block is None:
            return transactions

        # Get transactions from last N blocks
        for block_num in range(max(1, current_block - 3), current_block + 1):
            block = await self.get_block_by_number(block_num)
            if block and block.get("transactions"):
                for tx in block["transactions"][:10]:  # Limit per block
                    tx["block_number"] = block_num
                    tx["chain"] = "eth"
                    transactions.append(tx)
                    if len(transactions) >= limit:
                        return transactions

        return transactions

    async def get_transaction_details(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details by hash."""
        result = await self._rpc_call("eth_getTransactionByHash", [tx_hash])
        return result

    async def get_balance(self, address: str, block: str = "latest") -> Optional[Decimal]:
        """Get ETH balance of an address."""
        result = await self._rpc_call("eth_getBalance", [address, block])
        if result:
            return Decimal(int(result, 16)) / Decimal("1e18")
        return None

    async def close(self):
        await self.client.aclose()


# ===========================================================================
# USDT (ERC20/TRC20) - via Etherscan and TRON API
# ===========================================================================

class USDTClient:
    """USDT blockchain client for ERC20 and TRC20 networks."""

    def __init__(self):
        self.eth_client = EthereumClient()
        # Public TRON API endpoints
        self.tron_urls = [
            "https://api.trongrid.io",
            "https://tron-rpc.publicnode.com",
        ]
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_eth_usdt_transfers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get USDT (ERC20) transfers via Ethereum."""
        # USDT contract address
        usdt_contract = "0xdac17f958d2ee523a2206206994597c13d831ec7"
        transfers = []

        # Get recent blocks
        current_block = await self.eth_client.get_block_number()
        if current_block is None:
            return []

        for block_num in range(max(1, current_block - 5), current_block + 1):
            block = await self.eth_client.get_block_by_number(block_num)
            if not block or not block.get("transactions"):
                continue

            for tx in block["transactions"]:
                # Check if this is a USDT transfer (has to or data field)
                if tx.get("to") == usdt_contract or (tx.get("input") and tx["input"].startswith("0xa9059cbb")):
                    transfer = {
                        "txid": tx.get("hash"),
                        "from_address": tx.get("from"),
                        "to_address": tx.get("to"),
                        "amount": "0",
                        "block_number": block_num,
                        "timestamp": block.get("timestamp", 0),
                        "chain": "eth_usdt",
                        "contract": usdt_contract,
                    }
                    transfers.append(transfer)
                    if len(transfers) >= limit:
                        return transfers

        return transfers

    async def get_tron_usdt_transfers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get USDT (TRC20) transfers via TRON API."""
        transfers = []
        usdt_contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

        try:
            # Get recent transactions from main contract
            response = await self.client.get(
                f"{self.tron_urls[0]}/v1/accounts/{usdt_contract}/transactions",
                params={"limit": limit, "only_confirmed": True}
            )
            data = response.json()

            if data.get("data"):
                for tx in data["data"]:
                    transfer = {
                        "txid": tx.get("txID"),
                        "from_address": tx.get("from"),
                        "to_address": tx.get("to"),
                        "amount": str(tx.get("amount", 0)),
                        "block_number": tx.get("block_number", 0),
                        "timestamp": tx.get("timestamp", 0) // 1000,  # Convert ms to seconds
                        "chain": "tron_usdt",
                    }
                    transfers.append(transfer)
        except Exception as e:
            logger.error(f"TRON USDT client error: {e}")

        return transfers

    async def get_recent_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get USDT transactions from both networks."""
        eth_txs = await self.get_eth_usdt_transfers(limit // 2)
        tron_txs = await self.get_tron_usdt_transfers(limit // 2)
        return eth_txs + tron_txs

    async def close(self):
        await self.eth_client.close()
        await self.client.aclose()


# ===========================================================================
# Monero (XMR) - via public Monero nodes
# ===========================================================================

class MoneroClient:
    """XMR blockchain client using public RPC nodes."""

    def __init__(self):
        # Public Monero RPC endpoints
        self.rpc_urls = [
            "https://xmr.llamarpc.com",
            "https://monero-rpc.publicnode.com",
            "https://node.getmonero.org",
        ]
        self.current_rpc = 0
        self.client = httpx.AsyncClient(timeout=30.0)

    def _get_next_rpc(self) -> str:
        url = self.rpc_urls[self.current_rpc]
        self.current_rpc = (self.current_rpc + 1) % len(self.rpc_urls)
        return url

    async def _rpc_call(self, method: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Make a JSON-RPC call."""
        url = self._get_next_rpc()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }
        try:
            response = await self.client.post(url, json=payload, headers={"Content-Type": "application/json"})
            data = response.json()
            return data.get("result")
        except Exception as e:
            logger.error(f"Monero RPC error: {e}")
            return None

    async def get_block_count(self) -> Optional[int]:
        """Get current block count."""
        result = await self._rpc_call("getblockcount")
        if result:
            return result.get("count", 0)
        return None

    async def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        """Get block by height."""
        result = await self._rpc_call("get_block", {"height": height})
        return result

    async def get_pool_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent transactions from mempool."""
        transactions = []

        try:
            # Get recent blocks
            block_count = await self.get_block_count()
            if block_count is None:
                return []

            for height in range(max(1, block_count - 3), block_count + 1):
                block = await self.get_block_by_height(height)
                if block and block.get("blob"):
                    # Parse basic info from block
                    txs = block.get("txs", [])
                    for tx in txs[:10]:
                        transactions.append({
                            "txid": tx.get("txid", ""),
                            "amount": str(tx.get("amount", 0)),
                            "fee": str(tx.get("fee", 0)),
                            "block_height": height,
                            "timestamp": block.get("timestamp", 0),
                            "chain": "xmr",
                        })
                        if len(transactions) >= limit:
                            return transactions
        except Exception as e:
            logger.error(f"Monero pool transactions error: {e}")

        return transactions

    async def get_recent_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent transactions from latest blocks."""
        return await self.get_pool_transactions(limit)

    async def close(self):
        await self.client.aclose()


# ===========================================================================
# Factory function to get all clients
# ===========================================================================

async def get_all_blockchain_clients() -> Dict[str, Any]:
    """Get all blockchain clients initialized."""
    return {
        "btc": BitcoinClient(),
        "eth": EthereumClient(),
        "usdt": USDTClient(),
        "xmr": MoneroClient(),
    }
