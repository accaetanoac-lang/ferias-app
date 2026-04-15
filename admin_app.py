import streamlit as st
import sqlite3
import uuid
import pandas as pd
import urllib.parse
from datetime import datetime, timedelta, date

from ferias import EQUIPE

st.set_page_config(page_title="Gestão de Férias", layout="wide")

# ------------------------
# FERIADOS DINÂMICOS
# ------------------------

def easter_date(year):
    """Calcula a data da Páscoa usando o algoritmo de Meeus."""
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
    """Retorna lista de feriados no formato YYYY-MM-DD para o ano especificado."""
    feriados = []

    # Feriados fixos
    feriados_fixos = [
        (1, 1),   # Ano Novo
        (4, 21),  # Tiradentes
        (5, 1),   # Dia do Trabalho
        (9, 7),   # Independência
        (10, 12), # Nossa Senhora Aparecida
        (11, 2),  # Finados
        (11, 15), # Proclamação da República
        (12, 25)  # Natal
    ]

    for mes, dia in feriados_fixos:
        feriados.append(date(ano, mes, dia))

    # Feriados móveis baseados na Páscoa
    pascoa = easter_date(ano)
    sexta_santa = pascoa - timedelta(days=2)
    carnaval = pascoa - timedelta(days=47)
    corpus_christi = pascoa + timedelta(days=60)

    feriados.extend([sexta_santa, carnaval, corpus_christi])

    # Retornar como strings YYYY-MM-DD
    return [d.strftime("%Y-%m-%d") for d in feriados]

# ------------------------
# BANCO DE DADOS
# ------------------------

def get_conn():
    return sqlite3.connect("ferias.db", check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Tabela de colaboradores
    c.execute("""
    CREATE TABLE IF NOT EXISTS colaboradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    )
    """)

    # Tabela de tokens para links únicos
    c.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        usado INTEGER DEFAULT 0,
        criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores (id)
    )
    """)

    # Tabela de solicitações de férias
    c.execute("""
    CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        data_inicio TEXT NOT NULL,
        dias INTEGER NOT NULL,
        tipo_divisao TEXT NOT NULL,
        status TEXT DEFAULT 'PENDENTE',
        criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores (id)
    )
    """)

    # Tabela de controle de saldo de férias
    c.execute("""
    CREATE TABLE IF NOT EXISTS controle_ferias (
        colaborador_id INTEGER PRIMARY KEY,
        saldo INTEGER DEFAULT 30,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores (id)
    )
    """)

    conn.commit()
    conn.close()

# ------------------------
# IMPORTAÇÃO DE DADOS
# ------------------------

def importar_equipe():
    """Importa equipe do ferias.py para o banco."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM colaboradores")

    for nome in EQUIPE.keys():
        c.execute(
            "INSERT OR IGNORE INTO colaboradores (nome) VALUES (?)",
            (nome,)
        )

    conn.commit()
    conn.close()

def importar_controle():
    """Importa saldos de férias da planilha Excel."""
    try:
        df = pd.read_excel("ferias_equipe.xlsx", sheet_name="controle de ferias")
        conn = get_conn()
        c = conn.cursor()

        c.execute("DELETE FROM controle_ferias")

        for _, row in df.iterrows():
            nome = row.get("Nome")
            saldo = row.get("Saldo", 30)

            # Buscar ID do colaborador
            c.execute("SELECT id FROM colaboradores WHERE nome = ?", (nome,))
            result = c.fetchone()

            if result:
                colaborador_id = result[0]
                c.execute("""
                    INSERT INTO controle_ferias (colaborador_id, saldo)
                    VALUES (?, ?)
                """, (colaborador_id, saldo))

        conn.commit()
        conn.close()
        st.success("Controle de férias importado com sucesso!")

    except Exception as e:
        st.error(f"Erro ao importar controle: {e}")

# ------------------------
# VALIDAÇÕES
# ------------------------

def validar_janela_ferias(data_inicio):
    """Valida se a data está na janela permitida."""
    mes = data_inicio.month
    dia = data_inicio.day

    # Janela 1: 01/06 até 15/07
    if (mes == 6 and dia >= 1) or (mes == 7 and dia <= 15):
        return True, "Janela de férias válida (01/06 - 15/07)."

    # Janela 2: 01/09 até 30/03 (considerando virada de ano)
    if mes in [9, 10, 11, 12] or mes in [1, 2] or (mes == 3 and dia <= 30):
        return True, "Janela de férias válida (01/09 - 30/03)."

    return False, "Data fora da janela permitida (01/06-15/07 ou 01/09-30/03)."

def validar_data_inicio(data_inicio):
    """Valida regras de data de início."""
    # Não pode ser sexta-feira
    if data_inicio.weekday() == 4:  # 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom
        return False, "Data de início não pode ser sexta-feira."

    # Não pode ser véspera de feriado
    ano = data_inicio.year
    feriados = get_feriados(ano)
    dia_seguinte = data_inicio + timedelta(days=1)
    dia_seguinte_str = dia_seguinte.strftime("%Y-%m-%d")

    if dia_seguinte_str in feriados:
        return False, f"Data de início não pode ser véspera de feriado ({dia_seguinte_str})."

    return True, "Data de início válida."

def validar_periodo(dias):
    """Valida se o período é permitido."""
    if dias not in [15, 20, 30]:
        return False, "Período inválido. Apenas 15, 20 ou 30 dias são permitidos."
    return True, "Período válido."

def validar_divisao(tipo_divisao, dias):
    """Valida se a divisão corresponde aos dias informados."""
    mapeamento = {
        "30 dias": 30,
        "15 + 15 dias": 15,
        "20 + 10 dias": 20
    }

    esperado = mapeamento.get(tipo_divisao)
    if esperado is None:
        return False, "Tipo de divisão inválido."

    if dias != esperado:
        return False, f"Para '{tipo_divisao}', deve solicitar {esperado} dias."

    return True, "Divisão válida."

def validar_solicitacao(nome, data_inicio, dias):
    """Validação final usando regras de negócio."""
    if nome not in EQUIPE:
        return False, "Funcionário não encontrado na equipe."

    if dias < 5:
        return False, "Mínimo de 5 dias de férias."

    if dias > 30:
        return False, "Máximo de 30 dias de férias."

    # Verificar safra (16/07 a 31/08)
    if (data_inicio.month == 7 and data_inicio.day > 15) or data_inicio.month == 8:
        return False, "Período bloqueado durante safra (16/07 - 31/08)."

    # Verificar saldo
    conn = get_conn()
    df = pd.read_sql("""
        SELECT saldo FROM controle_ferias
        WHERE colaborador_id = (
            SELECT id FROM colaboradores WHERE nome = ?
        )
    """, conn, params=(nome,))
    conn.close()

    if not df.empty:
        saldo = df.iloc[0]["saldo"]
        if dias > saldo:
            return False, f"Saldo insuficiente. Disponível: {saldo} dias."

    return True, "Solicitação válida."

# ------------------------
# TOKENS
# ------------------------

def gerar_token(colaborador_id):
    """Gera um token único para o colaborador."""
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
    """Valida se o token é válido e não foi usado."""
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
# INICIALIZAÇÃO
# ------------------------

init_db()
importar_equipe()
importar_controle()

# ------------------------
# CONFIGURAÇÃO
# ------------------------

BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")
params = st.query_params
token = params.get("token")

# ------------------------
# INTERFACE FUNCIONÁRIO
# ------------------------

if token:
    colaborador_id = validar_token(token)

    if colaborador_id:
        st.title("🚀 Solicitação de Férias")

        # Buscar nome do colaborador
        conn = get_conn()
        nome_df = pd.read_sql(
            "SELECT nome FROM colaboradores WHERE id = ?",
            conn,
            params=(colaborador_id,)
        )
        conn.close()
        nome = nome_df.iloc[0]["nome"]

        st.subheader(f"Olá, {nome}!")

        # Formulário
        with st.form("form_ferias"):
            data_inicio = st.date_input(
                "📅 Data de início",
                min_value=date.today(),
                help="Escolha a data de início das férias"
            )

            tipo_divisao = st.selectbox(
                "📊 Tipo de período",
                ["30 dias", "15 + 15 dias", "20 + 10 dias"],
                help="Selecione o tipo de período desejado"
            )

            dias = st.number_input(
                "⏱️ Dias",
                min_value=1,
                max_value=30,
                value=30,
                help="Número de dias a solicitar"
            )

            submitted = st.form_submit_button("📤 Enviar Solicitação")

        if submitted:
            # Validações em ordem obrigatória
            valido, msg = validar_janela_ferias(data_inicio)
            if not valido:
                st.error(f"❌ {msg}")
                st.stop()

            valido, msg = validar_data_inicio(data_inicio)
            if not valido:
                st.error(f"❌ {msg}")
                st.stop()

            valido, msg = validar_periodo(dias)
            if not valido:
                st.error(f"❌ {msg}")
                st.stop()

            valido, msg = validar_divisao(tipo_divisao, dias)
            if not valido:
                st.error(f"❌ {msg}")
                st.stop()

            # Validação final com ferias.py
            valido, msg = validar_solicitacao(nome, data_inicio, dias)
            if not valido:
                st.error(f"❌ {msg}")
            else:
                # Salvar solicitação
                conn = get_conn()
                c = conn.cursor()

                c.execute("""
                    INSERT INTO solicitacoes (colaborador_id, data_inicio, dias, tipo_divisao, status)
                    VALUES (?, ?, ?, ?, 'APROVADO')
                """, (colaborador_id, str(data_inicio), dias, tipo_divisao))

                # Marcar token como usado
                c.execute(
                    "UPDATE tokens SET usado = 1 WHERE token = ?",
                    (token,)
                )

                conn.commit()
                conn.close()

                st.success("✅ Solicitação aprovada automaticamente!")
                st.balloons()

    else:
        st.error("🔒 Link inválido ou já utilizado.")

# ------------------------
# INTERFACE ADMIN
# ------------------------

else:
    st.title("👨‍💼 Painel Administrativo - Gestão de Férias")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Colaboradores",
        "🔗 Gerar Links",
        "📅 Solicitações",
        "⚙️ Configurações"
    ])

    # Tab 1: Colaboradores
    with tab1:
        st.header("Colaboradores Cadastrados")
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        conn.close()

        if df.empty:
            st.warning("Nenhum colaborador encontrado.")
        else:
            st.dataframe(df, use_container_width=True)

    # Tab 2: Gerar Links
    with tab2:
        st.header("Gerar Link de Solicitação")

        conn = get_conn()
        df = pd.read_sql("SELECT * FROM colaboradores", conn)
        conn.close()

        if df.empty:
            st.warning("Nenhum colaborador encontrado.")
        else:
            nome = st.selectbox("Selecione o colaborador", df["nome"])

            if st.button("🔗 Gerar Link"):
                colaborador_id = df[df["nome"] == nome]["id"].values[0]
                token = gerar_token(colaborador_id)
                link = f"{BASE_URL}/?token={token}"

                st.success("Link gerado com sucesso!")
                st.code(link, language="text")

                # Link para WhatsApp
                mensagem = f"Olá {nome}, acesse o link para solicitar suas férias: {link}"
                mensagem_encoded = urllib.parse.quote(mensagem)
                wa_link = f"https://wa.me/?text={mensagem_encoded}"
                st.link_button("📱 Enviar via WhatsApp", wa_link)

    # Tab 3: Solicitações
    with tab3:
        st.header("Solicitações de Férias")

        conn = get_conn()
        df = pd.read_sql("""
            SELECT s.id, c.nome, s.data_inicio, s.dias, s.tipo_divisao, s.status, s.criado_em
            FROM solicitacoes s
            JOIN colaboradores c ON s.colaborador_id = c.id
            ORDER BY s.criado_em DESC
        """, conn)
        conn.close()

        if df.empty:
            st.info("Nenhuma solicitação encontrada.")
        else:
            st.dataframe(df, use_container_width=True)

    # Tab 4: Configurações
    with tab4:
        st.header("Configurações do Sistema")

        if st.button("🔄 Reimportar Equipe"):
            importar_equipe()
            st.success("Equipe reimportada!")

        if st.button("📊 Reimportar Controle de Férias"):
            importar_controle()

        st.subheader("Feriados do Ano Atual")
        ano_atual = date.today().year
        feriados = get_feriados(ano_atual)
        st.write(f"Feriados para {ano_atual}:")
        for feriado in sorted(feriados):
            st.write(f"- {feriado}")