"""
Cliente Supabase opcional.

Quando USE_SUPABASE=true e as variáveis SUPABASE_URL / SUPABASE_KEY estiverem
configuradas (via .env local ou st.secrets no Streamlit Cloud), as operações
são roteadas para o Supabase. Caso contrário, o módulo é importado normalmente
mas nenhuma função é chamada (o repository.py usa SQLite como fallback).
"""
import os

try:
    import streamlit as st
    _secrets = st.secrets
except Exception:
    _secrets = {}


def _get_url():
    url = os.getenv("SUPABASE_URL", "")
    if not url:
        try:
            url = _secrets.get("SUPABASE_URL", "")
        except Exception:
            pass
    return url


def _get_key():
    key = os.getenv("SUPABASE_KEY", "")
    if not key:
        try:
            key = _secrets.get("SUPABASE_KEY", "")
        except Exception:
            pass
    return key


def _client():
    try:
        from supabase import create_client
        return create_client(_get_url(), _get_key())
    except Exception:
        return None


def select(table: str, query: str = ""):
    """Retorna lista de dicts da tabela. query é um filtro opcional no formato '&col=eq.val'."""
    client = _client()
    if client is None:
        return []
    try:
        req = client.table(table).select("*")
        # aplica filtros simples no formato col=eq.valor
        if query:
            for part in query.lstrip("&").split("&"):
                if "=eq." in part:
                    col, val = part.split("=eq.", 1)
                    req = req.eq(col, val)
        resp = req.execute()
        return resp.data if resp.data else []
    except Exception:
        return []


def insert(table: str, data: dict):
    client = _client()
    if client is None:
        return None
    try:
        resp = client.table(table).insert(data).execute()
        return resp.data
    except Exception as e:
        return str(e)


def update(table: str, data: dict, query: str = ""):
    client = _client()
    if client is None:
        return None
    try:
        req = client.table(table).update(data)
        if query:
            for part in query.lstrip("&").split("&"):
                if "=eq." in part:
                    col, val = part.split("=eq.", 1)
                    req = req.eq(col, val)
        resp = req.execute()
        return resp.data
    except Exception:
        return None
