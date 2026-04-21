"""
Backup local: cópia do SQLite + export JSON da tabela solicitacoes.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime

from database import DB_PATH, get_conn

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(ROOT, "backup")


def backup_database() -> tuple[str, str]:
    """
    Copia ferias.db e exporta solicitacoes para JSON com timestamp.
    Retorna (caminho_db_backup, caminho_json_solicitacoes).
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    dest_db = os.path.join(BACKUP_DIR, f"ferias_{ts}.db")
    if os.path.isfile(DB_PATH):
        shutil.copy2(DB_PATH, dest_db)
    else:
        dest_db = ""

    dest_json = os.path.join(BACKUP_DIR, f"solicitacoes_{ts}.json")
    conn = get_conn()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, colaborador_id, tipo, data_inicio_1, data_fim_1, "
            "data_inicio_2, data_fim_2, criado_em, status, aprovado_por, data_aprovacao "
            "FROM solicitacoes ORDER BY id"
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    return dest_db, dest_json


if __name__ == "__main__":
    db_path, json_path = backup_database()
    print("Backup concluído:")
    if db_path:
        print(f"  DB:  {db_path}")
    else:
        print("  DB:  (ferias.db não encontrado — apenas JSON de solicitacoes)")
    print(f"  JSON: {json_path}")
