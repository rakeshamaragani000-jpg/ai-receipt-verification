import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status

from ai_service import generate_ai_response
from database import ensure_database_and_table, get_connection
from hash_chain import build_record_hash_payload, compute_record_hash
from models import AskRequest, AskResponse, TamperResponse, VerifyRequest, VerifyResponse


def create_app() -> FastAPI:
    app = FastAPI(
        title="Prove What the AI Did",
        version="1.0.0",
        description=(
            "A small FastAPI project that records AI prompts/responses, stores a SHA-256 "
            "hash chain, and verifies whether records were tampered with."
        ),
    )

    ensure_database_and_table()

    @app.get("/health", summary="Health check", description="Returns basic service health.")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/ask",
        response_model=AskResponse,
        summary="Create a receipt for an AI request",
        description=(
            "Accepts a prompt and the exact response from the client, stores the record in SQLite, "
            "and adds a SHA-256 hash chain entry."
        ),
    )
    def ask(payload: AskRequest):
        prompt = payload.prompt.strip()
        response_text = payload.response.strip()

        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Prompt must not be empty.",
            )
        if not response_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Response must not be empty.",
            )

        timestamp = datetime.now(timezone.utc).isoformat()

        conn = get_connection()
        try:
            result = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) AS max_sequence FROM receipts"
            ).fetchone()
            sequence_no = int(result["max_sequence"]) + 1

            # previous_hash is the anchor for the chain: each record points to the hash of the
            # record that came before it, and the first record uses a fixed genesis value.
            previous_hash = "GENESIS" if sequence_no == 1 else conn.execute(
                "SELECT current_hash FROM receipts WHERE sequence_no = ?",
                (sequence_no - 1,),
            ).fetchone()["current_hash"]

            receipt_id = f"rcpt-{sequence_no}-{uuid.uuid4().hex[:8]}"
            payload_for_hash = build_record_hash_payload(
                receipt_id=receipt_id,
                sequence_no=sequence_no,
                prompt=prompt,
                response=response_text,
                timestamp=timestamp,
                previous_hash=previous_hash,
            )
            current_hash = compute_record_hash(payload_for_hash)

            conn.execute(
                """
                INSERT INTO receipts (
                    receipt_id, sequence_no, prompt, response, previous_hash, current_hash, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (receipt_id, sequence_no, prompt, response_text, previous_hash, current_hash, timestamp),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "receipt_id": receipt_id,
            "sequence_no": sequence_no,
            "prompt": prompt,
            "response": response_text,
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "timestamp": timestamp,
        }

    @app.post(
        "/verify",
        response_model=VerifyResponse,
        summary="Verify a stored receipt",
        description=(
            "Recomputes the SHA-256 hash from stored record fields and checks the chain relationship "
            "against the previous record and all linked history in the chain."
        ),
    )
    def verify(payload: VerifyRequest):
        requested_receipt_id = payload.receipt_id
        conn = get_connection()
        try:
            selected_row = conn.execute(
                "SELECT * FROM receipts WHERE receipt_id = ?",
                (requested_receipt_id,),
            ).fetchone()
            if selected_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Receipt '{requested_receipt_id}' was not found.",
                )

            chain_rows = []
            current_row = selected_row
            while current_row is not None:
                chain_rows.append(current_row)
                if current_row["sequence_no"] == 1:
                    break
                current_row = conn.execute(
                    "SELECT * FROM receipts WHERE sequence_no = ?",
                    (current_row["sequence_no"] - 1,),
                ).fetchone()

            chain_rows.sort(key=lambda row: row["sequence_no"])

            for row in chain_rows:
                # Verification recomputes the hash from the actual stored record data. If the
                # data changed after write-time but the stored hash was not updated, the
                # recalculated value no longer matches the signed record state.
                expected_hash = compute_record_hash(
                    build_record_hash_payload(
                        receipt_id=row["receipt_id"],
                        sequence_no=row["sequence_no"],
                        prompt=row["prompt"],
                        response=row["response"],
                        timestamp=row["timestamp"],
                        previous_hash=row["previous_hash"],
                    )
                )

                if expected_hash != row["current_hash"]:
                    return VerifyResponse(
                        receipt_id=requested_receipt_id,
                        valid=False,
                        status="tampered",
                        message="The stored record content does not match the original SHA-256 hash.",
                        stored_hash=row["current_hash"],
                        calculated_hash=expected_hash,
                        explanation=(
                            "This record was modified after being created without updating its stored hash, "
                            "so the recomputed hash no longer matches the stored value."
                        ),
                    )

                if row["sequence_no"] > 1:
                    previous_row = conn.execute(
                        "SELECT * FROM receipts WHERE sequence_no = ?",
                        (row["sequence_no"] - 1,),
                    ).fetchone()
                    if previous_row is None:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Previous record in the chain is missing.",
                        )
                    if previous_row["current_hash"] != row["previous_hash"]:
                        return VerifyResponse(
                            receipt_id=requested_receipt_id,
                            valid=False,
                            status="tampered",
                            message="Chain link mismatch: previous_hash does not match the previous record's stored hash.",
                            stored_hash=row["current_hash"],
                            calculated_hash=expected_hash,
                            explanation=(
                                f"Sequence {row['sequence_no']} points to previous_hash {row['previous_hash']}, "
                                f"but the previous record's stored hash is {previous_row['current_hash']}. "
                                "The chain relationship is broken."
                            ),
                        )

            return VerifyResponse(
                receipt_id=selected_row["receipt_id"],
                valid=True,
                status="valid",
                message="The record and its chain relationship match the stored receipt.",
                stored_hash=selected_row["current_hash"],
                calculated_hash=compute_record_hash(
                    build_record_hash_payload(
                        receipt_id=selected_row["receipt_id"],
                        sequence_no=selected_row["sequence_no"],
                        prompt=selected_row["prompt"],
                        response=selected_row["response"],
                        timestamp=selected_row["timestamp"],
                        previous_hash=selected_row["previous_hash"],
                    )
                ),
                explanation="The verifier recomputed the SHA-256 hash for each record in the linked chain and matched it to the stored hash and previous_hash values.",
            )
        finally:
            conn.close()

    @app.post(
        "/tamper/{receipt_id}",
        response_model=TamperResponse,
        summary="Development-only tamper demonstration",
        description=(
            "Intentionally changes a stored response without updating the hash. This endpoint "
            "exists only to demonstrate tamper detection in a development environment."
        ),
    )
    def tamper_receipt(receipt_id: str):
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Receipt '{receipt_id}' was not found.",
                )

            conn.execute(
                "UPDATE receipts SET response = ? WHERE receipt_id = ?",
                ("[TAMPERED FOR DEMONSTRATION] This response was changed after the receipt was written.", receipt_id),
            )
            conn.commit()
            return {
                "receipt_id": receipt_id,
                "status": "tampered",
                "message": "The record was intentionally modified without updating its hash to demonstrate verification failure.",
            }
        finally:
            conn.close()

    return app


app = create_app()
