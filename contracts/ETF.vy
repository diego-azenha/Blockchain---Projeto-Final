# @version 0.4.3

"""
ETF Example – FINAL (view/internal fixes)
- internal helpers that only read state are @view @internal
- oracle getPrice via staticcall (returns tuple)
- ERC20 balanceOf via staticcall (returns uint256)
- ERC20 transfer/transferFrom via extcall
- integer division '//' everywhere
"""

# -------- ERC20 INTERFACE
interface ERC20:
    def transfer(_to: address, _value: uint256) -> bool: nonpayable
    def transferFrom(_from: address, _to: address, _value: uint256) -> bool: nonpayable
    def balanceOf(_owner: address) -> uint256: view
    def approve(_spender: address, _value: uint256) -> bool: nonpayable

# -------- ORACLE INTERFACE
interface OracleIface:
    def getPrice(symbol: bytes32) -> (uint256, uint256): view

# --- CONSTANTS
PRICE_SCALE: constant(uint256) = 10 ** 8
SHARE_DECIMALS: constant(uint256) = 10 ** 18
TOKEN_DECIMALS: constant(uint256) = 10 ** 18

# --- STORAGE
tokens: public(address[3])
symbols: public(bytes32[3])
oracle: public(address)
total_shares: public(uint256)
balances: public(HashMap[address, uint256])

event Mint:
    to: address
    shares: uint256
    value_scaled: uint256

event Redeem:
    from_: address
    shares: uint256
    value_scaled: uint256


# -------- CONSTRUCTOR
@deploy
def __init__(_tokens: address[3], _symbols: bytes32[3], _oracle: address):
    for i: uint256 in range(3):
        assert _tokens[i] != 0x0000000000000000000000000000000000000000, "invalid token"
        self.tokens[i] = _tokens[i]
        self.symbols[i] = _symbols[i]

    assert _oracle != 0x0000000000000000000000000000000000000000, "invalid oracle"
    self.oracle = _oracle
    self.total_shares = 0


# -------- INTERNAL HELPERS (now marked view)
@view
@internal
def _get_token_value_scaled(token_index: uint256, amount: uint256) -> uint256:
    # getPrice returns (price_scaled, timestamp)
    price_tuple: (uint256, uint256) = staticcall OracleIface(self.oracle).getPrice(self.symbols[token_index])
    price_scaled: uint256 = price_tuple[0]
    return (amount * price_scaled) // TOKEN_DECIMALS


@view
@internal
def _totalValueScaled() -> uint256:
    total: uint256 = 0
    for i: uint256 in range(3):
        # balanceOf returns uint256
        bal: uint256 = staticcall ERC20(self.tokens[i]).balanceOf(self)
        total += self._get_token_value_scaled(i, bal)
    return total


# -------- VIEW FUNCTIONS
@view
@external
def totalValueScaled() -> uint256:
    return self._totalValueScaled()


@view
@external
def pricePerShareScaled() -> uint256:
    total_value: uint256 = self._totalValueScaled()  # ok now: calling a view internal
    if self.total_shares == 0:
        return PRICE_SCALE
    return (total_value * SHARE_DECIMALS) // self.total_shares


# -------- MINT
@external
def mintWithUnderlying(amounts: uint256[3]) -> uint256:
    total_value: uint256 = 0
    shares_to_mint: uint256 = 0
    pps_scaled: uint256 = 0

    for i: uint256 in range(3):
        if amounts[i] > 0:
            ok: bool = extcall ERC20(self.tokens[i]).transferFrom(msg.sender, self, amounts[i])
            assert ok, "transferFrom failed"
            # call internal view helper to compute value of deposited tokens
            total_value += self._get_token_value_scaled(i, amounts[i])

    assert total_value > 0, "no value deposited"

    if self.total_shares == 0:
        shares_to_mint = (total_value * SHARE_DECIMALS) // PRICE_SCALE
    else:
        current_total_value: uint256 = self._totalValueScaled()
        pps_scaled = (current_total_value * SHARE_DECIMALS) // self.total_shares
        assert pps_scaled > 0, "pps zero"
        shares_to_mint = (total_value * SHARE_DECIMALS) // pps_scaled

    assert shares_to_mint > 0, "zero shares"

    self.balances[msg.sender] += shares_to_mint
    self.total_shares += shares_to_mint

    log Mint(msg.sender, shares_to_mint, total_value)
    return shares_to_mint


# -------- REDEEM
@external
def redeemForUnderlying(shares: uint256) -> uint256[3]:
    assert shares > 0, "zero shares"
    assert self.balances[msg.sender] >= shares, "insufficient shares"
    assert self.total_shares >= shares, "bad pool"

    total_value: uint256 = self._totalValueScaled()
    value_shares: uint256 = (total_value * shares) // self.total_shares

    out: uint256[3] = [0, 0, 0]

    for i: uint256 in range(3):
        bal: uint256 = staticcall ERC20(self.tokens[i]).balanceOf(self)
        if total_value > 0:
            out[i] = (bal * value_shares) // total_value
        else:
            out[i] = 0

        if out[i] > 0:
            ok: bool = extcall ERC20(self.tokens[i]).transfer(msg.sender, out[i])
            assert ok, "transfer failed"

    self.balances[msg.sender] -= shares
    self.total_shares -= shares

    log Redeem(msg.sender, shares, value_shares)
    return out
