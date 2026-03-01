import os, json, hashlib
from flask import Flask, request, jsonify
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

app = Flask(__name__)

# ========== 配置 ==========
# 在環境變數中設置 SIGNER_PRIVATE_KEY=0x...
SIGNER_PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY")  # 必須以 0x 開頭

def require_private_key():
    if not SIGNER_PRIVATE_KEY:
        raise RuntimeError("SIGNER_PRIVATE_KEY 未設置。請在環境變數中添加。")

# ========== 工具函數 ==========
def canonical_json(obj):
    """確定性 JSON（排序 keys，無多餘空格）"""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def sha256_hex_of_bytes(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()

def sha256_hex_of_report(report_obj: dict) -> str:
    """計算 report 的 sha256，排除 integrity_proof 欄位（如果存在）"""
    r = dict(report_obj)
    if 'integrity_proof' in r:
        r.pop('integrity_proof')
    canonical = canonical_json(r).encode('utf-8')
    return sha256_hex_of_bytes(canonical)

def get_signer_address():
    """返回當前配置的簽名地址（Checksum）或 None"""
    if not SIGNER_PRIVATE_KEY:
        return None
    acct = Account.from_key(SIGNER_PRIVATE_KEY)
    return Web3.to_checksum_address(acct.address)

# ========== 簽名與驗證 ==========
def sign_report(report_obj: dict) -> dict:
    """
    返回帶 integrity_proof 的 signed_report（不修改原對象，返回新對象）
    integrity_proof: { sha256, signature, signer_address }
    簽名採用 personal_sign / EIP-191 風格（encode_defunct）
    """
    require_private_key()
    report_hash = sha256_hex_of_report(report_obj)
    message = encode_defunct(text=report_hash)
    signed = Account.sign_message(message, private_key=SIGNER_PRIVATE_KEY)
    signed_report = dict(report_obj)
    signed_report['integrity_proof'] = {
        "sha256": report_hash,
        "signature": signed.signature.hex(),
        "signer_address": Web3.to_checksum_address(Account.from_key(SIGNER_PRIVATE_KEY).address)
    }
    return signed_report

def verify_signed_report(signed_report_obj: dict) -> dict:
    """
    驗證帶簽名報告。返回:
      { valid: bool, reason: str, recovered_address: str|null, sha256: str|null }
    """
    if 'integrity_proof' not in signed_report_obj:
        return {"valid": False, "reason": "missing integrity_proof", "recovered_address": None, "sha256": None}
    proof = signed_report_obj['integrity_proof']
    sig = proof.get('signature')
    signed_addr = proof.get('signer_address')
    sha256_in_proof = proof.get('sha256')

    # 重新計算 sha256
    recomputed_sha = sha256_hex_of_report(signed_report_obj)
    if sha256_in_proof != recomputed_sha:
        return {"valid": False, "reason": "sha256 mismatch (content changed)", "recovered_address": None, "sha256": recomputed_sha}

    try:
        message = encode_defunct(text=recomputed_sha)
        recovered = Account.recover_message(message, signature=bytes.fromhex(sig.replace('0x', '')))
        recovered = Web3.to_checksum_address(recovered)
    except Exception as e:
        return {"valid": False, "reason": f"signature recover error: {str(e)}", "recovered_address": None, "sha256": recomputed_sha}

    if signed_addr:
        try:
            signed_addr = Web3.to_checksum_address(signed_addr)
            if signed_addr != recovered:
                return {"valid": False, "reason": "signature not matching declared signer_address", "recovered_address": recovered, "sha256": recomputed_sha}
        except Exception as e:
            return {"valid": False, "reason": f"invalid signer_address format: {e}", "recovered_address": recovered, "sha256": recomputed_sha}

    return {"valid": True, "reason": "ok", "recovered_address": recovered, "sha256": recomputed_sha}

# ========== HTTP API ==========
@app.get("/")
def home():
    addr = get_signer_address()
    return jsonify({
        "service": "Truth Anchor SDK Signer",
        "version": "v0.2",
        "signer_address": addr,
        "note": "請確保 SIGNER_PRIVATE_KEY 已在環境變數中配置（僅用於簽名，勿用於資金存儲）"
    })

@app.route("/sign-report", methods=["POST"])
def api_sign_report():
    try:
        report = request.get_json(force=True)
        if not isinstance(report, dict):
            return jsonify({"ok": False, "error": "report must be JSON object"}), 400
        signed = sign_report(report)
        return jsonify({"ok": True, "signed_report": signed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/verify-report", methods=["POST"])
def api_verify_report():
    try:
        signed_report = request.get_json(force=True)
        if not isinstance(signed_report, dict):
            return jsonify({"valid": False, "reason": "signed_report must be JSON object"}), 400
        res = verify_signed_report(signed_report)
        return jsonify(res)
    except Exception as e:
        return jsonify({"valid": False, "reason": str(e)}), 500

# ========== 運行 ==========
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
