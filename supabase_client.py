"""
Cliente Supabase com mapeamento correto de colunas.

Schema real das tabelas no Supabase:
  colaboradores : id, nome, cargo, funcao, email, telefone, dias_disponiveis, data_admissao
  admin_senha   : id, hash, senha_hash
  tokens        : id, colaborador_id, token, expiracao, usos, revogado
  solicitacoes  : id, colaborador_id, tipo, data_inicio_1, data_fim_1,
                  data_inicio_2, data_fim_2, status, dias, criado_em,
                  aprovado_por, data_aprovacao
  controle_ferias: id, colaborador_id, saldo_total, saldo_utilizado
"""
import os

try:
    import streamlit as st
    _secrets = st.secrets
except Exception:
    _secrets = {}


def _get(key: str, default: str = "") -> str:
    val = os.getenv(key, "")
    if val:
        return val
    try:
        return _secrets.get(key, default)
    except Exception:
        return default


def _client():
    url = _get("SUPABASE_URL")
    key = _get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _apply_filters(req, query: str):
    """Aplica filtros no formato '&col=eq.val' a uma query do supabase-py."""
    if not query:
        return req
    for part in query.lstrip("&").split("&"):
        if "=eq." in part:
            col, val = part.split("=eq.", 1)
            req = req.eq(col, val)
        elif "=neq." in part:
            col, val = part.split("=neq.", 1)
            req = req.neq(col, val)
        elif "=is." in part:
            col, val = part.split("=is.", 1)
            req = req.is_(col, val)
    return req


def select(table: str, query: str = ""):
    c = _client()
    if c is None:
        return []
    try:
        req = _apply_filters(c.table(table).select("*"), query)
        resp = req.execute()
        rows = resp.data or []
        return [_normalize_row(table, r) for r in rows]
    except Exception:
        return []


def insert(table: str, data: dict):
    c = _client()
    if c is None:
        return None
    try:
        mapped = _map_row(table, data)
        resp = c.table(table).insert(mapped).execute()
        return resp.data
    except Exception as e:
        return str(e)


def update(table: str, data: dict, query: str = ""):
    c = _client()
    if c is None:
        return None
    try:
        mapped = _map_row(table, data)
        req = _apply_filters(c.table(table).update(mapped), query)
        resp = req.execute()
        return resp.data
    except Exception:
        return None


def delete(table: str, query: str = ""):
    c = _client()
    if c is None:
        return None
    try:
        req = _apply_filters(c.table(table).delete(), query)
        resp = req.execute()
        return resp.data
    except Exception:
        return None


# ─────────────────────────────────────────────
# Mapeamento de colunas: SQLite → Supabase
# ─────────────────────────────────────────────

def _map_row(table: str, data: dict) -> dict:
    """Converte nomes de colunas do SQLite para o schema do Supabase."""
    if table == "admin_senha":
        out = {}
        for k, v in data.items():
            if k == "senha_hash":
                out["hash"] = v
                out["senha_hash"] = v
            else:
                out[k] = v
        return out
    if table == "colaboradores":
        out = {}
        for k, v in data.items():
            if k == "funcao":
                out["funcao"] = v
                out["cargo"] = v
            else:
                out[k] = v
        return out
    return data


def _normalize_row(table: str, row: dict) -> dict:
    """Normaliza colunas do Supabase para o formato esperado pelo código."""
    if table == "admin_senha":
        if "senha_hash" not in row and "hash" in row:
            row = dict(row, senha_hash=row["hash"])
        return row
    if table == "colaboradores":
        row = dict(row)
        if not row.get("funcao"):
            row["funcao"] = row.get("cargo", "")
        if "dias_disponiveis" not in row:
            row["dias_disponiveis"] = 30
        return row
    if table == "tokens":
        row = dict(row)
        if "revogado" not in row:
            row["revogado"] = 0
        if "usos" not in row:
            row["usos"] = 0
        return row
    return row
