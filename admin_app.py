import streamlit as st
import sqlite3
import uuid
import pandas as pd
import urllib.parse
from datetime import datetime

# ------------------------
# CONFIGURAÇÃO DA PÁGINA
# ------------------------

st.set_page_config(page_title="Gestão de Férias - Green Máquinas", layout="wide")

# ------------------------
# BANCO DE DADOS
# ------------------------

def get_conn():
    return sqlite3.connect("ferias.db", check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS colaboradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        cargo TEXT
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

init_db()

# ------------------------
# FUNÇÕES AUXILIARES
# ------------------------

def importar_excel():
    try:
        df = pd.read_excel("férias-fy26.xlsx")
        conn = get_conn()
        c = conn.cursor()

        # Limpar tabela
        c.execute("DELETE FROM colaboradores")

        # Inserir dados
        for _, row in df.iterrows():
            c.execute("INSERT INTO colaboradores (nome, cargo) VALUES (?, ?)", (row['Nome'], row['Cargo']))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erro ao importar: {e}")
        return False

def gerar_token(colaborador_id):
    token = str(uuid.uuid4())
    conn = get_conn()
    c = conn.cursor()

    c.execute("INSERT INTO tokens (colaborador_id, token) VALUES (?, ?)", (colaborador_id, token))

    conn.commit()
    conn.close()

    return token

def validar_token(token):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT colaborador_id, usado FROM tokens WHERE token = ?", (token,))
    result = c.fetchone()

    conn.close()

    if result and result[1] == 0:
        return result[0]
    return None

def salvar_solicitacao(colaborador_id, data_inicio, dias):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        INSERT INTO solicitacoes (colaborador_id, data_inicio, dias, status)
        VALUES (?, ?, ?, 'PENDENTE')
    """, (colaborador_id, str(data_inicio), dias))

    conn.commit()
    conn.close()

def marcar_token_usado(token):
    conn = get_conn()
    c = conn.cursor()

    c.execute("UPDATE tokens SET usado = 1 WHERE token = ?", (token,))

    conn.commit()
    conn.close()

# ------------------------
# PARÂMETROS DA URL
# ------------------------

params = st.query_params
token = params.get("token")

# ------------------------
# FLUXO FUNCIONÁRIO (VIA TOKEN)
# ------------------------

if token:
    colaborador_id = validar_token(token)

    if colaborador_id:
        st.title("Solicitação de Férias")

        data_inicio = st.date_input("Data de início")
        dias = st.number_input("Quantidade de dias", min_value=1)

        if st.button("Enviar"):
            salvar_solicitacao(colaborador_id, data_inicio, dias)
            marcar_token_usado(token)
            st.success("Solicitação enviada com sucesso!")
    else:
        st.error("Link inválido ou já utilizado.")

# ------------------------
# PAINEL ADMINISTRATIVO
# ------------------------

else:
    st.title("Painel Administrativo - Gestão de Férias")

    tab1, tab2, tab3 = st.tabs(["Colaboradores", "Gerar Links", "Solicitações"])

    # -------------------------
    # ABA COLABORADORES
    # -------------------------
    with tab1:
        st.subheader("Gerenciar Colaboradores")

        if st.button("Importar do Excel (férias-fy26.xlsx)"):
            if importar_excel():
                st.success("Colaboradores importados com sucesso!")

        conn = get_conn()
        df_colab = pd.read_sql("SELECT * FROM colaboradores", conn)
        st.dataframe(df_colab)

    # -------------------------
    # ABA GERAR LINKS
    # -------------------------
    with tab2:
        st.subheader("Gerar Link para Colaborador")

        conn = get_conn()
        df_colab = pd.read_sql("SELECT * FROM colaboradores", conn)

        st.dataframe(df_colab)

        colaborador_id = st.number_input("ID do colaborador", step=1)

        if st.button("Gerar Link"):
            token = gerar_token(colaborador_id)
            link = f"http://localhost:8501/?token={token}"

            st.success("Link gerado!")
            st.code(link)

            # Buscar nome do colaborador
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT nome FROM colaboradores WHERE id = ?", (colaborador_id,))
            nome = c.fetchone()[0]
            conn.close()

            mensagem = f"Olá {nome}, favor preencher suas férias: {link}"
            whatsapp_link = f"https://wa.me/?text={urllib.parse.quote(mensagem)}"

            st.markdown(f"[Enviar via WhatsApp]({whatsapp_link})", unsafe_allow_html=True)

    # -------------------------
    # ABA SOLICITAÇÕES
    # -------------------------
    with tab3:
        st.subheader("Solicitações Recebidas")

        conn = get_conn()
        df_solic = pd.read_sql("SELECT * FROM solicitacoes", conn)
        st.dataframe(df_solic)

            c.execute("""
                INSERT INTO solicitacoes (colaborador_id, data_inicio, dias, status)
                VALUES (?, ?, ?, 'PENDENTE')
            """, (colaborador_id, str(data_inicio), dias))

            c.execute("UPDATE tokens SET usado = 1 WHERE token = ?", (token,))

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

    tab1, tab2, tab3 = st.tabs(["Colaboradores", "Gerar Links", "Solicitações"])

    # COLABORADORES
    with tab1:
        nome = st.text_input("Nome")

        if st.button("Salvar"):
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO colaboradores (nome) VALUES (?)", (nome,))
            conn.commit()
            conn.close()
            st.success("Salvo!")

        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        st.dataframe(df)

    # GERAR LINKS
    with tab2:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        st.dataframe(df)

        colaborador_id = st.number_input("ID", step=1)

        if st.button("Gerar Link"):
            token = gerar_token(colaborador_id)

            link = f"http://localhost:8501/?token={token}"

            mensagem = f"Olá, favor preencher suas férias: {link}"
            mensagem_encoded = urllib.parse.quote(mensagem)

            wa_link = f"https://wa.me/?text={mensagem_encoded}"

            st.success("Link gerado")
            st.code(link)
            st.link_button("Enviar WhatsApp", wa_link)

    # SOLICITAÇÕES
    with tab3:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM solicitacoes", conn)
        st.dataframe(df)