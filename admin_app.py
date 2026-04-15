import streamlit as st
import sqlite3
import uuid
import pandas as pd
import urllib.parse

from ferias import EQUIPE

st.set_page_config(page_title="Gestão de Férias", layout="wide")

# ------------------------
# BANCO
# ------------------------

def get_conn():
    return sqlite3.connect("ferias.db", check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS colaboradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER,
        token TEXT,
        usado INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER,
        data_inicio TEXT,
        dias INTEGER,
        status TEXT
    )
    """)

    conn.commit()
    conn.close()

# ------------------------
# IMPORTAÇÃO AUTOMÁTICA (EQUIPE FIXA)
# ------------------------

def importar_equipe():
    conn = get_conn()
    c = conn.cursor()

    # SEMPRE limpa e recria (sincronização total)
    c.execute("DELETE FROM colaboradores")

    for nome in EQUIPE.keys():
        c.execute(
            "INSERT INTO colaboradores (nome) VALUES (?)",
            (nome,)
        )

    conn.commit()
    conn.close()

# ------------------------
# INIT
# ------------------------

init_db()
importar_equipe()

# ------------------------
# TOKEN
# ------------------------

def gerar_token(colaborador_id):
    token = str(uuid.uuid4())
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        "INSERT INTO tokens (colaborador_id, token) VALUES (?, ?)",
        (colaborador_id, token)
    )

    conn.commit()
    conn.close()

    return token

def validar_token(token):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        "SELECT colaborador_id, usado FROM tokens WHERE token = ?",
        (token,)
    )
    result = c.fetchone()

    conn.close()

    if result and result[1] == 0:
        return result[0]
    return None

# ------------------------
# BASE URL
# ------------------------

BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")

# ------------------------
# PARAMETROS
# ------------------------

params = st.query_params
token = params.get("token")

# ------------------------
# FUNCIONÁRIO
# ------------------------

if token:
    colaborador_id = validar_token(token)

    if colaborador_id:
        st.title("Solicitação de Férias")

        data_inicio = st.date_input("Data início")
        dias = st.number_input("Dias", min_value=1)

        if st.button("Enviar"):
            conn = get_conn()
            c = conn.cursor()

            c.execute("""
                INSERT INTO solicitacoes (colaborador_id, data_inicio, dias, status)
                VALUES (?, ?, ?, 'PENDENTE')
            """, (colaborador_id, str(data_inicio), dias))

            c.execute(
                "UPDATE tokens SET usado = 1 WHERE token = ?",
                (token,)
            )

            conn.commit()
            conn.close()

            st.success("Enviado com sucesso!")

    else:
        st.error("Link inválido ou já usado")

# ------------------------
# ADMIN
# ------------------------

else:
    st.title("Painel Administrativo")

    tab1, tab2, tab3 = st.tabs([
        "Colaboradores",
        "Gerar Links",
        "Solicitações"
    ])

    # ------------------------
    # COLABORADORES
    # ------------------------
    with tab1:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        conn.close()

        st.dataframe(df, use_container_width=True)

    # ------------------------
    # GERAR LINKS
    # ------------------------
    with tab2:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        conn.close()

        if df.empty:
            st.warning("Nenhum colaborador encontrado")
        else:
            nome = st.selectbox("Colaborador", df["nome"])

            colaborador_id = df[df["nome"] == nome]["id"].values[0]

            if st.button("Gerar Link"):
                token = gerar_token(colaborador_id)

                link = f"{BASE_URL}?token={token}"

                mensagem = f"Olá {nome}, favor preencher suas férias: {link}"
                mensagem_encoded = urllib.parse.quote(mensagem)

                wa_link = f"https://wa.me/?text={mensagem_encoded}"

                st.success("Link gerado")
                st.code(link)
                st.link_button("Enviar WhatsApp", wa_link)

    # ------------------------
    # SOLICITAÇÕES
    # ------------------------
    with tab3:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM solicitacoes", conn)
        conn.close()

        st.dataframe(df, use_container_width=True)