"""Safety mechanisms: confirmation gate, mode guard, audit log."""

import json
import secrets
import time
from pathlib import Path
from typing import Any

# Confirmation tokens: token -> {action, params, created_at}
_pending_confirmations: dict[str, dict[str, Any]] = {}
TOKEN_EXPIRY_SEC = 120


def create_confirmation(action: str, params: dict[str, Any], summary: str) -> str:
    """Create a confirmation request. Returns formatted message string for user."""
    token = secrets.token_hex(8)
    _pending_confirmations[token] = {
        "action": action,
        "params": params,
        "summary": summary,
        "created_at": time.time(),
    }
    # Clean expired tokens
    now = time.time()
    expired = [k for k, v in _pending_confirmations.items() if now - v["created_at"] > TOKEN_EXPIRY_SEC]
    for k in expired:
        del _pending_confirmations[k]

    return (
        f"⚠️ 확인 필요: {summary}\n\n"
        f"이 작업을 실행하려면 confirm_token='{token}'을 포함하여 다시 호출하세요.\n"
        f"(토큰은 {TOKEN_EXPIRY_SEC}초 후 만료됩니다)"
    )


def verify_confirmation(token: str) -> dict[str, Any] | None:
    """Verify and consume a confirmation token. Returns action details or None."""
    if token not in _pending_confirmations:
        return None
    entry = _pending_confirmations.pop(token)
    if time.time() - entry["created_at"] > TOKEN_EXPIRY_SEC:
        return None
    return entry


def audit_log(tool_name: str, params: dict, mode: str, result_status: str, audit_dir: Path):
    """Append tool invocation to audit log."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_path = audit_dir / "audit.jsonl"
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": tool_name,
        "params": params,
        "mode": mode,
        "status": result_status,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
