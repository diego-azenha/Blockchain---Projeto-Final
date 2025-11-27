# @version 0.4.3

NULL_ADDR: constant(address) = 0x0000000000000000000000000000000000000000

name: public(String[64])
symbol: public(String[16])
decimals: public(uint256)
_totalSupply: uint256
balances: HashMap[address, uint256]
allowances: HashMap[address, HashMap[address, uint256]]
owner: public(address)

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

event Approval:
    owner: indexed(address)
    spender: indexed(address)
    value: uint256

@deploy
def __init__(_name: String[64], _symbol: String[16]):
    self.name = _name
    self.symbol = _symbol
    self.decimals = 18
    self.owner = msg.sender

@view
@external
def totalSupply() -> uint256:
    return self._totalSupply

@view
@external
def balanceOf(account: address) -> uint256:
    return self.balances[account]

@external
def transfer(recipient: address, amount: uint256) -> bool:
    assert self.balances[msg.sender] >= amount, "insufficient"
    self.balances[msg.sender] -= amount
    self.balances[recipient] += amount
    log Transfer(sender=msg.sender, receiver=recipient, value=amount)
    return True

@external
def approve(spender: address, amount: uint256) -> bool:
    self.allowances[msg.sender][spender] = amount
    log Approval(owner=msg.sender, spender=spender, value=amount)
    return True

@external
def transferFrom(sender: address, recipient: address, amount: uint256) -> bool:
    allowed: uint256 = self.allowances[sender][msg.sender]

    if msg.sender != sender:
        assert allowed >= amount, "allowance"
        self.allowances[sender][msg.sender] = allowed - amount

    assert self.balances[sender] >= amount, "insufficient"
    self.balances[sender] -= amount
    self.balances[recipient] += amount
    log Transfer(sender=sender, receiver=recipient, value=amount)
    return True

@external
def mint(to: address, amount: uint256):
    assert msg.sender == self.owner, "only owner"
    self.balances[to] += amount
    self._totalSupply += amount
    log Transfer(sender=NULL_ADDR, receiver=to, value=amount)
