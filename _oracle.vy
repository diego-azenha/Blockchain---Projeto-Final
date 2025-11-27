# @version 0.4.3

PRICE_SCALE: constant(uint256) = 10 ** 8

prices: public(HashMap[bytes32, uint256])
timestamps: public(HashMap[bytes32, uint256])
updater: public(address)

event PriceUpdated:
    symbol: bytes32
    price: uint256
    ts: uint256


@deploy
def __init__(_updater: address):
    assert _updater != 0x0000000000000000000000000000000000000000, "invalid updater"
    self.updater = _updater


@external
def setPrice(symbol: bytes32, price: uint256, ts: uint256):
    """
    Only updater may call.
    price: integer, scaled by PRICE_SCALE externally
    ts: unix timestamp
    """
    assert msg.sender == self.updater, "only updater"

    # timestamp sanity: allow small future skew, reject very old timestamps
    assert ts <= block.timestamp + 300, "ts too far future"
    assert ts >= block.timestamp - 86400, "ts too old"

    self.prices[symbol] = price
    self.timestamps[symbol] = ts

    log PriceUpdated(symbol=symbol, price=price, ts=ts)


@view
@external
def getPrice(symbol: bytes32) -> (uint256, uint256):
    return (self.prices[symbol], self.timestamps[symbol])


@view
@external
def getPriceString(sym: String[32]) -> (uint256, uint256):
    """
    UI helper: pass "AAPL" etc. (no hex). Returns (price_scaled, timestamp).
    Uses direct conversion to Bytes[32] which pads with zeros.
    """
    bs: Bytes[32] = convert(sym, Bytes[32])      # convert & pad
    key: bytes32 = convert(bs, bytes32)         # convert to bytes32
    return (self.prices[key], self.timestamps[key])


@view
@external
def getTimestampString(sym: String[32]) -> uint256:
    bs: Bytes[32] = convert(sym, Bytes[32])
    key: bytes32 = convert(bs, bytes32)
    return self.timestamps[key]


@external
def setUpdater(new_updater: address):
    assert msg.sender == self.updater, "only updater"
    assert new_updater != 0x0000000000000000000000000000000000000000, "invalid updater"
    self.updater = new_updater
