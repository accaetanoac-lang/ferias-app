import streamlit as st
import sqlite3
import uuid
import pandas as pd
import urllib.parse
from datetime import datetime, timedelta, date
from pathlib import Path

st.set_page_config(page_title="Gestão de Férias", layout="wide")

# ------------------------
# FERIADOS DINÂMICOS
# ------------------------

def easter_date(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def get_feriados(ano):
    feriados = []
    fixos = [(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)]
    for m,d in fixos:
        feriados.append(date(ano,m,d))

    pascoa = easter_date(ano)
    feriados += [
        pascoa - timedelta(days=2),
        pascoa - timedelta(days=47),
        pascoa + timedelta(days=60)
    ]

    return [d.strftime("%Y-%m-%d") for d in feriados]

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
        nome TEXT UNIQUE,
        telefone TEXT,
        email TEXT,
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
        tipo_divisao TEXT,
        status TEXT DEFAULT 'PENDENTE',
        tem_conflito INTEGER DEFAULT 0,
        data_aprovacao TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS controle_ferias (
        colaborador_id INTEGER PRIMARY KEY,
        saldo_total INTEGER DEFAULT 30,
        saldo_utilizado INTEGER DEFAULT 0,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
    )
    """)

    conn.commit()
    conn.close()

# ------------------------
# IMPORTAÇÃO EXCEL
# ------------------------

def importar_equipe():
    try:
        caminho_xlsx = Path("ferias_equipe.xlsx")

        if not caminho_xlsx.exists():
            return

        df = pd.read_excel(caminho_xlsx)

        if df.empty:
            return

        expected_columns = {"Nome_Completo", "Telefone", "Email", "Cargo"}
        if not expected_columns.issubset(set(df.columns)):
            return

        conn = get_conn()
        c = conn.cursor()

        for _, row in df.iterrows():
            nome = str(row.get("Nome_Completo", "")).strip()
            telefone = str(row.get("Telefone", "")).strip()
            email = str(row.get("Email", "")).strip()
            cargo = str(row.get("Cargo", "")).strip()

            if not nome:
                continue

            # Verificar se já existe
            c.execute("SELECT id FROM colaboradores WHERE nome = ?", (nome,))
            if c.fetchone():
                continue  # Já existe, pular

            c.execute(
                """
                INSERT INTO colaboradores (nome, telefone, email, cargo)
                VALUES (?, ?, ?, ?)
                """,
                (nome, telefone, email, cargo),
            )

        conn.commit()
        conn.close()
    except Exception as e:
        st.warning(f"Erro ao importar equipe: {e}")


def init_controle_ferias():
    conn = get_conn()
    c = conn.cursor()

    colaboradores = c.execute("SELECT id FROM colaboradores").fetchall()

    for col in colaboradores:
        c.execute(
            "INSERT OR IGNORE INTO controle_ferias (colaborador_id, saldo_total, saldo_utilizado) VALUES (?, ?, ?)",
            (col[0], 30, 0)
        )

    conn.commit()
    conn.close()

# ------------------------
# VALIDAÇÕES
# ------------------------

def validar_data_inicio(data_inicio):
    if data_inicio.weekday() == 4:
        return False, "Não pode iniciar sexta-feira"

    feriados = get_feriados(data_inicio.year)
    if (data_inicio + timedelta(days=1)).strftime("%Y-%m-%d") in feriados:
        return False, "Véspera de feriado"

    return True, ""

def validar_janela(data):
    m,d = data.month, data.day
    if (m==6 and d>=1) or (m==7 and d<=15):
        return True
    if m in [9,10,11,12,1,2] or (m==3 and d<=30):
        return True
    return False

# ------------------------
# SALDO DE FÉRIAS
# ------------------------

def get_saldo_restante(colaborador_id):
    conn = get_conn()
    df = pd.read_sql(
        "SELECT saldo_total, saldo_utilizado FROM controle_ferias WHERE colaborador_id = ?",
        conn,
        params=(colaborador_id,)
    )
    conn.close()
    if df.empty:
        return 30
    row = df.iloc[0]
    return int(row["saldo_total"] - row["saldo_utilizado"])


def incrementar_saldo_utilizado(colaborador_id, dias):
    conn = get_conn()
    conn.execute("""
        UPDATE controle_ferias
        SET saldo_utilizado = saldo_utilizado + ?
        WHERE colaborador_id = ?
    """, (dias, colaborador_id))
    conn.commit()
    conn.close()

# ------------------------
# NOTIFICAÇÕES
# ------------------------

def gerar_link_whatsapp(telefone, mensagem):
    telefone_formatado = str(telefone).strip()
    if telefone_formatado.startswith("0"):
        telefone_formatado = telefone_formatado[1:]
    if telefone_formatado and not telefone_formatado.startswith("55"):
        telefone_formatado = f"55{telefone_formatado}"
    mensagem_codificada = urllib.parse.quote(mensagem)
    if telefone_formatado:
        return f"https://wa.me/{telefone_formatado}?text={mensagem_codificada}"
    return f"https://wa.me/?text={mensagem_codificada}"


def enviar_email(destino, assunto, mensagem):
    return {
        "destino": destino,
        "assunto": assunto,
        "mensagem": mensagem,
        "status": "pronto"
    }

# ------------------------# CONFLITO
# ------------------------

def verificar_alerta(colaborador_id, data_inicio, dias):
    conn = get_conn()

    df = pd.read_sql("""
    SELECT c2.nome, c2.cargo, s.data_inicio, s.dias
    FROM solicitacoes s
    JOIN colaboradores c1 ON c1.id = ?
    JOIN colaboradores c2 ON c2.id = s.colaborador_id
    WHERE c1.cargo = c2.cargo
    AND s.status IN ('APROVADO','PENDENTE')
    """, conn, params=(colaborador_id,))

    conn.close()

    conflitos = []
    fim = data_inicio + timedelta(days=dias-1)

    for _,r in df.iterrows():
        inicio2 = datetime.strptime(r["data_inicio"], "%Y-%m-%d").date()
        fim2 = inicio2 + timedelta(days=r["dias"]-1)

        if not (fim < inicio2 or data_inicio > fim2):
            conflitos.append(r["nome"])

    return conflitos

# ------------------------
# TOKEN
# ------------------------

def gerar_token(colaborador_id):
    token = str(uuid.uuid4())
    conn = get_conn()
    conn.execute("INSERT INTO tokens (colaborador_id, token) VALUES (?,?)",(colaborador_id,token))
    conn.commit()
    conn.close()
    return token

def validar_token(token):
    conn = get_conn()
    r = conn.execute("SELECT colaborador_id, usado FROM tokens WHERE token=?",(token,)).fetchone()
    conn.close()
    return r[0] if r and r[1]==0 else None

# ------------------------
# INIT
# ------------------------

init_db()
importar_equipe()
init_controle_ferias()

BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")
params = st.query_params
token = params.get("token")

# ------------------------
# FUNCIONÁRIO
# ------------------------

if token:
    colab_id = validar_token(token)

    if colab_id:
        conn = get_conn()
        df_nome = pd.read_sql("SELECT nome FROM colaboradores WHERE id=?", conn, params=(colab_id,))
        conn.close()

        if df_nome.empty:
            st.error("Colaborador não encontrado")
            st.stop()

        nome = df_nome.iloc[0][0]

        st.title("Solicitação de Férias")
        st.write(nome)

        data_inicio = st.date_input("Data início")
        tipo = st.selectbox("Tipo",["30 dias","15 + 15 dias","20 + 10 dias"])
        dias = st.number_input("Dias",min_value=1,max_value=30)

        saldo_restante = get_saldo_restante(colab_id)
        st.info(f"Saldo disponível: {saldo_restante} dias")

        if st.button("Enviar"):

            ok,msg = validar_data_inicio(data_inicio)
            if not ok:
                st.error(msg)
                st.stop()

            if not validar_janela(data_inicio):
                st.error("Fora da janela")
                st.stop()

            saldo_restante = get_saldo_restante(colab_id)
            if dias > saldo_restante:
                st.error(f"Saldo insuficiente. Disponível: {saldo_restante} dias.")
                st.stop()

            conflitos = verificar_alerta(colab_id,data_inicio,dias)

            if conflitos:
                st.warning(f"Já existem: {', '.join(conflitos)}")
                if not st.checkbox("Continuar mesmo assim"):
                    st.stop()

            status_inicial = "PENDENTE_ANALISE" if conflitos else "PENDENTE"
            conn = get_conn()
            conn.execute("""
            INSERT INTO solicitacoes (colaborador_id,data_inicio,dias,tipo_divisao,status,tem_conflito)
            VALUES (?,?,?,?,?,?)
            """,(colab_id,str(data_inicio),dias,tipo,status_inicial,1 if conflitos else 0))

            conn.execute("UPDATE tokens SET usado=1 WHERE token=?",(token,))
            conn.commit()
            conn.close()

            st.success("Enviado para aprovação")

            conn_gestor = get_conn()
            gestor_df = pd.read_sql(
                "SELECT telefone FROM colaboradores WHERE cargo LIKE '%gestor%' OR cargo LIKE '%Gestor%' LIMIT 1",
                conn_gestor
            )
            conn_gestor.close()

            if not gestor_df.empty and gestor_df.iloc[0][0]:
                link = gerar_link_whatsapp(gestor_df.iloc[0][0], f"Nova solicitação de férias de {nome}")
                st.markdown(f"[📲 Notificar Gestor via WhatsApp]({link})")

# ------------------------
# ADMIN
# ------------------------

else:
    st.title("Painel Administrativo")

    tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs(["Colaboradores","Links","Solicitações","Calendário","Dashboard","Relatório RH"])

    with tab1:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        conn.close()
        st.subheader("Colaboradores")
        st.dataframe(df)

    with tab2:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        conn.close()
        nome = st.selectbox("Colaborador", df["nome"])

        if st.button("Gerar"):
            id = int(df[df["nome"]==nome]["id"].values[0])
            t = gerar_token(id)
            link = f"{BASE_URL}/?token={t}"
            st.code(link)

    with tab3:
        conn = get_conn()
        df = pd.read_sql("""
        SELECT s.id, s.colaborador_id, c.nome, s.data_inicio, s.dias, s.tipo_divisao, s.status, s.data_aprovacao
        FROM solicitacoes s JOIN colaboradores c ON c.id=s.colaborador_id
        ORDER BY s.status, s.data_inicio
        """, conn)
        conn.close()

        if df.empty:
            st.info("Nenhuma solicitação encontrada.")
        else:
            for _, row in df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([2,2,1])
                    with col1:
                        st.write(f"**{row['nome']}**")
                        st.write(f"Data início: {row['data_inicio']}")
                        st.write(f"Dias: {row['dias']}")
                        st.write(f"Tipo: {row['tipo_divisao']}")
                    with col2:
                        st.write(f"Status: {row['status']}")
                        if row['data_aprovacao']:
                            st.write(f"Aprovado em: {row['data_aprovacao']}")
                    with col3:
                        if row['status'] != 'APROVADO':
                            if st.button(f"✅ Aprovar {row['id']}", key=f"aprovar_{row['id']}"):
                                conn = get_conn()
                                conn.execute("""
                                    UPDATE solicitacoes
                                    SET status='APROVADO', data_aprovacao = datetime('now')
                                    WHERE id = ?
                                """, (row['id'],))
                                conn.commit()
                                conn.close()
                                incrementar_saldo_utilizado(int(row['colaborador_id']), int(row['dias']))
                                st.experimental_rerun()
                            if st.button(f"❌ Reprovar {row['id']}", key=f"reprovar_{row['id']}"):
                                conn = get_conn()
                                conn.execute("""
                                    UPDATE solicitacoes
                                    SET status='REPROVADO'
                                    WHERE id = ?
                                """, (row['id'],))
                                conn.commit()
                                conn.close()
                                st.experimental_rerun()
                        else:
                            conn = get_conn()
                            telefone_df = pd.read_sql("SELECT telefone FROM colaboradores WHERE id = ?", conn, params=(row['colaborador_id'],))
                            conn.close()

                            if telefone_df.empty:
                                st.error("Telefone não encontrado")
                                st.stop()

                            if telefone_df.iloc[0,0]:
                                wa_link = gerar_link_whatsapp(telefone_df.iloc[0,0], "Sua solicitação foi APROVADA")
                                st.markdown(f"[📲 Notificar Funcionário via WhatsApp]({wa_link})")

    with tab4:
        st.subheader("Calendário")
        st.write("Visualização do calendário será implementada em breve.")

    with tab5:
        conn = get_conn()
        df_total_colab = pd.read_sql("SELECT COUNT(*) AS total FROM colaboradores", conn)
        total_colab = df_total_colab.iloc[0,0] if not df_total_colab.empty else 0

        df_pendentes = pd.read_sql("SELECT COUNT(*) AS total FROM solicitacoes WHERE status='PENDENTE'", conn)
        pendentes = df_pendentes.iloc[0,0] if not df_pendentes.empty else 0

        df_aprovadas = pd.read_sql("SELECT COUNT(*) AS total FROM solicitacoes WHERE status='APROVADO'", conn)
        aprovadas = df_aprovadas.iloc[0,0] if not df_aprovadas.empty else 0

        df_em_andamento = pd.read_sql("SELECT COUNT(*) AS total FROM solicitacoes WHERE status='EM_ANDAMENTO'", conn)
        em_andamento = df_em_andamento.iloc[0,0] if not df_em_andamento.empty else 0

        df_mes = pd.read_sql("""
            SELECT substr(data_inicio,1,7) AS mes, COUNT(*) AS total
            FROM solicitacoes
            WHERE status='APROVADO'
            GROUP BY mes
            ORDER BY mes
        """, conn)
        df_carga = pd.read_sql("""
            SELECT c.cargo, COUNT(*) AS total
            FROM solicitacoes s JOIN colaboradores c ON c.id=s.colaborador_id
            GROUP BY c.cargo
        """, conn)
        conn.close()

        st.subheader("Dashboard Executivo")
        cols = st.columns(4)
        cols[0].metric("Total colaboradores", int(total_colab))
        cols[1].metric("Solicitações pendentes", int(pendentes))
        cols[2].metric("Aprovadas", int(aprovadas))
        cols[3].metric("Em andamento", int(em_andamento))

        st.subheader("Férias por mês")
        if not df_mes.empty:
            df_mes = df_mes.set_index('mes')
            st.bar_chart(df_mes['total'])
        else:
            st.info("Nenhum dado aprovado disponível.")

        st.subheader("Carga por equipe")
        st.dataframe(df_carga)

    with tab6:
        conn = get_conn()
        df = pd.read_sql("""
            SELECT c.nome, c.cargo, s.data_inicio, s.dias, s.data_aprovacao
            FROM solicitacoes s JOIN colaboradores c ON c.id=s.colaborador_id
            WHERE s.status = 'APROVADO'
        """, conn)
        conn.close()

        st.subheader("Relatório RH")
        st.dataframe(df)
        if not df.empty:
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button("Exportar CSV", csv, file_name='ferias_aprovadas.csv', mime='text/csv')