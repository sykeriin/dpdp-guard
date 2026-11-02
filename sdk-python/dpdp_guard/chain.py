"""Hash-chain helpers shared by the SDK (local mode) and the server."""
import hashlib
import json

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_hash(prev_hash: str, event: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(event)).encode("utf-8")).hexdigest()


def verify_chain(rows):
    """rows: iterable of dicts with prev_hash, hash, event (ordered). Returns (ok, bad_index|None)."""
    prev = GENESIS
    for i, r in enumerate(rows):
        if r["prev_hash"] != prev or compute_hash(prev, r["event"]) != r["hash"]:
            return False, i
        prev = r["hash"]
    return True, None


def hash_principal(tenant: str, user_id: str, salt: str = "") -> str:
    return hashlib.sha256(f"{salt}|{tenant}|{user_id}".encode()).hexdigest()[:32]
