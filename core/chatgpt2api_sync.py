# -*- coding: utf-8 -*-
"""把 turb 注册成功的网页 AT 同步到 chatgpt2api 号池。"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def rewrite_loopback_proxy(proxy: str, replacement_host: str = "host.docker.internal") -> str:
    text = str(proxy or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    host = str(parsed.hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        return text
    port = parsed.port
    netloc = replacement_host if port is None else f"{replacement_host}:{port}"
    if parsed.username:
        user = parsed.username
        if parsed.password:
            user = f"{user}:{parsed.password}"
        netloc = f"{user}@{netloc}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _resolve_proxy(proxy_used: str | None) -> str:
    from config import chatgpt2api as cfg

    override = str(getattr(cfg, "CHATGPT2API_ACCOUNT_PROXY", "") or "").strip()
    if override:
        return override
    proxy = str(proxy_used or "").strip()
    if bool(getattr(cfg, "CHATGPT2API_REWRITE_LOOPBACK_PROXY", True)):
        return rewrite_loopback_proxy(proxy)
    return proxy


def push_account_to_chatgpt2api(
    *,
    email: str,
    access_token: str,
    proxy_used: str | None = None,
    account_id: int | None = None,
    password: str | None = None,
    refresh_token: str | None = None,
    totp_secret: str | None = None,
) -> dict[str, Any]:
    from config import chatgpt2api as cfg

    if not bool(getattr(cfg, "CHATGPT2API_AUTO_EXPORT", False)):
        return {"skipped": True, "reason": "disabled"}

    api_base = str(getattr(cfg, "CHATGPT2API_API_BASE", "") or "").strip().rstrip("/")
    auth_key = str(getattr(cfg, "CHATGPT2API_AUTH_KEY", "") or "").strip()
    token = str(access_token or "").strip()
    if not api_base:
        return {"skipped": True, "reason": "missing_api_base"}
    if not token:
        return {"skipped": True, "reason": "missing_access_token"}

    timeout = int(getattr(cfg, "CHATGPT2API_API_TIMEOUT", 180) or 180)
    source_type = str(getattr(cfg, "CHATGPT2API_SOURCE_TYPE", "web") or "web").strip() or "web"
    acc_entry: dict[str, Any] = {
        "email": str(email or "").strip(),
        "access_token": token,
        "source_type": source_type,
        "proxy": _resolve_proxy(proxy_used),
    }
    if password and str(password).strip():
        acc_entry["password"] = str(password).strip()
    if refresh_token and str(refresh_token).strip():
        acc_entry["refresh_token"] = str(refresh_token).strip()
    if totp_secret and str(totp_secret).strip():
        acc_entry["totp_secret"] = str(totp_secret).strip()

    payload = {
        "accounts": [acc_entry]
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"

    req = Request(
        f"{api_base}/api/accounts",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = int(getattr(resp, "status", 200) or 200)
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body}
            result = {
                "ok": 200 <= status < 300,
                "status": status,
                "added": parsed.get("added") if isinstance(parsed, dict) else None,
                "skipped": parsed.get("skipped") if isinstance(parsed, dict) else None,
                "refreshed": parsed.get("refreshed") if isinstance(parsed, dict) else None,
                "errors": (parsed.get("errors") if isinstance(parsed, dict) else None) or [],
                "body": parsed,
            }
            logger.info(
                "[chatgpt2api] 同步完成 id=%s email=%s status=%s added=%s skipped=%s refreshed=%s",
                account_id,
                email,
                status,
                result.get("added"),
                result.get("skipped"),
                result.get("refreshed"),
            )
            if result["errors"]:
                logger.warning("[chatgpt2api] 同步返回错误: %s", result["errors"][:3])
            return result
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        logger.warning(
            "[chatgpt2api] 同步失败 HTTP %s id=%s email=%s body=%s",
            exc.code,
            account_id,
            email,
            body[:300],
        )
        return {"ok": False, "status": exc.code, "error": body[:500]}
    except URLError as exc:
        logger.warning(
            "[chatgpt2api] 同步失败连接错误 id=%s email=%s: %s",
            account_id,
            email,
            exc.reason,
        )
        return {"ok": False, "error": str(exc.reason)}
    except Exception as exc:
        logger.warning(
            "[chatgpt2api] 同步异常 id=%s email=%s: %s: %s",
            account_id,
            email,
            type(exc).__name__,
            str(exc)[:180],
        )
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def maybe_push_registered_account(
    *,
    email: str,
    access_token: str,
    proxy_used: str | None = None,
    account_id: int | None = None,
    password: str | None = None,
    refresh_token: str | None = None,
    totp_secret: str | None = None,
) -> dict[str, Any]:
    try:
        from config import chatgpt2api as cfg
    except Exception as exc:
        logger.warning("[chatgpt2api] 读取配置失败，跳过同步: %s", exc)
        return {"skipped": True, "reason": "config_error"}
    if not bool(getattr(cfg, "CHATGPT2API_AUTO_EXPORT", False)):
        logger.info("[chatgpt2api] 自动同步已关闭: id=%s email=%s", account_id, email)
        return {"skipped": True, "reason": "disabled"}
    return push_account_to_chatgpt2api(
        email=email,
        access_token=access_token,
        proxy_used=proxy_used,
        account_id=account_id,
        password=password,
        refresh_token=refresh_token,
        totp_secret=totp_secret,
    )


def push_bulk_accounts_to_chatgpt2api(
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """批量同步账号到 chatgpt2api。"""
    from config import chatgpt2api as cfg

    if not bool(getattr(cfg, "CHATGPT2API_AUTO_EXPORT", False)):
        return {"skipped": True, "reason": "disabled"}

    api_base = str(getattr(cfg, "CHATGPT2API_API_BASE", "") or "").strip().rstrip("/")
    auth_key = str(getattr(cfg, "CHATGPT2API_AUTH_KEY", "") or "").strip()
    if not api_base:
        return {"skipped": True, "reason": "missing_api_base"}
    if not accounts:
        return {"skipped": True, "reason": "empty_accounts"}

    timeout = int(getattr(cfg, "CHATGPT2API_API_TIMEOUT", 180) or 180)
    source_type_default = str(getattr(cfg, "CHATGPT2API_SOURCE_TYPE", "web") or "web").strip() or "web"

    formatted_accounts: list[dict[str, Any]] = []
    for item in accounts:
        token = str(item.get("access_token") or item.get("accessToken") or "").strip()
        if not token:
            continue
        entry: dict[str, Any] = {
            "email": str(item.get("email") or "").strip(),
            "access_token": token,
            "source_type": str(item.get("source_type") or source_type_default).strip(),
            "proxy": _resolve_proxy(item.get("proxy") or item.get("proxy_used")),
        }
        for key in ("password", "refresh_token", "totp_secret"):
            val = str(item.get(key) or "").strip()
            if val:
                entry[key] = val
        formatted_accounts.append(entry)

    if not formatted_accounts:
        return {"skipped": True, "reason": "no_valid_accounts"}

    payload = {"accounts": formatted_accounts}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"

    req = Request(
        f"{api_base}/api/accounts",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = int(getattr(resp, "status", 200) or 200)
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body}
            result = {
                "ok": 200 <= status < 300,
                "status": status,
                "added": parsed.get("added") if isinstance(parsed, dict) else None,
                "skipped": parsed.get("skipped") if isinstance(parsed, dict) else None,
                "refreshed": parsed.get("refreshed") if isinstance(parsed, dict) else None,
                "errors": (parsed.get("errors") if isinstance(parsed, dict) else None) or [],
                "body": parsed,
            }
            logger.info(
                "[chatgpt2api] 批量同步完成 total=%s status=%s added=%s skipped=%s refreshed=%s",
                len(formatted_accounts),
                status,
                result.get("added"),
                result.get("skipped"),
                result.get("refreshed"),
            )
            return result
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        logger.warning("[chatgpt2api] 批量同步失败 HTTP %s body=%s", exc.code, body[:300])
        return {"ok": False, "status": exc.code, "error": body[:500]}
    except URLError as exc:
        logger.warning("[chatgpt2api] 批量同步失败连接错误: %s", exc.reason)
        return {"ok": False, "error": str(exc.reason)}
    except Exception as exc:
        logger.warning("[chatgpt2api] 批量同步异常: %s: %s", type(exc).__name__, str(exc)[:180])
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def sync_db_accounts_to_chatgpt2api(
    account_ids: list[int] | None = None,
) -> dict[str, Any]:
    """从本地 SQLite 数据库读取账号并批量同步到 chatgpt2api。"""
    import sqlite3
    from pathlib import Path

    db_path = Path(__file__).resolve().parent.parent / "turb.sqlite3"
    if not db_path.exists():
        return {"skipped": True, "reason": "db_not_found"}

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    if account_ids:
        placeholders = ",".join("?" for _ in account_ids)
        cur.execute(f"SELECT id, email, payload FROM accounts WHERE id IN ({placeholders}) ORDER BY id ASC", account_ids)
    else:
        cur.execute("SELECT id, email, payload FROM accounts ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()

    items: list[dict[str, Any]] = []
    for aid, email, payload_raw in rows:
        data = json.loads(payload_raw) if payload_raw else {}
        token = str(data.get("access_token") or data.get("accessToken") or "").strip()
        if not token:
            continue
        extra_json = data.get("extra_json")
        extra = json.loads(extra_json) if isinstance(extra_json, str) else (extra_json or {})
        codex_data = extra.get("codex") if isinstance(extra.get("codex"), dict) else {}

        # 密码优先级：registration_password -> password
        password = str(
            extra.get("registration_password")
            or data.get("password")
            or ""
        ).strip()

        refresh_token = str(
            codex_data.get("refresh_token")
            or extra.get("refresh_token")
            or ""
        ).strip()

        totp_secret = str(data.get("totp_secret") or extra.get("totp_secret") or "").strip()
        proxy_used = str(data.get("proxy_used") or extra.get("proxy_used") or "").strip()

        items.append({
            "account_id": aid,
            "email": email,
            "access_token": token,
            "password": password,
            "refresh_token": refresh_token,
            "totp_secret": totp_secret,
            "proxy_used": proxy_used,
        })

    return push_bulk_accounts_to_chatgpt2api(items)
