# -*- coding: utf-8 -*-
"""Export ChatGPT access tokens from turb.sqlite3 for a GPT Image account pool."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "turb.sqlite3"


def _load_payload(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _registration_password(payload: dict) -> str:
    extra = payload.get("extra_json")
    if isinstance(extra, str) and extra.strip():
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    if isinstance(extra, dict):
        value = str(extra.get("registration_password") or "").strip()
        if value:
            return value
    return str(payload.get("registration_password") or "").strip()


def _truthy(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ok"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None


def iter_accounts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, email, status, archived, created_at, updated_at, payload "
        "FROM accounts ORDER BY id"
    ).fetchall()
    out = []
    for row in rows:
        payload = _load_payload(row["payload"])
        email = str(row["email"] or payload.get("email") or "").strip()
        token = str(payload.get("access_token") or "").strip()
        out.append({
            "id": int(row["id"]),
            "email": email,
            "archived": int(row["archived"] or 0),
            "status": str(row["status"] or payload.get("status") or "").strip(),
            "access_token": token,
            "registration_password": _registration_password(payload),
            "plan_type": str(
                payload.get("current_plan_type")
                or payload.get("plan_type")
                or ""
            ).strip(),
            "plus_trial_eligible": _truthy(payload.get("plus_trial_eligible")),
            "live_check_ok": _truthy(payload.get("live_check_ok")),
            "live_check_status": str(payload.get("live_check_status") or "").strip(),
            "expires_at": str(payload.get("expires_at") or payload.get("expires") or "").strip(),
            "proxy_used": str(payload.get("proxy_used") or "").strip(),
            "email_source": str(payload.get("email_source") or "").strip(),
            "created_at": str(row["created_at"] or payload.get("created_at") or "").strip(),
            "updated_at": str(row["updated_at"] or payload.get("updated_at") or "").strip(),
        })
    return out


def filter_accounts(items: list[dict], *, live_only: bool, with_token: bool) -> list[dict]:
    selected = []
    for item in items:
        if item["archived"]:
            continue
        if with_token and not item["access_token"]:
            continue
        if live_only and item["live_check_ok"] is False:
            continue
        if live_only and str(item["live_check_status"]).lower() in {"deactivated", "dead", "banned"}:
            continue
        selected.append(item)
    return selected


def write_outputs(items: list[dict], dest: Path) -> tuple[Path, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    jsonl_path = dest / f"image-pool-{stamp}.jsonl"
    txt_path = dest / f"image-pool-{stamp}.txt"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as jsonl_file:
        for item in items:
            jsonl_file.write(json.dumps(item, ensure_ascii=False) + "\n")
    with txt_path.open("w", encoding="utf-8", newline="\n") as txt_file:
        for item in items:
            txt_file.write(f"{item['email']}----{item['access_token']}\n")
    return jsonl_path, txt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export GPT Image account pool from turb.sqlite3")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to turb.sqlite3")
    parser.add_argument("--out", default=str(ROOT / "image_pool"), help="Output directory")
    parser.add_argument("--live-only", action="store_true", help="Skip accounts marked dead by live check")
    parser.add_argument("--include-empty-token", action="store_true", help="Keep rows without access_token")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        items = filter_accounts(
            iter_accounts(conn),
            live_only=args.live_only,
            with_token=not args.include_empty_token,
        )
    finally:
        conn.close()

    jsonl_path, txt_path = write_outputs(items, Path(args.out))
    print(f"exported {len(items)} accounts")
    print(jsonl_path)
    print(txt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
