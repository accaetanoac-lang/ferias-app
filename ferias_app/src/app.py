import streamlit as st
st.write('🔥 APP NOVO RODANDO 🔥')
import streamlit as st
import uuid
import pandas as pd
from db import get_conn, init_db
from ferias import validar_regras

init_db()

st.set_page_config(page_title="Gestão de Férias", layout="wide")
st.write("VERSÃO NOVA - SISTEMA COM LINKS")

params = st.query_params
token = params.get("token")

# =========================
# FUNÇÕES
# =========================

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

    c.execute("SELECT colaborador_id, usado FROM tokens WHERE token = ?", (token,))
    result = c.fetchone()

    conn.close()

    if result and result[1] == 0:
        return result[0]
    return None


# =========================
# FLUXO FUNCIONÁRIO
# =========================

if token:
    colaborador_id = validar_token(token)

    if colaborador_id:
        st.title("Solicitação de Férias")

        data_inicio = st.date_input("Data de início")
        dias = st.number_input("Quantidade de dias", min_value=1)

        if st.button("Enviar"):
            valido, msg = validar_regras(data_inicio)

            if not valido:
                st.error(msg)
            else:
                conn = get_conn()
                c = conn.cursor()

                c.execute("""
                    INSERT INTO solicitacoes (colaborador_id, data_inicio, dias, status)
                    VALUES (?, ?, ?, 'PENDENTE')
                """, (colaborador_id, str(data_inicio), dias))

                c.execute("UPDATE tokens SET usado = 1 WHERE token = ?", (token,))

                conn.commit()
                conn.close()

                st.success("Solicitação enviada com sucesso!")
    else:
        st.error("Link inválido ou já utilizado.")


# =========================
# FLUXO ADMIN
# =========================

else:
    st.title("Painel Administrativo")

    tab1, tab2, tab3 = st.tabs(["Colaboradores", "Gerar Links", "Solicitações"])

    # -------------------------
    # COLABORADORES
    # -------------------------
    with tab1:
        st.subheader("Cadastrar colaborador")

        nome = st.text_input("Nome")
        cargo = st.text_input("Cargo")

        if st.button("Salvar"):
            conn = get_conn()
            c = conn.cursor()

            c.execute(
                "INSERT INTO colaboradores (nome, cargo) VALUES (?, ?)",
                (nome, cargo)
            )

            conn.commit()
            conn.close()

            st.success("Salvo com sucesso")

        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        st.dataframe(df)

    # -------------------------
    # GERAR LINKS
    # -------------------------
    with tab2:
        st.subheader("Gerar link")

        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)

        st.dataframe(df)

        colaborador_id = st.number_input("ID do colaborador", step=1)

        if st.button("Gerar Link"):
            token = gerar_token(colaborador_id)
            link = f"http://localhost:8501/?token={token}"

            st.success("Link gerado")
            st.code(link)

    # -------------------------
    # SOLICITAÇÕES
    # -------------------------
    with tab3:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM solicitacoes", conn)

        st.dataframe(df)
