import datetime
import hashlib
import json
import os

import database
import supabase_client

def _use_supabase() -> bool:
    val = os.getenv("USE_SUPABASE", "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    # Fallback: tenta ler dos secrets do Streamlit
    try:
        import streamlit as st
        v = str(st.secrets.get("USE_SUPABASE", "")).lower()
        if v in ("true", "1", "yes"):
            return True
        if v in ("false", "0", "no"):
            return False
    except Exception:
        pass
    # Padrão: usa Supabase sempre que o cliente conseguir conectar
    return supabase_client._client() is not None

USE_SUPABASE = _use_supabase()


def get_colaboradores():
    if USE_SUPABASE:
        return supabase_client.select("colaboradores")
    conn = database.get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM colaboradores")
    rows = cursor.fetchall()
    if not cursor.description:
        conn.close()
        return []
    columns = [d[0] for d in cursor.description]
    out = [dict(zip(columns, row)) for row in rows]
    conn.close()
    return out


def _path_colaboradores_json():
    return os.path.join(os.path.dirname(__file__), "data", "colaboradores.json")


def calcular_hash_arquivo(caminho):
    with open(caminho, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def seed_colaboradores_if_needed():
    path = _path_colaboradores_json()

    if not os.path.isfile(path):
        raise FileNotFoundError(
            "colaboradores.json não encontrado. Execute: python scripts/generate_colaboradores_json.py"
        )

    current_hash = calcular_hash_arquivo(path)

    conn = database.get_conn()
    c = conn.cursor()

    c.execute("SELECT value FROM metadata WHERE key = ?", ("colaboradores_hash",))
    row = c.fetchone()
    stored = row[0] if row else None

    if stored == current_hash:
        conn.close()
        return

    with open(path, encoding="utf-8") as f:
        items = json.load(f)

    if not isinstance(items, list):
        items = [items]

    c.execute("DELETE FROM colaboradores")

    for item in items:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("nome", "")).strip()
        if not nome or nome.lower() == "nan":
            continue
        funcao = str(item.get("funcao") or "").strip()
        dias = int(item.get("dias", 30))
        c.execute(
            "INSERT INTO colaboradores (nome, funcao, dias_disponiveis) VALUES (?, ?, ?)",
            (nome, funcao, dias),
        )

    c.execute("DELETE FROM metadata WHERE key = ?", ("colaboradores_hash",))
    c.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        ("colaboradores_hash", current_hash),
    )

    conn.commit()
    conn.close()


def criar_colaborador(nome, funcao, dias):
    conn = database.get_conn()
    c = conn.cursor()

    c.execute(
        "INSERT INTO colaboradores (nome, funcao, dias_disponiveis) VALUES (?, ?, ?)",
        (nome.strip(), (funcao or "").strip(), int(dias)),
    )

    conn.commit()
    conn.close()


def listar_colaboradores():
    conn = database.get_conn()
    c = conn.cursor()

    c.execute("SELECT id, nome, funcao, dias_disponiveis FROM colaboradores")
    data = c.fetchall()

    conn.close()
    return data


def buscar_colaborador(colaborador_id):
    conn = database.get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, nome, funcao, dias_disponiveis FROM colaboradores WHERE id = ?",
        (colaborador_id,),
    )
    row = c.fetchone()
    conn.close()
    return row


def colaborador_row_para_dict(row):
    if not row:
        return None

    return {
        "id": row[0],
        "nome": row[1],
        "funcao": row[2] or "",
        "dias_disponiveis": row[3] if len(row) > 3 else 30,
    }


def buscar_colaborador_por_nome(nome):
    if not nome:
        return None
    conn = database.get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, nome, funcao, dias_disponiveis FROM colaboradores WHERE nome = ?",
        (str(nome).strip(),),
    )
    row = c.fetchone()
    conn.close()
    return row


def salvar_solicitacao(colaborador_id, tipo, periodos):
    conn = database.get_conn()
    c = conn.cursor()

    p1 = periodos[0]
    p2 = periodos[1] if len(periodos) > 1 else None

    c.execute(
        """
        INSERT INTO solicitacoes (
            colaborador_id,
            tipo,
            data_inicio_1,
            data_fim_1,
            data_inicio_2,
            data_fim_2,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')
        """,
        (
            colaborador_id,
            tipo,
            p1["inicio"],
            p1["fim"],
            p2["inicio"] if p2 else None,
            p2["fim"] if p2 else None,
        ),
    )

    conn.commit()
    conn.close()


def atualizar_status_solicitacao(solicitacao_id, status, aprovado_por):
    conn = database.get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE solicitacoes
        SET status = ?, aprovado_por = ?, data_aprovacao = date('now')
        WHERE id = ?
        """,
        (status, aprovado_por, solicitacao_id),
    )
    conn.commit()
    conn.close()


def listar_solicitacoes_com_status():
    """Consulta direta ao SQLite (sem @st.cache_data); sempre dados atuais."""
    conn = database.get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT
            s.id,
            c.nome,
            c.funcao,
            s.tipo,
            s.data_inicio_1,
            s.data_fim_1,
            s.data_inicio_2,
            s.data_fim_2,
            s.status,
            s.aprovado_por,
            s.data_aprovacao,
            s.criado_em
        FROM solicitacoes s
        JOIN colaboradores c ON c.id = s.colaborador_id
        ORDER BY s.criado_em DESC
        """
    )

    colunas = [desc[0] for desc in c.description]
    dados = [dict(zip(colunas, row)) for row in c.fetchall()]

    conn.close()
    return dados


def listar_solicitacoes():
    return listar_solicitacoes_com_status()


def listar_colaboradores_sem_programacao():
    """LEFT JOIN sem cache; após INSERT em solicitacoes, o colaborador some da lista."""
    conn = database.get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT c.id, c.nome
        FROM colaboradores c
        LEFT JOIN solicitacoes s ON c.id = s.colaborador_id
        WHERE s.id IS NULL
        ORDER BY c.nome
        """
    )

    data = c.fetchall()
    conn.close()
    return data


def criar_solicitacao_ferias(colaborador_id, data_inicio, dias, tipo_divisao=None, observacao=None):
    if not colaborador_id:
        return {"erro": "colaborador_id é obrigatório"}

    if not data_inicio:
        return {"erro": "data_inicio é obrigatória"}

    if not dias or dias <= 0:
        return {"erro": "dias inválidos"}

    data = {
        "colaborador_id": colaborador_id,
        "data_inicio": data_inicio,
        "dias": dias,
        "status": "PENDENTE",
        "periodo": 1,
        "tipo_divisao": tipo_divisao,
        "observacao": observacao,
        "tem_conflito": 0
    }

    # =========================
    # VALIDAR SALDO
    # =========================
    if USE_SUPABASE:
        saldo_data = supabase_client.select(
            "controle_ferias",
            f"&colaborador_id=eq.{colaborador_id}"
        )
    else:
        conn = database.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT saldo_total, saldo_utilizado FROM controle_ferias WHERE colaborador_id = ?",
            (colaborador_id,),
        )
        row = cursor.fetchone()
        saldo_data = []
        if row:
            saldo_data.append({
                "saldo_total": row[0],
                "saldo_utilizado": row[1]
            })
        conn.close()

    if not isinstance(saldo_data, list):
        saldo_data = []

    if not saldo_data:
        saldo_total = 30
        saldo_utilizado = 0
    else:
        saldo_total = saldo_data[0].get("saldo_total", 30)
        saldo_utilizado = saldo_data[0].get("saldo_utilizado", 0)

    if saldo_total is None:
        saldo_total = 30
    if saldo_utilizado is None:
        saldo_utilizado = 0

    # =========================
    # SOMAR SOLICITAÇÕES PENDENTES
    # =========================
    if USE_SUPABASE:
        pendentes = supabase_client.select(
            "solicitacoes",
            f"&colaborador_id=eq.{colaborador_id}&status=eq.PENDENTE"
        )
    else:
        conn = database.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT dias FROM solicitacoes WHERE colaborador_id = ? AND status = 'PENDENTE'",
            (colaborador_id,),
        )
        rows = cursor.fetchall()
        pendentes = [{"dias": r[0]} for r in rows]
        conn.close()

    dias_pendentes = 0

    if isinstance(pendentes, list):
        for p in pendentes:
            try:
                dias_pendentes += int(p.get("dias", 0))
            except (TypeError, ValueError, AttributeError):
                continue

    dias_int = int(dias)
    saldo_disponivel = max(
        0,
        int(saldo_total) - (int(saldo_utilizado) + dias_pendentes)
    )

    if dias_int > saldo_disponivel:
        return {
            "erro": f"Saldo insuficiente considerando solicitações pendentes. Disponível: {saldo_disponivel} dias"
        }

    inicio = datetime.datetime.strptime(str(data_inicio)[:10], "%Y-%m-%d")
    fim = inicio + datetime.timedelta(days=dias_int)

    if USE_SUPABASE:
        existentes = supabase_client.select(
            "solicitacoes",
            f"&colaborador_id=eq.{colaborador_id}"
        )
    else:
        conn = database.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_inicio, dias FROM solicitacoes WHERE colaborador_id = ?",
            (colaborador_id,),
        )
        rows = cursor.fetchall()
        existentes = [
            {"data_inicio": r[0], "dias": r[1]} for r in rows
        ]
        conn.close()

    if isinstance(existentes, list):
        for s in existentes:
            s_inicio = datetime.datetime.strptime(str(s["data_inicio"])[:10], "%Y-%m-%d")
            s_fim = s_inicio + datetime.timedelta(days=int(s["dias"]))

            if (inicio <= s_fim) and (fim >= s_inicio):
                return {"erro": "Conflito de datas de férias"}

    if USE_SUPABASE:
        try:
            resp = supabase_client.insert("solicitacoes", data)

            if isinstance(resp, list):
                return {"sucesso": True, "data": resp}

            return {"erro": resp}

        except Exception as e:
            return {"erro": str(e)}

    # fallback SQLite
    try:
        conn = database.get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO solicitacoes (
                colaborador_id,
                data_inicio,
                dias,
                status,
                periodo,
                tipo_divisao,
                observacao,
                tem_conflito
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            colaborador_id,
            data_inicio,
            dias,
            "PENDENTE",
            1,
            tipo_divisao,
            observacao,
            0
        ))

        conn.commit()
        conn.close()

        return {"sucesso": True}

    except Exception as e:
        return {"erro": str(e)}


def aprovar_solicitacao(solicitacao_id):
    if not solicitacao_id:
        return {"erro": "solicitacao_id é obrigatório"}

    # =========================
    # BUSCAR SOLICITAÇÃO
    # =========================
    if USE_SUPABASE:
        resp = supabase_client.select(
            "solicitacoes",
            f"&id=eq.{solicitacao_id}"
        )

        if not isinstance(resp, list) or not resp:
            return {"erro": "Solicitação não encontrada"}

        solicitacao = resp[0]

    else:
        conn = database.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT colaborador_id, dias, status FROM solicitacoes WHERE id = ?",
            (solicitacao_id,),
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"erro": "Solicitação não encontrada"}

        solicitacao = {
            "colaborador_id": row[0],
            "dias": row[1],
            "status": row[2]
        }

    # =========================
    # VALIDAR STATUS
    # =========================
    if solicitacao["status"] != "PENDENTE":
        if not USE_SUPABASE:
            conn.close()
        return {"erro": "Solicitação já processada"}

    colaborador_id = solicitacao["colaborador_id"]
    dias = int(solicitacao["dias"])

    # =========================
    # ATUALIZAR SOLICITAÇÃO
    # =========================
    if USE_SUPABASE:
        # atualizar status
        resp_update = supabase_client.update(
            "solicitacoes",
            {"status": "APROVADO"},
            f"id=eq.{solicitacao_id}&status=eq.PENDENTE"
        )

        if not resp_update:
            return {"erro": "Solicitação já processada ou não encontrada"}

        # buscar controle atual
        controle = supabase_client.select(
            "controle_ferias",
            f"&colaborador_id=eq.{colaborador_id}"
        )

        if controle and isinstance(controle, list):
            su = controle[0].get("saldo_utilizado", 0)
            saldo_utilizado = int(su) if su is not None else 0

            supabase_client.update(
                "controle_ferias",
                {"saldo_utilizado": saldo_utilizado + dias},
                f"colaborador_id=eq.{colaborador_id}"
            )
        else:
            # cria controle se não existir
            supabase_client.insert("controle_ferias", {
                "colaborador_id": colaborador_id,
                "saldo_total": 30,
                "saldo_utilizado": dias
            })

        return {"sucesso": True}

    # =========================
    # SQLITE FALLBACK
    # =========================
    try:
        # atualizar status
        cursor.execute(
            "UPDATE solicitacoes SET status = 'APROVADO' WHERE id = ? AND status = 'PENDENTE'",
            (solicitacao_id,),
        )

        if cursor.rowcount == 0:
            conn.close()
            return {"erro": "Solicitação já processada"}

        # buscar controle
        cursor.execute(
            "SELECT saldo_total, saldo_utilizado FROM controle_ferias WHERE colaborador_id = ?",
            (colaborador_id,),
        )
        row = cursor.fetchone()

        if row:
            su = row[1]
            saldo_utilizado = int(su) if su is not None else 0

            cursor.execute(
                "UPDATE controle_ferias SET saldo_utilizado = ? WHERE colaborador_id = ?",
                (saldo_utilizado + dias, colaborador_id)
            )
        else:
            cursor.execute(
                "INSERT INTO controle_ferias (colaborador_id, saldo_total, saldo_utilizado) VALUES (?, ?, ?)",
                (colaborador_id, 30, dias)
            )

        conn.commit()
        conn.close()

        return {"sucesso": True}

    except Exception as e:
        conn.close()
        return {"erro": str(e)}


def buscar_token(token):
    if not token:
        return None

    if USE_SUPABASE:
        resp = supabase_client.select(
            "tokens",
            f"&token=eq.{token}&revogado=eq.0"
        )

        if isinstance(resp, list) and resp:
            return resp[0]

        return None

    conn = database.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT colaborador_id, token, expiracao, usos, revogado FROM tokens WHERE token = ? AND revogado = 0",
        (token,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "colaborador_id": row[0],
        "token": row[1],
        "expiracao": row[2],
        "usos": row[3],
        "revogado": row[4],
    }


def buscar_colaborador_por_id(colaborador_id):
    if USE_SUPABASE:
        resp = supabase_client.select(
            "colaboradores",
            f"&id=eq.{colaborador_id}"
        )
        if isinstance(resp, list) and resp:
            return resp[0]
        return None

    conn = database.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT nome FROM colaboradores WHERE id = ?",
        (colaborador_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return {"nome": row[0]} if row else None
