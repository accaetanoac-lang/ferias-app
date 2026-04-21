import hashlib
import json
import os

from database import get_conn


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

    conn = get_conn()
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
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        "INSERT INTO colaboradores (nome, funcao, dias_disponiveis) VALUES (?, ?, ?)",
        (nome.strip(), (funcao or "").strip(), int(dias)),
    )

    conn.commit()
    conn.close()


def listar_colaboradores():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id, nome, funcao, dias_disponiveis FROM colaboradores")
    data = c.fetchall()

    conn.close()
    return data


def buscar_colaborador(colaborador_id):
    conn = get_conn()
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
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, nome, funcao, dias_disponiveis FROM colaboradores WHERE nome = ?",
        (str(nome).strip(),),
    )
    row = c.fetchone()
    conn.close()
    return row


def salvar_solicitacao(colaborador_id, tipo, periodos):
    conn = get_conn()
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
    conn = get_conn()
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
    conn = get_conn()
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
