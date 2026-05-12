# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Truth Anchor SDK is a single-file Flask service (`main.py`) that signs and verifies JSON "reports" using Ethereum-style EIP-191 `personal_sign`. It produces a Proof of Equity (PoE) by attaching an `integrity_proof` block to a report; the proof contains the canonical-JSON SHA-256, an EIP-191 signature, and the signer's checksum address.

## Commands

There is no `requirements.txt`, `Makefile`, or test suite. The full developer loop:

```bash
pip install flask web3 eth-account
cp .env.example .env          # then edit SIGNER_PRIVATE_KEY (must start with 0x)
export $(grep -v '^#' .env | xargs)   # main.py reads env vars directly; it does not call load_dotenv
python main.py                # serves on 0.0.0.0:$PORT (default 8080)
```

Manual smoke test against the running service:

```bash
curl -s localhost:8080/                                                    # health, returns signer_address
curl -s -X POST localhost:8080/sign-report   -H 'content-type: application/json' -d '{"finding":"x"}'
curl -s -X POST localhost:8080/verify-report -H 'content-type: application/json' -d '<paste signed_report>'
```

## Architecture & critical invariants

The signing/verification round-trip only works if every step preserves byte-for-byte equivalence. When editing `main.py`, do not break these:

- **Canonical JSON is load-bearing.** `canonical_json` uses `sort_keys=True`, `separators=(',', ':')`, and `ensure_ascii=False`. Any change to these args (or introducing a different serializer) silently invalidates every previously-signed report.
- **Hash excludes `integrity_proof`.** `sha256_hex_of_report` pops `integrity_proof` before hashing so the same function is used for both signing and verification. Do not hash the signed object directly.
- **Signature scheme is EIP-191 over the hex string.** `encode_defunct(text=report_hash)` signs the ASCII hex digest (not the raw 32 bytes). Verification must mirror this exactly.
- **Address comparison is checksum-normalized.** Both the declared `signer_address` and the recovered address are passed through `Web3.to_checksum_address` before comparison; preserve this when adding new code paths.
- **`integrity_proof` shape is the public contract:** `{ sha256, signature, signer_address }`. Downstream consumers (PDF reports, on-chain verifiers per the README's architecture diagram) depend on these exact field names.

`sign_report` returns a new dict (shallow copy via `dict(report_obj)`), so the caller's input is not mutated — keep this behavior.

## Configuration

- `SIGNER_PRIVATE_KEY` (required for `/sign-report` and the `signer_address` field on `/`) — hex string starting with `0x`. `require_private_key()` raises at sign time if missing; the service still starts and `/verify-report` still works without it.
- `PORT` (optional, default `8080`).

## Repo conventions

- README and inline comments are bilingual (English headings, Traditional Chinese prose). Match this style when editing user-facing docs.
- Develop on the branch specified by the task harness (currently `claude/add-claude-documentation-abY7L`); do not push to `main`.
