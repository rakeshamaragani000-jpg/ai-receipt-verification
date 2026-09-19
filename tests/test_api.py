import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "receipts.db"
    monkeypatch.setenv("RECEIPTS_DB_PATH", str(db_path))
    from main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_create_record(client):
    response = client.post(
        "/ask",
        json={
            "prompt": "What is machine learning?",
            "response": "Machine learning is a method of teaching computers to learn patterns from data.",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "receipt_id" in payload
    assert payload["prompt"] == "What is machine learning?"
    assert payload["response"] == "Machine learning is a method of teaching computers to learn patterns from data."
    assert payload["previous_hash"] == "GENESIS"
    assert payload["sequence_no"] == 1
    assert payload["current_hash"]


def test_verify_untampered_record(client):
    create_response = client.post(
        "/ask",
        json={
            "prompt": "Explain hashing.",
            "response": "Hashing converts data into a fixed-size digest for verification.",
        },
    )
    receipt_id = create_response.json()["receipt_id"]

    verify_response = client.post("/verify", json={"receipt_id": receipt_id})
    assert verify_response.status_code == 200, verify_response.text
    payload = verify_response.json()
    assert payload["valid"] is True
    assert payload["status"] == "valid"


def test_verify_detects_tampering(client):
    create_response = client.post(
        "/ask",
        json={
            "prompt": "Explain a hash chain.",
            "response": "A hash chain links each record to the previous hash.",
        },
    )
    receipt_id = create_response.json()["receipt_id"]

    db_path = Path(os.environ["RECEIPTS_DB_PATH"])
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE receipts SET response = ? WHERE receipt_id = ?",
            ("TAMPERED RESPONSE WITHOUT HASH UPDATE", receipt_id),
        )
        conn.commit()

    verify_response = client.post("/verify", json={"receipt_id": receipt_id})
    assert verify_response.status_code == 200, verify_response.text
    payload = verify_response.json()
    assert payload["valid"] is False
    assert payload["status"] == "tampered"


def test_invalid_prompt_is_rejected(client):
    response = client.post(
        "/ask",
        json={"prompt": "   ", "response": "This should be rejected because the prompt is blank."},
    )
    assert response.status_code == 422, response.text

    missing_response = client.post("/ask", json={"prompt": "Missing response field"})
    assert missing_response.status_code == 422, missing_response.text


def test_hash_chain_links_two_records(client):
    first = client.post(
        "/ask",
        json={"prompt": "First prompt", "response": "First response"},
    )
    first_payload = first.json()
    second = client.post(
        "/ask",
        json={"prompt": "Second prompt", "response": "Second response"},
    )
    second_payload = second.json()

    assert first_payload["previous_hash"] == "GENESIS"
    assert second_payload["previous_hash"] == first_payload["current_hash"]

    first_verify = client.post("/verify", json={"receipt_id": first_payload["receipt_id"]})
    second_verify = client.post("/verify", json={"receipt_id": second_payload["receipt_id"]})

    assert first_verify.json()["valid"] is True
    assert second_verify.json()["valid"] is True


def test_tampering_first_record_breaks_chain(client):
    first = client.post(
        "/ask",
        json={"prompt": "Chain A", "response": "Chain A response"},
    )
    first_id = first.json()["receipt_id"]
    second = client.post(
        "/ask",
        json={"prompt": "Chain B", "response": "Chain B response"},
    )
    second_id = second.json()["receipt_id"]

    db_path = Path(os.environ["RECEIPTS_DB_PATH"])
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE receipts SET response = ? WHERE receipt_id = ?",
            ("TAMPERED FIRST RECORD", first_id),
        )
        conn.commit()

    first_verify = client.post("/verify", json={"receipt_id": first_id})
    second_verify = client.post("/verify", json={"receipt_id": second_id})

    assert first_verify.json()["valid"] is False
    assert second_verify.json()["valid"] is False
    assert second_verify.json()["status"] == "tampered"


def test_verify_returns_requested_receipt_id_for_chain_break(client):
    first = client.post(
        "/ask",
        json={"prompt": "Original first prompt", "response": "Original first response"},
    )
    first_id = first.json()["receipt_id"]
    second = client.post(
        "/ask",
        json={"prompt": "Original second prompt", "response": "Original second response"},
    )
    second_id = second.json()["receipt_id"]

    db_path = Path(os.environ["RECEIPTS_DB_PATH"])
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE receipts SET response = ? WHERE receipt_id = ?",
            ("TAMPERED EARLIER RECORD", first_id),
        )
        conn.commit()

    response = client.post("/verify", json={"receipt_id": second_id})
    payload = response.json()

    assert payload["receipt_id"] == second_id
    assert payload["valid"] is False
    assert payload["status"] == "tampered"


def test_nonexistent_receipt_returns_404(client):
    response = client.post("/verify", json={"receipt_id": "missing-receipt"})
    assert response.status_code == 404
    payload = response.json()
    assert "detail" in payload
