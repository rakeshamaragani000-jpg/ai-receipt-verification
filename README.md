# Protofine Backend / ML Engineering Task

## 1. Problem

This project addresses a simple but important audit problem: after an AI interaction happens, we want a way to check whether the recorded request and response were changed later.

The goal is not to claim that an AI answer is correct or truthful. The goal is to make the interaction auditable after the fact by recording:

- what was asked
- what the AI returned
- when it happened
- a SHA-256 receipt for that record
- a hash chain linking the record to the one before it

If someone changes the stored data later without updating the hash, the verification step can detect the mismatch.

---

## 2. What I Built

I built a small FastAPI application that:

- accepts both a prompt and a response via `POST /ask`
- stores the exact prompt and exact response received from the client
- stores the record details and hash in SQLite
- creates a SHA-256 receipt for each record
- links each new record to the previous record through `previous_hash`
- verifies integrity through `POST /verify`
- includes a development-only tampering demo through `POST /tamper/{receipt_id}`

This keeps the system small, understandable, and aligned with the assignment.

---

## 3. Architecture

### Request flow

```text
Client
  |
  v
POST /ask
  |
  v
AI service
  |
  v
Record + canonical data
  |
  v
SHA-256 hash
  |
  v
SQLite
  |
  v
Receipt
```

### Verification flow

```text
POST /verify
  |
  v
Load stored record
  |
  v
Recalculate SHA-256
  |
  v
Compare stored hash
  |
  +---- match ----> VALID
  |
  +---- mismatch -> TAMPERED
```

The chain works like this:

- Record 1: `previous_hash = GENESIS`
- Record 2: `previous_hash = HASH1`
- Record 3: `previous_hash = HASH2`

This means later records depend on earlier records. If an earlier record is modified without updating its hash, the later chain link can also become invalid.

---

## 4. Project Structure

```text
backend/
├── .gitignore
├── README.md
├── requirements.txt
├── main.py
├── database.py
├── models.py
├── hash_chain.py
├── ai_service.py
├── data/
│   └── receipts.db
├── tests/
│   └── test_api.py
└── .venv/   (local only)
```

The SQLite database is created automatically when the app starts if it does not already exist.

---

## 5. Setup on Windows

Open PowerShell in VS Code.

```powershell
cd "C:\Users\jyoth\OneDrive\Desktop\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation because of execution policy, use this alternative:

```powershell
cd "C:\Users\jyoth\OneDrive\Desktop\backend"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If needed, Command Prompt also works:

```cmd
cd /d "C:\Users\jyoth\OneDrive\Desktop\backend"
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

---

## 6. Run the Application

From the project folder:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/docs
```

Swagger UI is available at `/docs` and the health endpoint is at `/health`.

---

## 7. API Endpoints

### GET /health

Purpose:
- quick server health check

Example response:

```json
{
  "status": "ok"
}
```

### POST /ask

Purpose:
- accept a prompt and the exact response from the client, then create a receipt record

Request example:

```json
{
  "prompt": "What is machine learning?",
  "response": "Machine learning is a method of learning patterns from data."
}
```

Important response fields:

- `receipt_id`
- `sequence_no`
- `prompt`
- `response`
- `previous_hash`
- `current_hash`
- `timestamp`

The first record uses `previous_hash = "GENESIS"`.

### POST /verify

Purpose:
- recompute and compare the record hash and chain integrity

Request example:

```json
{
  "receipt_id": "rcpt-1-abc12345"
}
```

Important response fields:

- `receipt_id`
- `valid`
- `status`
- `message`
- `stored_hash`
- `calculated_hash`
- `explanation`

### POST /tamper/{receipt_id}

Purpose:
- intentionally modify a stored response without updating its hash for demonstration only

This endpoint is development/demo only and is not meant for production use.

Example:

```http
POST /tamper/rcpt-1-abc12345
```

It changes the stored content so that the receipt can be verified as tampered.

---

## 8. Example Workflow

Request body:

```json
{
  "prompt": "What is machine learning?",
  "response": "Machine learning is a method of learning patterns from data."
}
```

Example response:

```json
{
  "receipt_id": "rcpt-1-abc12345",
  "sequence_no": 1,
  "prompt": "What is machine learning?",
  "response": "Machine learning is a method of learning patterns from data.",
  "previous_hash": "GENESIS",
  "current_hash": "8ff15d4c37b9d9d0d0d5b94db6a1b1a7d9b0c64f9f30e9d7cf391a9f99855ccf",
  "timestamp": "2026-09-19T10:49:00.000000+00:00"
}
```

Then:

```text
POST /verify
    |
    v
valid = true
    |
    v
POST /tamper/{receipt_id}
    |
    v
stored response modified without updating hash
    |
    v
POST /verify
    |
    v
valid = false
```

---

## 9. Tampering Demonstration

This is the most important proof of the assignment.

### Real test sequence

1. Start the server.
2. Create a record using `POST /ask`.
3. Copy the returned `receipt_id`.
4. Verify it with `POST /verify`.
5. Confirm that `valid` is `true`.
6. Call the development-only tamper endpoint for that receipt.
7. Do not update the original stored hash.
8. Call `POST /verify` again.
9. Confirm that `valid` becomes `false`.

Why it fails:

- the response field in the database was modified
- the stored `current_hash` was left unchanged
- the verifier recalculates the SHA-256 hash from the current stored content
- the newly calculated hash no longer matches the original stored hash
- the response shows the mismatch clearly

This is honest tamper evidence. The system is not claiming that hashing prevents tampering in all circumstances; it is showing that the system can detect a mismatch when the stored content changed after the receipt was created.

---

## 10. Hash Chain

Each record is hashed using canonical data:

- `receipt_id`
- `sequence_no`
- `prompt`
- `response`
- `timestamp`
- `previous_hash`

Example chain:

```text
Record 1:
previous_hash = GENESIS
current_hash = HASH1

Record 2:
previous_hash = HASH1
current_hash = HASH2

Record 3:
previous_hash = HASH2
current_hash = HASH3
```

This creates an auditable chain. If an earlier record is modified, that record's recomputed hash no longer matches the originally stored hash, and the later record's `previous_hash` can also become inconsistent with the previous record's actual hash.

---

## 11. What the Receipt Proves

The receipt provides evidence that the current stored content matches the content represented by the original stored hash.

In practical terms, it can detect when the stored data has changed without a matching hash update.

It does not prove that the AI answer was correct, truthful, safe, or high quality. It only shows that the stored record corresponds to a particular SHA-256 fingerprint at a point in time.

---

## 12. What the Receipt Does NOT Prove

The receipt does not prove:

- that the AI answer is correct
- that the AI answer is truthful
- that the model was unbiased
- that the AI response was safe
- who originally created the record unless authentication or signatures are added
- that the system is immutable in all circumstances
- that an attacker cannot rewrite both the stored content and the stored hash

It also does not replace proper audit infrastructure in a production system.

This honesty matters for the internship assignment and for technical maturity.

---

## 13. Testing

Run:

```powershell
python -m pytest -q
```

The test suite currently covers:

- record creation
- valid untouched record
- tampering detection
- invalid prompt
- missing receipt
- two-record hash chain
- earlier-record chain tampering

The current verified result is:

- 8 tests passed

---

## 14. Design Decisions

### FastAPI

FastAPI was selected because it is small, clear, and ideal for a beginner-friendly API with automatic validation and Swagger docs.

### SQLite

SQLite is used because it is local, file-based, easy to run in VS Code, and persistent across restarts without a database server.

### SHA-256

SHA-256 gives a deterministic fingerprint of the record content. Small changes produce a different hash.

### Canonical JSON serialization

We use a stable JSON format with sorted keys and compact separators. This avoids unstable Python dict ordering and ensures the same logical record hashes the same way every time.

### Hash chain

The `previous_hash` field creates a simple linked structure showing that each record depends on the one before it.

### Client-supplied response

The assignment requires the caller to provide both the prompt and the response in the request body. The API stores the exact values it receives and hashes them as part of the receipt. This keeps the project aligned with the requirement while still allowing a local deterministic fallback to remain in the codebase for convenience.

---

## 15. Limitations and Production Improvements

This is intentionally a small demo project, not a full enterprise audit system.

Possible future improvements include:

- append-only or immutable storage
- external trusted checkpoints
- digital signatures
- secure key management
- access control and audit logging
- backups and monitoring
- stronger production-grade integrity infrastructure

These are not implemented here because the assignment says not to over-build.

---

## 16. Internship Assignment Alignment

```text
[ x ] REST API
[ x ] AI request and response recorded
[ x ] Receipt generated
[ x ] Hash chain
[ x ] Verification endpoint
[ x ] Tampering demonstrated
[ x ] README
[ x ] Tests
[ x ] Honest limitations
```

---

## Final Notes

This project is designed to be easy to explain in a short interview:

> The application stores an AI prompt and response, creates a SHA-256 receipt, links each record to the prior one, and later verifies whether the stored content still matches the original hash. If someone changes the record without updating the hash, verification detects the mismatch.

That is the actual goal of the assignment: showing evidence that the stored data changed, not proving that the AI answer was correct.
