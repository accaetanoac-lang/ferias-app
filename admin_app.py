import streamlit as st
import sqlite3
import uuid
import pandas as pd
import urllib.parse
from datetime import datetime, timedelta, date

from ferias import EQUIPE, LIMITES_EQUIPE

# deploy refresh - force Streamlit Cloud update
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

def validar_solicitacao(nome, data_inicio, dias, colaborador_id=None):
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

    # Verificar conflito de equipe (se colaborador_id fornecido)
    if colaborador_id:
        conflito, msg_conflito = verificar_conflito_equipe(data_inicio, dias, colaborador_id)
        if conflito:
            return False, msg_conflito

    return True, "Solicitação válida."

# ------------------------
# CALENDÁRIO INTELIGENTE
# ------------------------

def verificar_conflito_equipe(data_inicio, dias, colaborador_id):
    """Verifica se há conflito de equipe na data especificada."""
    # Buscar cargo do colaborador
    conn = get_conn()
    df_colab = pd.read_sql("""
        SELECT c.nome FROM colaboradores c WHERE c.id = ?
    """, conn, params=(colaborador_id,))
    conn.close()

    if df_colab.empty:
        return False, "Colaborador não encontrado."

    nome = df_colab.iloc[0]["nome"]
    cargo = EQUIPE.get(nome)

    if not cargo:
        return False, "Cargo não encontrado."

    limite = LIMITES_EQUIPE.get(cargo, 1)

    # Calcular período das férias
    data_fim = data_inicio + timedelta(days=dias - 1)

    # Buscar solicitações aprovadas no período
    conn = get_conn()
    df_solicitacoes = pd.read_sql("""
        SELECT s.colaborador_id, c.nome
        FROM solicitacoes s
        JOIN colaboradores c ON s.colaborador_id = c.id
        WHERE s.status = 'APROVADO'
        AND (
            (s.data_inicio <= ? AND DATE(s.data_inicio, '+' || (s.dias - 1) || ' days') >= ?) OR
            (s.data_inicio <= ? AND DATE(s.data_inicio, '+' || (s.dias - 1) || ' days') >= ?) OR
            (s.data_inicio >= ? AND DATE(s.data_inicio, '+' || (s.dias - 1) || ' days') <= ?)
        )
    """, conn, params=(str(data_inicio), str(data_inicio), str(data_fim), str(data_fim), str(data_inicio), str(data_fim)))
    conn.close()

    # Contar quantos do mesmo cargo estão de férias
    colegas_cargo = [row["nome"] for _, row in df_solicitacoes.iterrows() if EQUIPE.get(row["nome"]) == cargo]

    if len(colegas_cargo) >= limite:
        return True, f"Conflito: {len(colegas_cargo)}/{limite} {cargo}s já de férias."

    return False, f"OK: {len(colegas_cargo)}/{limite} {cargo}s de férias."

def verificar_alerta_conflito(colaborador_id, data_inicio, dias):
    """
    Verifica se há pessoas do mesmo cargo em férias no período.
    NÃO bloqueia, apenas alerta sobre a situação.
    
    Retorna: (tem_alerta: bool, lista_colegas: list)
    """
    # Buscar cargo do colaborador
    conn = get_conn()
    df_colab = pd.read_sql("""
        SELECT c.nome FROM colaboradores c WHERE c.id = ?
    """, conn, params=(colaborador_id,))
    conn.close()

    if df_colab.empty:
        return False, []

    nome = df_colab.iloc[0]["nome"]
    cargo = EQUIPE.get(nome)

    if not cargo:
        return False, []

    # Calcular período das férias
    data_fim = data_inicio + timedelta(days=dias - 1)

    # Buscar solicitações APROVADAS ou EM_ANDAMENTO no período (excluindo o próprio)
    conn = get_conn()
    df_conflitos = pd.read_sql("""
        SELECT DISTINCT c.nome, s.data_inicio, s.dias, s.status
        FROM solicitacoes s
        JOIN colaboradores c ON s.colaborador_id = c.id
        WHERE s.colaborador_id != ?
        AND s.status IN ('APROVADO', 'EM_ANDAMENTO')
        AND (
            (DATE(s.data_inicio) <= ? AND DATE(s.data_inicio, '+' || (s.dias - 1) || ' days') >= ?)
        )
    """, conn, params=(colaborador_id, str(data_fim), str(data_inicio)))
    conn.close()

    if df_conflitos.empty:
        return False, []

    # Filtrar apenas pessoas do mesmo cargo
    colegas_conflito = []
    for _, row in df_conflitos.iterrows():
        nome_colega = row["nome"]
        cargo_colega = EQUIPE.get(nome_colega)
        
        if cargo_colega == cargo:
            colegas_conflito.append({
                "nome": nome_colega,
                "data_inicio": row["data_inicio"],
                "dias": row["dias"],
                "status": row["status"]
            })

    if colegas_conflito:
        return True, colegas_conflito

    return False, []


def gerar_calendario_mes(ano, mes):
    """Gera dados do calendário para um mês específico."""
    from calendar import monthrange

    # Dias do mês
    _, ultimo_dia = monthrange(ano, mes)
    dias_mes = [date(ano, mes, dia) for dia in range(1, ultimo_dia + 1)]

    calendario = {}

    for dia in dias_mes:
        dia_str = dia.strftime("%Y-%m-%d")

        # Buscar solicitações para este dia
        conn = get_conn()
        df_dia = pd.read_sql("""
            SELECT s.id, c.nome, s.data_inicio, s.dias, s.status, s.tipo_divisao
            FROM solicitacoes s
            JOIN colaboradores c ON s.colaborador_id = c.id
            WHERE s.status IN ('APROVADO', 'PENDENTE', 'EM_ANDAMENTO')
            AND DATE(s.data_inicio) <= ?
            AND DATE(s.data_inicio, '+' || (s.dias - 1) || ' days') >= ?
        """, conn, params=(dia_str, dia_str))
        conn.close()

        ferias_dia = []
        status_dia = "NORMAL"
        conflito = False

        for _, row in df_dia.iterrows():
            nome = row["nome"]
            cargo = EQUIPE.get(nome, "Desconhecido")
            status = row["status"]
            tipo = row["tipo_divisao"]

            ferias_dia.append({
                "nome": nome,
                "cargo": cargo,
                "status": status,
                "tipo": tipo
            })

            # Verificar conflito de equipe
            limite = LIMITES_EQUIPE.get(cargo, 1)
            colegas_cargo = [f for f in ferias_dia if f["cargo"] == cargo]

            if len(colegas_cargo) > limite:
                conflito = True

        # Determinar status do dia
        if conflito:
            status_dia = "CONFLITO"
        elif ferias_dia:
            # Verificar se há diferentes status
            statuses = set(f["status"] for f in ferias_dia)
            if len(statuses) > 1:
                status_dia = "MISTO"
            elif "APROVADO" in statuses:
                status_dia = "APROVADO"
            elif "EM_ANDAMENTO" in statuses:
                status_dia = "EM_ANDAMENTO"
            else:
                status_dia = "PENDENTE"

        calendario[dia] = {
            "ferias": ferias_dia,
            "status": status_dia,
            "conflito": conflito,
            "quantidade": len(ferias_dia)
        }

    return calendario

def sugerir_melhor_periodo(colaborador_id, dias):
    """Sugere o melhor período disponível para férias."""
    from calendar import monthrange

    # Buscar informações do colaborador
    conn = get_conn()
    df_colab = pd.read_sql("""
        SELECT c.nome FROM colaboradores c WHERE c.id = ?
    """, conn, params=(colaborador_id,))
    conn.close()

    if df_colab.empty:
        return None, "Colaborador não encontrado."

    nome = df_colab.iloc[0]["nome"]
    cargo = EQUIPE.get(nome)

    if not cargo:
        return None, "Cargo não encontrado."

    limite = LIMITES_EQUIPE.get(cargo, 1)

    # Analisar próximos 6 meses
    hoje = date.today()
    sugestoes = []

    for meses_a_frente in range(6):
        mes_atual = hoje.month + meses_a_frente
        ano_atual = hoje.year + (mes_atual - 1) // 12
        mes_atual = ((mes_atual - 1) % 12) + 1

        calendario = gerar_calendario_mes(ano_atual, mes_atual)

        for dia, dados in calendario.items():
            if dia < hoje:
                continue

            # Verificar se o período cabe
            periodo_fim = dia + timedelta(days=dias - 1)

            # Verificar se todo o período está livre de conflitos
            periodo_livre = True
            carga_maxima = 0

            for d in range(dias):
                dia_check = dia + timedelta(days=d)
                if dia_check in calendario:
                    dados_dia = calendario[dia_check]
                    colegas_cargo = [f for f in dados_dia["ferias"] if f["cargo"] == cargo]
                    if len(colegas_cargo) >= limite:
                        periodo_livre = False
                        break
                    carga_maxima = max(carga_maxima, len(colegas_cargo))

            if periodo_livre:
                # Verificar validações básicas
                valido_janela, _ = validar_janela_ferias(dia)
                valido_data, _ = validar_data_inicio(dia)

                if valido_janela and valido_data:
                    pontuacao = (limite - carga_maxima) * 10  # Preferir períodos com menos colegas
                    sugestoes.append({
                        "data_inicio": dia,
                        "data_fim": periodo_fim,
                        "pontuacao": pontuacao,
                        "carga_maxima": carga_maxima
                    })

    # Ordenar por pontuação (maior = melhor)
    sugestoes.sort(key=lambda x: x["pontuacao"], reverse=True)

    return sugestoes[:5], "Sugestões geradas com sucesso."  # Top 5 sugestões

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

            # Validação final
            valido, msg = validar_solicitacao(nome, data_inicio, dias, colaborador_id)
            if not valido:
                st.error(f"❌ {msg}")
            else:
                # Verificar alerta de conflito (não bloqueante)
                tem_alerta, colegas_conflito = verificar_alerta_conflito(colaborador_id, data_inicio, dias)

                if tem_alerta:
                    st.warning("⚠️ Alerta de Conflito de Equipe")
                    st.write("Já existem funcionários da mesma função programados neste período:")
                    
                    # Listar colegas em conflito
                    for colega in colegas_conflito:
                        data_fim = datetime.strptime(colega["data_inicio"], "%Y-%m-%d").date() + timedelta(days=colega["dias"] - 1)
                        status_emoji = {
                            "APROVADO": "✅",
                            "EM_ANDAMENTO": "🔄"
                        }.get(colega["status"], "❓")
                        
                        st.write(
                            f"{status_emoji} **{colega['nome']}** - "
                            f"{colega['data_inicio']} até {data_fim.strftime('%d/%m/%Y')} "
                            f"({colega['dias']} dias)"
                        )

                    # Checkbox para confirmar
                    confirmar = st.checkbox(
                        "✅ Entendo o conflito e desejo continuar com a solicitação",
                        key="confirmar_conflito"
                    )

                    if not confirmar:
                        st.info("💡 Você pode usar a aba 'Calendário' para encontrar datas com menor conflito.")
                        st.stop()

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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Colaboradores",
        "🔗 Gerar Links",
        "📅 Solicitações",
        "📊 Calendário",
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

    # Tab 4: Calendário
    with tab4:
        st.header("📊 Calendário de Férias")

        # Selecionar mês e ano
        col1, col2 = st.columns(2)
        with col1:
            ano_selecionado = st.selectbox(
                "Ano",
                options=[2024, 2025, 2026, 2027, 2028],
                index=2  # 2026 por padrão
            )
        with col2:
            mes_selecionado = st.selectbox(
                "Mês",
                options=list(range(1, 13)),
                format_func=lambda x: ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                                     "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][x-1],
                index=date.today().month - 1
            )

        if st.button("📅 Gerar Calendário"):
            with st.spinner("Gerando calendário..."):
                calendario = gerar_calendario_mes(ano_selecionado, mes_selecionado)

            # Criar visualização em grid
            st.subheader(f"📅 {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                              'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'][mes_selecionado-1]} {ano_selecionado}")

            # Dias da semana como cabeçalho
            dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
            cols = st.columns(7)
            for i, dia in enumerate(dias_semana):
                cols[i].markdown(f"**{dia}**")

            # Calcular primeiro dia do mês
            primeiro_dia = date(ano_selecionado, mes_selecionado, 1)
            dia_semana_inicio = primeiro_dia.weekday()  # 0=seg, 6=dom

            # Criar grid do mês
            dia_atual = 1
            from calendar import monthrange
            _, ultimo_dia = monthrange(ano_selecionado, mes_selecionado)

            for semana in range(6):  # Máximo 6 semanas por mês
                cols = st.columns(7)
                for dia_semana in range(7):
                    with cols[dia_semana]:
                        if semana == 0 and dia_semana < dia_semana_inicio:
                            # Dias do mês anterior
                            st.write("")
                        elif dia_atual > ultimo_dia:
                            # Dias do mês seguinte
                            st.write("")
                        else:
                            # Dia válido do mês
                            dia_data = date(ano_selecionado, mes_selecionado, dia_atual)
                            dados_dia = calendario.get(dia_data, {"ferias": [], "status": "NORMAL", "quantidade": 0})

                            # Determinar cor e emoji baseado no status
                            if dados_dia["status"] == "CONFLITO":
                                cor = "🔴"
                                bg_color = "#ffcccc"
                            elif dados_dia["status"] == "APROVADO":
                                cor = "🟢"
                                bg_color = "#ccffcc"
                            elif dados_dia["status"] == "EM_ANDAMENTO":
                                cor = "🔵"
                                bg_color = "#ccccff"
                            elif dados_dia["status"] == "PENDENTE":
                                cor = "⚪"
                                bg_color = "#ffffcc"
                            else:
                                cor = "⚫"
                                bg_color = "#f0f0f0"

                            # Criar botão/elemento clicável
                            if dados_dia["quantidade"] > 0:
                                if st.button(
                                    f"{cor} {dia_atual}\n{dados_dia['quantidade']} pessoa{'s' if dados_dia['quantidade'] != 1 else ''}",
                                    key=f"dia_{dia_atual}",
                                    help=f"Clique para ver detalhes de {dia_data.strftime('%d/%m/%Y')}"
                                ):
                                    # Mostrar detalhes em um expander
                                    with st.expander(f"📅 Detalhes de {dia_data.strftime('%d/%m/%Y')}", expanded=True):
                                        if dados_dia["conflito"]:
                                            st.error("🚨 CONFLITO DE EQUIPE DETECTADO!")

                                        for ferias in dados_dia["ferias"]:
                                            status_emoji = {
                                                "APROVADO": "✅",
                                                "EM_ANDAMENTO": "🔄",
                                                "PENDENTE": "⏳"
                                            }.get(ferias["status"], "❓")

                                            st.write(f"{status_emoji} **{ferias['nome']}** - {ferias['cargo']} ({ferias['tipo']})")
                            else:
                                # Dia sem férias
                                st.button(
                                    f"⚫ {dia_atual}",
                                    key=f"dia_{dia_atual}",
                                    disabled=True,
                                    help=f"Nenhuma férias em {dia_data.strftime('%d/%m/%Y')}"
                                )

                            dia_atual += 1

                            if dia_atual > ultimo_dia:
                                break

                if dia_atual > ultimo_dia:
                    break

        # Sugestão automática
        st.divider()
        st.subheader("🎯 Sugestão Automática de Período")

        conn = get_conn()
        df_colaboradores = pd.read_sql("SELECT id, nome FROM colaboradores", conn)
        conn.close()

        if not df_colaboradores.empty:
            colaborador_nome = st.selectbox(
                "Selecione colaborador para sugestão",
                df_colaboradores["nome"],
                key="sugestao_colaborador"
            )

            dias_sugestao = st.selectbox(
                "Dias de férias",
                [15, 20, 30],
                key="sugestao_dias"
            )

            if st.button("🔍 Sugerir Melhor Período"):
                colaborador_id = df_colaboradores[df_colaboradores["nome"] == colaborador_nome]["id"].values[0]

                with st.spinner("Analisando calendário..."):
                    sugestoes, msg = sugerir_melhor_periodo(colaborador_id, dias_sugestao)

                if sugestoes:
                    st.success(f"✅ {len(sugestoes)} sugestões encontradas!")

                    for i, sugestao in enumerate(sugestoes[:3], 1):  # Top 3
                        with st.container():
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                st.write(f"**Sugestão {i}:** {sugestao['data_inicio'].strftime('%d/%m/%Y')} - {sugestao['data_fim'].strftime('%d/%m/%Y')}")
                            with col2:
                                st.write(f"Carga máxima: {sugestao['carga_maxima']} colega(s)")
                            with col3:
                                st.write(f"Score: {sugestao['pontuacao']}")
                else:
                    st.warning("Nenhuma sugestão disponível no momento.")

    # Tab 5: Configurações
    with tab5:
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