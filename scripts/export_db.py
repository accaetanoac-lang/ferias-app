"""
Exporta todas as tabelas do SQLite para um único JSON (backup lógico completo).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database import DB_PATH, get_conn  # noqa: E402


def export_full_database(output_path: str | None = None) -> str:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]

        payload: dict = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "database_path": DB_PATH,
            "tables": {},
        }

        conn.row_factory = sqlite3.Row
        for name in tables:
            rows_cur = conn.execute(f'SELECT * FROM "{name}"')
            payload["tables"][name] = [dict(r) for r in rows_cur.fetchall()]
    finally:
        conn.close()

    if not output_path:
        backup_dir = os.path.join(ROOT, "backup")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(backup_dir, f"full_export_{ts}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path


def main() -> None:
    p = argparse.ArgumentParser(description="Exporta o banco ferias.db para JSON.")
    p.add_argument(
        "-o",
        "--output",
        help="Arquivo de saída (padrão: backup/full_export_YYYYMMDD_HHMM.json)",
    )
    args = p.parse_args()
    path = export_full_database(args.output)
    print(path)


if __name__ == "__main__":
    main()
