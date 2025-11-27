import os
import sys
import time
import argparse
import logging
from typing import List

from dotenv import load_dotenv
from web3 import Web3, exceptions
from eth_account import Account
import yfinance as yf

load_dotenv()

# -------- CONFIG / ENV (defaults)
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
ORACLE_ADDRESS = os.getenv("ORACLE_ADDRESS", "")
UPDATER_PRIVATE_KEY = os.getenv("UPDATER_PRIVATE_KEY", "")
PRICE_SCALE = int(os.getenv("PRICE_SCALE", 10**8))
GAS_MULTIPLIER = float(os.getenv("GAS_MULTIPLIER", "1.1"))
CHAIN_ID = int(os.getenv("CHAIN_ID", "31337"))  # Hardhat default

# Minimal ABI for oracle.setPrice(bytes32,uint256,uint256)
ORACLE_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "symbol", "type": "bytes32"},
            {"internalType": "uint256", "name": "price", "type": "uint256"},
            {"internalType": "uint256", "name": "ts", "type": "uint256"},
        ],
        "name": "setPrice",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# -------- Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("oracle_updater")


# -------- Helpers

def symbol_to_bytes32(sym: str) -> bytes:
    """Encode a short ASCII symbol into 32-byte padded value for bytes32 param."""
    b = sym.encode("utf-8")
    if len(b) > 32:
        raise ValueError("symbol too long for bytes32")
    return b.ljust(32, b"\0")


def fetch_price_yahoo(ticker: str) -> float:
    """Fetch a latest price using yfinance."""
    try:
        tk = yf.Ticker(ticker)

        info = getattr(tk, "fast_info", None)
        if info and "last_price" in info:
            return float(info["last_price"])

        df = tk.history(period="1d", interval="1m")
        if not df.empty:
            return float(df["Close"].iloc[-1])

        info2 = getattr(tk, "info", {})
        if "regularMarketPrice" in info2 and info2["regularMarketPrice"] is not None:
            return float(info2["regularMarketPrice"])

    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, str(e))

    raise RuntimeError(f"failed to fetch price for {ticker}")


# -------- BUILD AND SEND TX (CORRIGIDO)

def build_and_send_setprice(w3: Web3, oracle_contract, acct, symbol: str, price_scaled: int, ts: int, dry_run: bool = False):
    symbol_bytes = symbol_to_bytes32(symbol)
    func = oracle_contract.functions.setPrice(symbol_bytes, price_scaled, ts)

    # build base tx
    tx = func.build_transaction(
        {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "chainId": CHAIN_ID,
        }
    )

    # estimate gas
    try:
        gas_est = w3.eth.estimate_gas(tx)
        gas_limit = int(gas_est * GAS_MULTIPLIER)
    except Exception as e:
        logger.warning("gas estimate failed; using 200k gas (error: %s)", e)
        gas_limit = 200_000

    # EIP-1559 fee model
    try:
        base_fee = w3.eth.gas_price
    except Exception:
        base_fee = 1_000_000_000  # fallback 1 gwei

    max_priority = int(base_fee * 0.1)
    max_fee = base_fee + max_priority

    tx.update({
        "gas": gas_limit,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority,
    })

    # dry run
    if dry_run:
        logger.info(
            "[dry-run] Prepared tx for %s price=%s ts=%s gas=%s maxFee=%s maxPrio=%s",
            symbol, price_scaled, ts, gas_limit, max_fee, max_priority
        )
        return None

    # sign and send
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info("Sent setPrice tx for %s tx_hash=%s", symbol, tx_hash.hex())

    # wait receipt
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logger.info(
            "Tx mined for %s status=%s gasUsed=%s",
            symbol, receipt.status, receipt.gasUsed
        )
    except exceptions.TimeExhausted:
        logger.warning("Receipt timeout for %s (%s)", symbol, tx_hash.hex())
        return None

    return receipt


# -------- Runners

def run_once(w3: Web3, oracle_contract, acct, tickers: List[str], dry_run: bool = False):
    ts = int(time.time())
    for t in tickers:
        try:
            price = fetch_price_yahoo(t)
            price_scaled = int(round(price * PRICE_SCALE))
            logger.info("Ticker=%s price=%s scaled=%s", t, price, price_scaled)

            build_and_send_setprice(
                w3, oracle_contract, acct,
                t, price_scaled, ts,
                dry_run=dry_run
            )

            time.sleep(0.8)

        except Exception as e:
            logger.exception("Failed to update ticker %s: %s", t, e)


def run_watch(w3: Web3, oracle_contract, acct, tickers: List[str], interval: int, dry_run: bool = False):
    logger.info("Entering watch mode for tickers=%s interval=%ss (ctrl-c to stop)", tickers, interval)
    try:
        while True:
            run_once(w3, oracle_contract, acct, tickers, dry_run=dry_run)
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Watch stopped by user")


# -------- ARGS + MAIN

def parse_args():
    p = argparse.ArgumentParser()
    # ticker is now optional; fallback to TICKERS in .env
    p.add_argument("--ticker", "-t", type=str, required=False,
                   help="Comma separated tickers (overrides TICKERS env var), e.g. AAPL or AAPL,TSLA,GOOG")
    p.add_argument("--once", action="store_true", help="Run once and exit")
    p.add_argument("--watch", action="store_true", help="Run periodically")
    p.add_argument("--interval", type=int, default=60, help="Interval seconds for watch mode")
    p.add_argument("--rpc", type=str, default=RPC_URL, help="RPC URL (overrides .env)")
    p.add_argument("--oracle", type=str, default=ORACLE_ADDRESS, help="Oracle contract address (overrides .env)")
    p.add_argument("--pk", type=str, default=UPDATER_PRIVATE_KEY, help="Updater private key (overrides .env)")
    p.add_argument("--scale", type=int, default=PRICE_SCALE, help="PRICE_SCALE multiplier")
    p.add_argument("--dry-run", action="store_true", help="Do not send txs, only print what would be sent")
    return p.parse_args()


def main():
    args = parse_args()

    # --- fallback for tickers using .env if CLI not provided
    if args.ticker:
        tickers = [s.strip() for s in args.ticker.split(",") if s.strip()]
    else:
        env_tickers = os.getenv("TICKERS", "")
        if not env_tickers:
            logger.error("No tickers provided. Use --ticker or set TICKERS= in .env")
            sys.exit(1)
        tickers = [s.strip() for s in env_tickers.split(",") if s.strip()]

    rpc = args.rpc
    oracle_addr = None
    if args.oracle:
        try:
            oracle_addr = Web3.to_checksum_address(args.oracle)
        except Exception:
            logger.error("Invalid oracle address provided: %s", args.oracle)
            sys.exit(1)

    pk = args.pk
    if not rpc:
        logger.error("RPC URL not provided.")
        sys.exit(1)
    if not oracle_addr:
        logger.error("Oracle address not provided.")
        sys.exit(1)
    if not pk:
        logger.error("Updater private key not provided.")
        sys.exit(1)

    global PRICE_SCALE
    PRICE_SCALE = args.scale

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        logger.error("Failed to connect to RPC at %s", rpc)
        sys.exit(1)

    acct = Account.from_key(pk)
    logger.info("Using updater address %s", acct.address)
    logger.info("Tickers to update: %s", tickers)

    oracle_contract = w3.eth.contract(address=oracle_addr, abi=ORACLE_ABI)

    if args.dry_run:
        logger.info("Dry-run enabled: will not send transactions")

    if args.once:
        run_once(w3, oracle_contract, acct, tickers, dry_run=args.dry_run)
    elif args.watch:
        run_watch(w3, oracle_contract, acct, tickers, interval=args.interval, dry_run=args.dry_run)
    else:
        logger.info("Please pass --once or --watch. Exiting.")


if __name__ == "__main__":
    main()
