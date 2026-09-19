import hashlib
import json
from typing import Any


def canonical_json(data: dict[str, Any]) -> str:
    """Serialize record data in a stable, deterministic way for hashing.

    Canonical JSON matters because Python dicts are unordered. We sort keys and remove
    unnecessary whitespace so the exact same record content always produces the same hash.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_record_hash(record_data: dict[str, Any]) -> str:
    """Compute the SHA-256 hash for a record using canonical JSON serialization."""
    canonical = canonical_json(record_data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_record_hash_payload(
    receipt_id: str,
    sequence_no: int,
    prompt: str,
    response: str,
    timestamp: str,
    previous_hash: str,
) -> dict[str, Any]:
    """Build the exact record content used for hashing and verification."""
    return {
        "receipt_id": receipt_id,
        "sequence_no": sequence_no,
        "prompt": prompt,
        "response": response,
        "timestamp": timestamp,
        "previous_hash": previous_hash,
    }
