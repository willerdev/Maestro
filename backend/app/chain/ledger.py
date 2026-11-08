"""In-memory Project Coin ledger. Balances are derived by replaying blocks."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.chain.crypto import ADDRESS, address_for, canonical, meets_difficulty, sha256_hex, verify_message


class ChainError(Exception):
    pass


@dataclass(frozen=True)
class CoinParams:
    name: str = "Project Coin"
    symbol: str = "PCOIN"
    max_supply: int = 21_000_000 * 100_000_000
    initial_reward: int = 50 * 100_000_000
    halving_interval: int = 210_000
    difficulty: int = 16
    fee: int = 100_000

    def __post_init__(self) -> None:
        if self.max_supply < 0 or self.initial_reward < 0 or self.fee < 0:
            raise ChainError("Coin amounts cannot be negative")
        if self.halving_interval < 1:
            raise ChainError("Halving interval must be at least 1")
        if not 0 <= self.difficulty <= 256:
            raise ChainError("Difficulty must be between 0 and 256")


@dataclass
class Transfer:
    sender: str
    recipient: str
    amount: int
    fee: int
    nonce: int
    public_key: str
    signature: str

    def payload(self) -> dict:
        return {
            "amount": self.amount,
            "fee": self.fee,
            "nonce": self.nonce,
            "public_key": self.public_key,
            "recipient": self.recipient,
            "sender": self.sender,
        }

    def tx_hash(self) -> str:
        body = self.payload()
        body["signature"] = self.signature
        return sha256_hex(canonical(body))


@dataclass
class Reward:
    recipient: str
    amount: int
    height: int

    def tx_hash(self) -> str:
        return sha256_hex(canonical({"amount": self.amount, "height": self.height, "kind": "reward", "recipient": self.recipient}))


@dataclass
class Block:
    index: int
    timestamp: int
    previous_hash: str
    nonce: int
    difficulty: int
    miner: str
    reward: int
    transfers: list[Transfer] = field(default_factory=list)
    reward_tx: Reward | None = None

    def tx_hashes(self) -> list[str]:
        hashes = [tx.tx_hash() for tx in self.transfers]
        if self.reward_tx is not None:
            hashes.append(self.reward_tx.tx_hash())
        return hashes

    def block_hash(self) -> str:
        header = {
            "difficulty": self.difficulty,
            "index": self.index,
            "miner": self.miner,
            "nonce": self.nonce,
            "previous_hash": self.previous_hash,
            "reward": self.reward,
            "timestamp": self.timestamp,
            "transactions": self.tx_hashes(),
        }
        return sha256_hex(canonical(header))


def raw_subsidy(height: int, params: CoinParams) -> int:
    if height <= 0:
        return 0
    era = (height - 1) // params.halving_interval
    if era >= 63:
        return 0
    return params.initial_reward >> era


class Ledger:
    """One organization's chain. Confirmed state is whatever the blocks replay to."""

    def __init__(self, params: CoinParams) -> None:
        self.params = params
        self.blocks: list[Block] = []
        self.pending: list[Transfer] = []
        self.confirmed: set[str] = set()

    def create_genesis(self, timestamp: int = 0) -> Block:
        if self.blocks:
            raise ChainError("Genesis already exists")
        block = Block(0, timestamp, "0" * 64, 0, self.params.difficulty, "genesis", 0)
        from app.chain.miner import find_nonce

        found = find_nonce(block, cpu_percent=100)
        if found is None:
            raise ChainError("Genesis proof of work was not found")
        block.nonce = found[0]
        self.accept(block)
        return block

    def height(self) -> int:
        return self.blocks[-1].index if self.blocks else -1

    def work(self) -> int:
        return sum(1 << block.difficulty for block in self.blocks)

    def subsidy_for(self, height: int, minted: int) -> int:
        room = self.params.max_supply - minted
        if room <= 0:
            return 0
        return min(raw_subsidy(height, self.params), room)

    def state(self) -> tuple[dict[str, int], dict[str, int], int]:
        balances: dict[str, int] = {}
        nonces: dict[str, int] = {}
        minted = 0
        for block in self.blocks:
            minted = _apply_block(self.params, balances, nonces, block, minted)
        return balances, nonces, minted

    def available(self, address: str) -> int:
        balances, _, _ = self.state()
        spendable = balances.get(address, 0)
        for tx in self.pending:
            if tx.sender == address:
                spendable -= tx.amount + tx.fee
        return spendable

    def pending_incoming(self, address: str) -> int:
        return sum(tx.amount for tx in self.pending if tx.recipient == address)

    def totals(self, address: str) -> dict[str, int]:
        mined = received = sent = 0
        for block in self.blocks:
            if block.reward_tx is not None and block.reward_tx.recipient == address:
                mined += block.reward_tx.amount
            for tx in block.transfers:
                if tx.recipient == address:
                    received += tx.amount
                if tx.sender == address:
                    sent += tx.amount
        return {"mined": mined, "received": received, "sent": sent}

    def next_nonce(self, sender: str) -> int:
        _, nonces, _ = self.state()
        extra = sum(1 for tx in self.pending if tx.sender == sender)
        return nonces.get(sender, 0) + extra

    def add_transfer(self, tx: Transfer) -> None:
        if tx.tx_hash() in self.confirmed or any(item.tx_hash() == tx.tx_hash() for item in self.pending):
            raise ChainError("That transaction is already in the chain")
        balances, nonces, _ = self.state()
        for item in self.pending:
            _apply_transfer(self.params, balances, nonces, item)
        _apply_transfer(self.params, balances, nonces, tx)
        self.pending.append(tx)

    def candidate(self, miner: str, timestamp: int) -> Block:
        if not self.blocks:
            raise ChainError("Create the genesis block first")
        if not ADDRESS.match(miner):
            raise ChainError("Miner address is invalid")
        balances, nonces, _ = self.state()
        included: list[Transfer] = []
        for tx in self.pending:
            try:
                _apply_transfer(self.params, balances, nonces, tx)
            except ChainError:
                continue
            included.append(tx)
        height = self.blocks[-1].index + 1
        minted = sum(block.reward for block in self.blocks)
        subsidy = self.subsidy_for(height, minted)
        fees = sum(tx.fee for tx in included)
        reward_tx = Reward(miner, subsidy + fees, height) if subsidy + fees else None
        return Block(
            index=height,
            timestamp=max(timestamp, self.blocks[-1].timestamp),
            previous_hash=self.blocks[-1].block_hash(),
            nonce=0,
            difficulty=self.params.difficulty,
            miner=miner,
            reward=subsidy,
            transfers=included,
            reward_tx=reward_tx,
        )

    def accept(self, block: Block) -> None:
        if block.index > 0 and block.difficulty != self.params.difficulty:
            raise ChainError("A new block must use the current difficulty")
        self.blocks.append(block)
        try:
            self.validate()
        except ChainError:
            self.blocks.pop()
            raise
        for tx in block.transfers:
            self.confirmed.add(tx.tx_hash())
        if block.reward_tx is not None:
            self.confirmed.add(block.reward_tx.tx_hash())
        included = {tx.tx_hash() for tx in block.transfers}
        self.pending = [tx for tx in self.pending if tx.tx_hash() not in included]

    def validate(self) -> None:
        if not self.blocks:
            raise ChainError("The chain is empty")
        seen_blocks: set[str] = set()
        seen_tx: set[str] = set()
        balances: dict[str, int] = {}
        nonces: dict[str, int] = {}
        minted = 0
        previous: Block | None = None
        for block in self.blocks:
            digest = block.block_hash()
            if digest in seen_blocks:
                raise ChainError("A block hash is duplicated")
            seen_blocks.add(digest)
            if not meets_difficulty(digest, block.difficulty):
                raise ChainError("A block does not satisfy its proof of work")
            if previous is None:
                if block.index != 0 or block.previous_hash != "0" * 64 or block.miner != "genesis" or block.reward != 0 or block.transfers or block.reward_tx is not None:
                    raise ChainError("The genesis block is invalid")
            else:
                if block.index != previous.index + 1 or block.previous_hash != previous.block_hash():
                    raise ChainError("A block does not follow the previous block")
                if block.timestamp < previous.timestamp:
                    raise ChainError("A block timestamp moves backwards")
                if not ADDRESS.match(block.miner):
                    raise ChainError("A miner address is invalid")
                expected = self.subsidy_for(block.index, minted)
                if block.reward != expected:
                    raise ChainError("A block reward does not match the schedule")
            fees = 0
            for tx in block.transfers:
                if tx.tx_hash() in seen_tx:
                    raise ChainError("A transaction is duplicated")
                _apply_transfer(self.params, balances, nonces, tx)
                seen_tx.add(tx.tx_hash())
                fees += tx.fee
            total = block.reward + fees
            if block.index == 0:
                pass
            elif total == 0:
                if block.reward_tx is not None:
                    raise ChainError("An empty block includes a reward")
            else:
                reward = block.reward_tx
                if reward is None or reward.amount != total or reward.recipient != block.miner or reward.height != block.index:
                    raise ChainError("The mining reward transaction is invalid")
                if reward.tx_hash() in seen_tx:
                    raise ChainError("A transaction is duplicated")
                seen_tx.add(reward.tx_hash())
                balances[block.miner] = balances.get(block.miner, 0) + total
            minted += block.reward
            if minted > self.params.max_supply:
                raise ChainError("Minted coins exceed the maximum supply")
            previous = block

    def replace_if_stronger(self, other: "Ledger") -> None:
        if self.params != other.params:
            raise ChainError("The chains use different coin rules")
        other.validate()
        self.validate()
        if other.blocks[0].block_hash() != self.blocks[0].block_hash():
            raise ChainError("The chains do not share a genesis block")
        hashes = [block.block_hash() for block in other.blocks]
        if len(hashes) != len(set(hashes)):
            raise ChainError("The offered chain repeats a block")
        if other.work() <= self.work():
            raise ChainError("The offered chain has less work")
        confirmed = set()
        for block in other.blocks:
            for tx in block.transfers:
                confirmed.add(tx.tx_hash())
        self.blocks = list(other.blocks)
        self.confirmed = confirmed
        self.pending = [tx for tx in self.pending if tx.tx_hash() not in confirmed]


def _apply_block(params: CoinParams, balances: dict[str, int], nonces: dict[str, int], block: Block, minted: int) -> int:
    fees = 0
    for tx in block.transfers:
        _apply_transfer(params, balances, nonces, tx)
        fees += tx.fee
    if block.reward_tx is not None:
        balances[block.miner] = balances.get(block.miner, 0) + block.reward_tx.amount
    return minted + block.reward


def _apply_transfer(params: CoinParams, balances: dict[str, int], nonces: dict[str, int], tx: Transfer) -> None:
    if tx.amount <= 0 or tx.fee < 0:
        raise ChainError("A transaction amount is invalid")
    if tx.fee != params.fee:
        raise ChainError("A transaction fee does not match the chain fee")
    if tx.sender == tx.recipient or not ADDRESS.match(tx.sender) or not ADDRESS.match(tx.recipient):
        raise ChainError("A transaction address is invalid")
    try:
        if address_for(tx.public_key) != tx.sender:
            raise ChainError("The public key does not match the sender")
    except ValueError as exc:
        raise ChainError("The public key does not match the sender") from exc
    if not verify_message(tx.public_key, canonical(tx.payload()), tx.signature):
        raise ChainError("The transaction signature is invalid")
    expected = nonces.get(tx.sender, 0)
    if tx.nonce != expected:
        raise ChainError("The transaction nonce is not the next nonce")
    cost = tx.amount + tx.fee
    if balances.get(tx.sender, 0) < cost:
        raise ChainError("The balance is too low")
    balances[tx.sender] = balances.get(tx.sender, 0) - cost
    balances[tx.recipient] = balances.get(tx.recipient, 0) + tx.amount
    nonces[tx.sender] = expected + 1


def sign_transfer(private_hex: str, public_hex: str, sender: str, recipient: str, amount: int, fee: int, nonce: int) -> Transfer:
    from app.chain.crypto import sign_message

    tx = Transfer(sender, recipient, amount, fee, nonce, public_hex, "")
    tx.signature = sign_message(private_hex, canonical(tx.payload()))
    return tx
