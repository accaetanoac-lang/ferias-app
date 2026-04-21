import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

import io
import socket
import time
from datetime import date, timedelta
from typing import List, Optional, Tuple


def _app_port() -> int:
    """Porta do processo (Streamlit Cloud define PORT; local padrão 8501)."""
    try:
        return int(os.environ.get("PORT", "8501"))
    except ValueError:
        return 8501

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_calendar import calendar
import uuid
import bcrypt

from database import DB_PATH, get_conn, init_db
from repository import (
    atualizar_status_solicitacao,
    buscar_colaborador,
    colaborador_row_para_dict,
    criar_colaborador,
    listar_colaboradores,
    listar_colaboradores_sem_programacao,
    listar_solicitacoes_com_status,
    salvar_solicitacao,
    seed_colaboradores_if_needed,
)
import ferias
from escala import aplicar_flags_escala, obter_flags_nova_solicitacao_escala
from google_calendar import criar_evento, periodo_valido


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def _qp_first(key: str, default: str = "") -> str:
    query_params = st.query_params
    if key not in query_params:
        return default
    v = query_params[key]
    if isinstance(v, (list, tuple)):
        return str(v[0]) if v else default
    return str(v) if v is not None else default


ip = get_local_ip()
query_params = st.query_params
modo = _qp_first("modo", "admin")
MODO_IS_FORM = str(modo).lower() == "form"

st.set_page_config(
    page_title=(
        "Solicitação de Férias" if MODO_IS_FORM else "Gestão de Férias"
    ),
    layout="centered" if MODO_IS_FORM else "wide",
)

if not MODO_IS_FORM:
    _p = _app_port()
    st.info(f"Acesse no celular (rede local): http://{ip}:{_p}/")
    st.warning(
        "Se não abrir no celular, libere a porta do app no firewall (rede local) "
        "ou use a URL pública do deploy no Streamlit Cloud."
    )

_MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def gerar_insights(df: pd.DataFrame) -> dict:
    """Estrutura para análises e evolução com IA (placeholder)."""
    if df.empty or "excesso_funcao" not in df.columns:
        return {"risco": 0, "pico_mes": None}
    df_i = df.copy()
    risco = int(len(df_i[df_i["excesso_funcao"] == True]))
    if "data_inicio_1" not in df_i.columns:
        return {"risco": risco, "pico_mes": None}
    mes = pd.to_datetime(df_i["data_inicio_1"], errors="coerce").dt.month
    if mes.notna().any():
        pico = mes.value_counts().idxmax()
    else:
        pico = None
    return {"risco": risco, "pico_mes": pico}


# =========================
# SENHA ADMIN
# =========================

def admin_tem_senha():
    conn = get_conn()
    row = conn.execute("SELECT senha_hash FROM admin_senha LIMIT 1").fetchone()
    conn.close()
    return bool(row and row[0])


def definir_senha_admin(senha: str):
    conn = get_conn()
    senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    conn.execute("DELETE FROM admin_senha")
    conn.execute("INSERT INTO admin_senha (senha_hash) VALUES (?)", (senha_hash,))
    conn.commit()
    conn.close()


def verificar_senha_admin(senha: str):
    conn = get_conn()
    row = conn.execute("SELECT senha_hash FROM admin_senha LIMIT 1").fetchone()
    conn.close()

    if not row:
        return False

    return bcrypt.checkpw(senha.encode(), row[0].encode())


# =========================
# TOKEN
# =========================

def gerar_token(colab_id):
    token = str(uuid.uuid4())

    conn = get_conn()
    conn.execute(
        "INSERT INTO tokens (colaborador_id, token) VALUES (?,?)",
        (colab_id, token),
    )
    conn.commit()
    conn.close()

    return token


def validar_token(token):
    conn = get_conn()
    row = conn.execute(
        "SELECT colaborador_id FROM tokens WHERE token=?",
        (token,),
    ).fetchone()
    conn.close()

    return row[0] if row else None


def buscar_colaborador_por_token(token: str):
    cid = validar_token(token)
    if not cid:
        return None
    row = buscar_colaborador(cid)
    return colaborador_row_para_dict(row)


def gerar_link_form(
    token: str, ip: str, porta: Optional[int] = None
) -> str:
    p = _app_port() if porta is None else porta
    return f"http://{ip}:{p}/?modo=form&token={token}"


# =========================
# FORM FUNCIONÁRIO
# =========================

def _inserir_solicitacao_ferias(
    colab_id: int, colab: dict, periodos: List[Tuple[date, date]]
) -> bool:
    conn = get_conn()
    try:
        for di, df in periodos:
            dias = (df - di).days + 1
            cur = conn.execute(
                """
                SELECT 1 FROM ferias
                WHERE colaborador_id = ?
                AND date(data_inicio) <= date(?)
                AND date(data_fim) >= date(?)
                """,
                (colab_id, str(df), str(di)),
            )

            if cur.fetchone():
                st.error("Já existe férias nesse período")
                return False

            erro_funcao = ferias.validar_conflito_funcao(
                conn,
                colab["funcao"],
                di,
                df,
            )

            if erro_funcao:
                st.error(erro_funcao)
                return False

            conn.execute(
                """
                INSERT INTO ferias
                (colaborador_id, data_inicio, data_fim, dias, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    colab_id,
                    str(di),
                    str(df),
                    dias,
                    "PENDENTE",
                ),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao salvar: {e}")
        return False
    finally:
        conn.close()

    return True


def _data_fim_e_retorno(data_inicio: date, dias: int) -> Tuple[date, date]:
    data_fim = data_inicio + timedelta(days=dias - 1)
    data_retorno = data_fim + timedelta(days=1)
    return data_fim, data_retorno


def _montar_periodos_por_tipo(
    inicio1: date,
    inicio2: Optional[date],
    tipo_label: str,
) -> Tuple[Optional[str], List[Tuple[date, date]]]:
    """Retorna (codigo, periodos) ou (None, []) se inválido."""
    tipos_map = {
        "30 dias corridos": "30",
        "15 + 15 dias": "15+15",
        "20 + 10 dias": "20+10",
    }
    code = tipos_map.get(tipo_label)
    if not code:
        return None, []
    if code == "30":
        p1f, _ = _data_fim_e_retorno(inicio1, 30)
        return code, [(inicio1, p1f)]
    if inicio2 is None:
        return code, []
    if code == "15+15":
        p1f, _ = _data_fim_e_retorno(inicio1, 15)
        p2f, _ = _data_fim_e_retorno(inicio2, 15)
        return code, [(inicio1, p1f), (inicio2, p2f)]
    p1f, _ = _data_fim_e_retorno(inicio1, 20)
    p2f, _ = _data_fim_e_retorno(inicio2, 10)
    return code, [(inicio1, p1f), (inicio2, p2f)]


def validar_regras(
    inicio1: date,
    inicio2: Optional[date],
    tipo: str,
    colab: dict,
) -> Optional[str]:
    code, periodos = _montar_periodos_por_tipo(inicio1, inicio2, tipo)
    if not code:
        return "Tipo de férias inválido"
    if not periodos:
        return "Preencha a data do segundo período"
    return ferias.validar_solicitacao_ferias_fracionadas(colab, code, periodos)


def calcular_retorno(
    inicio1: date,
    inicio2: Optional[date],
    tipo: str,
) -> str:
    code, periodos = _montar_periodos_por_tipo(inicio1, inicio2, tipo)
    if not code or not periodos:
        return "—"
    if code == "30":
        _, r = _data_fim_e_retorno(periodos[0][0], 30)
        return f"{r:%d/%m/%Y}"
    if code == "15+15":
        _, r1 = _data_fim_e_retorno(periodos[0][0], 15)
        _, r2 = _data_fim_e_retorno(periodos[1][0], 15)
        return f"1º: {r1:%d/%m/%Y} | 2º: {r2:%d/%m/%Y}"
    _, r1 = _data_fim_e_retorno(periodos[0][0], 20)
    _, r2 = _data_fim_e_retorno(periodos[1][0], 10)
    return f"1º: {r1:%d/%m/%Y} | 2º: {r2:%d/%m/%Y}"


def _enviar_ferias_modo_form(
    colab_id: int,
    colab: dict,
    tipo_codigo: str,
    periodos: List[Tuple[date, date]],
) -> None:
    """Mesmo fluxo de envio do render_formulario (validação, escala, DB, calendário)."""
    flag_excesso, flag_conflito = obter_flags_nova_solicitacao_escala(
        colab, periodos
    )
    if flag_excesso:
        st.error("Limite de colaboradores por função excedido")
        st.stop()
    if flag_conflito:
        st.warning("Conflito de período detectado")

    if not _inserir_solicitacao_ferias(colab_id, colab, periodos):
        st.stop()
        return

    periodos_dicts = [
        {"inicio": str(di), "fim": str(df)} for di, df in periodos
    ]
    salvar_solicitacao(colab_id, tipo_codigo, periodos_dicts)

    nome_colaborador = colab["nome"]
    for p in periodos_dicts:
        if not periodo_valido(p["inicio"], p["fim"]):
            st.warning("Erro ao enviar para o Google Calendar")
            continue
        try:
            criar_evento(
                nome_colaborador,
                p["inicio"],
                p["fim"],
                conflito=flag_conflito,
                excesso_funcao=flag_excesso,
            )
        except Exception:
            st.warning("Erro ao enviar para o Google Calendar")

    try:
        st.cache_data.clear()
    except Exception:
        pass

    st.success("Solicitação enviada com sucesso!")
    time.sleep(1)
    st.rerun()


def render_modo_form() -> None:
    """Tela enxuta para ?modo=form&token=…"""
    st.markdown(
        """
    <style>
    .block-container {
        max-width: 500px;
        margin: auto;
    }
    h1, h2, h3 {
        text-align: center;
    }
    .stButton>button {
        width: 100%;
        height: 50px;
        font-size: 16px;
        border-radius: 10px;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    token = _qp_first("token", "")
    if not token:
        st.error("Acesso inválido")
        st.stop()

    colab = buscar_colaborador_por_token(token)
    if not colab:
        st.error("Token inválido")
        st.stop()

    colab_id = int(colab["id"])

    st.markdown("## 📅 Solicitação de Férias")
    st.markdown(f"### 👤 {colab['nome']}")
    st.caption(f"Função: {colab.get('funcao', '')} · Dias: {colab.get('dias_disponiveis', 30)}")

    tipo = st.radio(
        "Como deseja dividir suas férias?",
        [
            "30 dias corridos",
            "15 + 15 dias",
            "20 + 10 dias",
        ],
        key="form_modo_tipo",
    )

    inicio1 = st.date_input("📆 Data de início", key="form_inicio1")

    inicio2: Optional[date] = None
    if tipo != "30 dias corridos":
        inicio2 = st.date_input("📆 Segundo período", value=None, key="form_inicio2")

    erro = validar_regras(inicio1, inicio2, tipo, colab)
    if erro:
        st.error(erro)
    else:
        rtxt = calcular_retorno(inicio1, inicio2, tipo)
        st.info(f"Retorno previsto: {rtxt}")

    if st.button("✅ Enviar solicitação", key="form_enviar"):
        e2 = validar_regras(inicio1, inicio2, tipo, colab)
        if e2:
            st.error(e2)
            st.stop()
        code, periodos = _montar_periodos_por_tipo(inicio1, inicio2, tipo)
        if not code or not periodos:
            st.error("Preencha as datas corretamente")
            st.stop()
        _enviar_ferias_modo_form(colab_id, colab, code, periodos)


init_db()

try:
    seed_colaboradores_if_needed()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

if "_app_boot_logged" not in st.session_state:
    st.session_state["_app_boot_logged"] = True
    print("App iniciado")
    print("Banco:", DB_PATH)

if MODO_IS_FORM:
    render_modo_form()
    st.stop()

st.info(f"Banco em uso: {DB_PATH}")

st.sidebar.caption("Colaboradores: data/colaboradores.json (sem Excel em runtime)")


def render_formulario(colab_id):
    row = buscar_colaborador(colab_id)
    colab = colaborador_row_para_dict(row)

    if not colab:
        st.error("Colaborador não encontrado")
        st.stop()

    st.title("Solicitação de Férias")
    st.subheader(f"Olá, {colab['nome']}")

    st.write(f"Função: {colab['funcao']}")
    st.write(f"Dias disponíveis: {colab['dias_disponiveis']}")

    tipo_ferias = st.radio(
        "Tipo de férias",
        [
            "30 dias",
            "15 + 15 dias",
            "20 + 10 dias",
        ],
        key=f"tipo_ferias_{colab_id}",
    )

    tipo_map = {
        "30 dias": "30",
        "15 + 15 dias": "15+15",
        "20 + 10 dias": "20+10",
    }
    tipo_codigo = tipo_map[tipo_ferias]

    data_inicio: Optional[date] = None
    p1i: Optional[date] = None
    p2i: Optional[date] = None

    if tipo_codigo == "30":
        data_inicio = st.date_input("Data início", key=f"30_di_{colab_id}")
        data_fim, data_retorno = _data_fim_e_retorno(data_inicio, 30)
        st.write(f"Data fim: {data_fim}")
        st.write(f"Retorno ao trabalho: {data_retorno}")

    elif tipo_codigo == "15+15":
        st.markdown("### 📅 Período 1")
        p1i = st.date_input(
            "Data início 1",
            key=f"1515_i1_{colab_id}",
            value=None,
        )
        if p1i is not None:
            p1_fim, p1_ret = _data_fim_e_retorno(p1i, 15)
            st.write(f"Data fim: {p1_fim}")
            st.write(f"Retorno ao trabalho: {p1_ret}")

        show_p2 = p1i is not None

        if show_p2:
            st.markdown("### 📅 Período 2")
            p2i = st.date_input(
                "Data início 2",
                key=f"1515_i2_{colab_id}",
                value=None,
            )
            if p2i is not None:
                p2_fim, p2_ret = _data_fim_e_retorno(p2i, 15)
                st.write(f"Data fim: {p2_fim}")
                st.write(f"Retorno ao trabalho: {p2_ret}")

    else:
        st.markdown("### 📅 Período 1 (20 dias)")
        p1i = st.date_input("Data início 1", key=f"2010_i1_{colab_id}")
        p1_fim, p1_ret = _data_fim_e_retorno(p1i, 20)
        st.write(f"Data fim: {p1_fim}")
        st.write(f"Retorno ao trabalho: {p1_ret}")

        st.markdown("### 📅 Período 2 (10 dias)")
        p2i = st.date_input("Data início 2", key=f"2010_i2_{colab_id}")
        p2_fim, p2_ret = _data_fim_e_retorno(p2i, 10)
        st.write(f"Data fim: {p2_fim}")
        st.write(f"Retorno ao trabalho: {p2_ret}")

    if st.button("Enviar solicitação", key=f"enviar_{colab_id}"):
        periodos: List[Tuple[date, date]] = []

        if tipo_codigo == "30":
            df, _ = _data_fim_e_retorno(data_inicio, 30)
            periodos = [(data_inicio, df)]

        elif tipo_codigo == "15+15":
            if p1i is None:
                st.error("Preencha a data de início do período 1")
                return
            if p2i is None:
                st.error("Preencha a data de início do período 2")
                return
            p1f, _ = _data_fim_e_retorno(p1i, 15)
            p2f, _ = _data_fim_e_retorno(p2i, 15)
            periodos = [(p1i, p1f), (p2i, p2f)]

        else:
            p1f, _ = _data_fim_e_retorno(p1i, 20)
            p2f, _ = _data_fim_e_retorno(p2i, 10)
            periodos = [(p1i, p1f), (p2i, p2f)]

        erro = ferias.validar_solicitacao_ferias_fracionadas(
            colab, tipo_codigo, periodos
        )

        if erro:
            st.error(erro)
            return

        flag_excesso, flag_conflito = obter_flags_nova_solicitacao_escala(
            colab, periodos
        )
        if flag_excesso:
            st.error("Limite de colaboradores por função excedido")
            st.stop()
        if flag_conflito:
            st.warning("Conflito de período detectado")

        if not _inserir_solicitacao_ferias(colab_id, colab, periodos):
            return

        periodos_dicts = [
            {"inicio": str(di), "fim": str(df)} for di, df in periodos
        ]
        salvar_solicitacao(colab_id, tipo_codigo, periodos_dicts)

        nome_colaborador = colab["nome"]
        calendar_ok = True
        for p in periodos_dicts:
            if not periodo_valido(p["inicio"], p["fim"]):
                st.warning(
                    "Período com datas inválidas para o Google Calendar "
                    f"({p.get('inicio')} – {p.get('fim')}); evento não enviado."
                )
                calendar_ok = False
                continue
            try:
                criar_evento(
                    nome_colaborador,
                    p["inicio"],
                    p["fim"],
                    conflito=flag_conflito,
                    excesso_funcao=flag_excesso,
                )
            except Exception as e:
                st.warning(f"Erro ao enviar para Google Calendar: {e}")
                calendar_ok = False

        if calendar_ok:
            st.success("Solicitação registrada e enviada ao Google Calendar")
        else:
            st.success("Solicitação registrada com sucesso")


# =========================
# APP
# =========================

try:
    # cria senha apenas se não existir
    if not admin_tem_senha():
        definir_senha_admin("123456")

    token = _qp_first("token", "")

    # =========================
    # FUNCIONÁRIO (link legado ?token=… sem modo=form)
    # =========================
    if token and not MODO_IS_FORM:
        colab_id = validar_token(token)

        if not colab_id:
            st.error("Token inválido")
            st.stop()

        render_formulario(colab_id)
        st.stop()

    # =========================
    # ADMIN LOGIN
    # =========================
    if "admin_autenticado" not in st.session_state:
        st.session_state["admin_autenticado"] = False

    if not st.session_state["admin_autenticado"]:
        st.title("Painel Administrativo")

        senha = st.text_input("Senha", type="password")

        if st.button("Entrar"):
            if verificar_senha_admin(senha):
                st.session_state["admin_autenticado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta")

        st.stop()

    # =========================
    # ADMIN LOGADO
    # =========================
    st.title("Painel Administrativo")

    if st.sidebar.button("Sair"):
        st.session_state["admin_autenticado"] = False
        st.rerun()

    if "perfil_usuario" not in st.session_state:
        st.session_state["perfil_usuario"] = "RH"

    st.sidebar.selectbox(
        "Perfil",
        ["RH", "Gestor"],
        key="perfil_usuario",
    )
    perfil = st.session_state["perfil_usuario"]

    tab1, tab2, tab3 = st.tabs(["Colaboradores", "Tokens", "Dashboard"])

    # =========================
    # COLABORADORES
    # =========================
    with tab1:
        st.subheader("Adicionar colaborador")

        nome = st.text_input("Nome", key="admin_colab_nome")
        funcao = st.text_input("Função", key="admin_colab_funcao")
        dias = st.number_input(
            "Dias disponíveis", 0, 30, 30, key="admin_colab_dias"
        )

        if st.button("Salvar", key="admin_btn_salvar_colab"):
            if not nome.strip():
                st.error("Nome obrigatório")
            else:
                criar_colaborador(nome, funcao, dias)
                st.success("Salvo com sucesso")
                st.rerun()

        st.subheader("Colaboradores cadastrados")

        colaboradores = listar_colaboradores()

        if colaboradores:
            st.dataframe(
                [
                    {"id": r[0], "nome": r[1], "funcao": r[2], "dias": r[3]}
                    for r in colaboradores
                ]
            )
        else:
            st.warning("Nenhum colaborador cadastrado")

    # =========================
    # TOKENS
    # =========================
    with tab2:
        st.subheader("Gerar Token")

        colaboradores = listar_colaboradores()

        if colaboradores:
            nomes = [c[1] for c in colaboradores]
            nome_sel = st.selectbox("Colaborador", nomes)

            colab_id = next(c[0] for c in colaboradores if c[1] == nome_sel)

            if st.button("Gerar", key="admin_btn_gerar_token"):
                t = gerar_token(colab_id)
                link = gerar_link_form(t, ip)
                st.code(link)
                st.caption("Link com tela de formulário (recomendado: rede local).")
        else:
            st.warning("Cadastre colaboradores primeiro")

    # =========================
    # DASHBOARD
    # =========================
    with tab3:
        st.info("🔎 Verde = OK | Amarelo = Conflito | Vermelho = Excesso")

        hoje = date.today()

        if hoje.month >= 2:
            ano_inicio = hoje.year
            ano_fim = hoje.year + 1
        else:
            ano_inicio = hoje.year - 1
            ano_fim = hoje.year

        st.markdown(
            f"<h2 style='text-align:center;'>📅 Programação de Férias</h2>"
            f"<h4 style='text-align:center;'>Ano Fiscal {ano_inicio}/{ano_fim}</h4>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        dados = listar_solicitacoes_com_status()
        sem_programacao = listar_colaboradores_sem_programacao()
        total_sem = len(sem_programacao)

        if not dados:
            st.warning("Nenhuma solicitação registrada")
            df = pd.DataFrame(
                columns=[
                    "id",
                    "nome",
                    "funcao",
                    "tipo",
                    "data_inicio_1",
                    "data_fim_1",
                    "data_inicio_2",
                    "data_fim_2",
                    "status",
                    "aprovado_por",
                    "data_aprovacao",
                    "criado_em",
                ]
            )
        else:
            df = pd.DataFrame(dados)

        df.columns = [str(c).strip().lower() for c in df.columns]

        if "status" not in df.columns:
            df["status"] = "PENDENTE"
        df["status"] = df["status"].fillna("PENDENTE")

        for col in [
            "data_inicio_1",
            "data_fim_1",
            "data_inicio_2",
            "data_fim_2",
            "criado_em",
            "data_aprovacao",
        ]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        df = aplicar_flags_escala(df)

        df["indicador"] = df.apply(
            lambda row: (
                "🔴 Excesso"
                if row["excesso_funcao"]
                else "🟡 Conflito" if row["conflito"] else "🟢 OK"
            ),
            axis=1,
        )

        df_alerta = df[df["excesso_funcao"] == True]
        if not df_alerta.empty:
            st.error("⚠️ Existe conflito crítico de escala")

        insight = gerar_insights(df)
        pico = insight["pico_mes"]
        if pico is not None:
            st.info(
                f"Pico de férias no mês: {_MESES_PT.get(int(pico), pico)}"
            )
        else:
            st.info("Pico de férias no mês: —")

        filtro_status = st.selectbox(
            "Status",
            ["Todos", "PENDENTE", "APROVADO", "REJEITADO"],
            key="dash_filtro_status",
        )

        df_filt = df.copy()
        if filtro_status != "Todos":
            df_filt = df_filt[df_filt["status"] == filtro_status]

        total = len(df_filt)
        colaboradores = (
            df_filt["nome"].nunique() if "nome" in df_filt.columns else total
        )

        ts = pd.Timestamp.today().normalize()
        em_p1 = (
            df_filt["data_inicio_1"].notna()
            & df_filt["data_fim_1"].notna()
            & (df_filt["data_inicio_1"] <= ts)
            & (df_filt["data_fim_1"] >= ts)
        )
        em_p2 = pd.Series(False, index=df_filt.index)
        if "data_inicio_2" in df_filt.columns and "data_fim_2" in df_filt.columns:
            em_p2 = (
                df_filt["data_inicio_2"].notna()
                & df_filt["data_fim_2"].notna()
                & (df_filt["data_inicio_2"] <= ts)
                & (df_filt["data_fim_2"] >= ts)
            )
        em_andamento = df_filt[em_p1 | em_p2]

        col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)

        col_k1.metric("Total solicitações", total)
        col_k2.metric("Colaboradores", colaboradores)
        col_k3.metric("Em férias hoje", len(em_andamento))
        col_k4.metric("Conflitos críticos", len(df_alerta))
        col_k5.metric("Pendentes de programação", total_sem)

        if total_sem > 0:
            st.warning(
                f"{total_sem} colaboradores ainda não programaram férias"
            )

        st.markdown("---")

        st.markdown("### Análises visuais")

        df_plot = df_filt.copy()
        df_plot["inicio"] = pd.to_datetime(
            df_plot["data_inicio_1"], errors="coerce"
        )
        df_plot["mes"] = df_plot["inicio"].dt.month
        df_plot["mes_nome"] = df_plot["inicio"].dt.strftime("%b")

        df_chart = df_plot.dropna(subset=["inicio"])

        if len(df_chart) > 0:
            graf_mes = (
                df_chart.groupby(["mes", "mes_nome"])
                .size()
                .reset_index(name="quantidade")
                .sort_values("mes")
            )
            fig1 = px.bar(
                graf_mes,
                x="mes_nome",
                y="quantidade",
                title="Férias por mês",
                text_auto=True,
            )
            st.plotly_chart(fig1, use_container_width=True)

            df_func = df_chart.copy()
            df_func["funcao"] = df_func["funcao"].fillna("").replace(
                "", "(Sem função)"
            )
            graf_funcao = (
                df_func.groupby("funcao").size().reset_index(name="qtd")
            )
            fig2 = px.pie(
                graf_funcao,
                names="funcao",
                values="qtd",
                title="Distribuição por função",
            )
            st.plotly_chart(fig2, use_container_width=True)

            graf_tempo = df_chart.sort_values("inicio").reset_index(
                drop=True
            )
            fig3 = px.line(
                graf_tempo,
                x="inicio",
                y=graf_tempo.index,
                title="Linha do tempo de férias",
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem dados de data de início para exibir os gráficos.")

        st.markdown("### Calendário de férias")

        def _cor_calendario_escala(row) -> str:
            color = "#28a745"
            if row.get("excesso_funcao"):
                color = "#ff4d4d"
            elif row.get("conflito"):
                color = "#ffc107"
            return color

        events = []
        for _, row in df_filt.iterrows():
            nome = row.get("nome", "")
            funcao = row.get("funcao", "") or ""
            titulo = f'{nome} ({funcao})'
            cor = _cor_calendario_escala(row)
            if pd.notna(row.get("data_inicio_1")):
                fim_1 = (
                    row["data_fim_1"]
                    if pd.notna(row.get("data_fim_1"))
                    else row["data_inicio_1"]
                )
                events.append(
                    {
                        "title": titulo,
                        "start": str(pd.Timestamp(row["data_inicio_1"]).date()),
                        "end": str(pd.Timestamp(fim_1).date()),
                        "color": cor,
                    }
                )
            if pd.notna(row.get("data_inicio_2")):
                fim_2 = (
                    row["data_fim_2"]
                    if pd.notna(row.get("data_fim_2"))
                    else row["data_inicio_2"]
                )
                events.append(
                    {
                        "title": titulo,
                        "start": str(pd.Timestamp(row["data_inicio_2"]).date()),
                        "end": str(pd.Timestamp(fim_2).date()),
                        "color": cor,
                    }
                )
        if events:
            calendar(
                events=events,
                options={
                    "initialView": "dayGridMonth",
                    "locale": "pt-br",
                },
                key="calendario_ferias",
            )
        else:
            st.info("Sem períodos de férias com datas para exibir no calendário.")

        st.markdown("---")

        def marcar_linha(row):
            if row.get("excesso_funcao"):
                return ["background-color: #ff4d4d"] * len(row)
            if row.get("conflito"):
                return ["background-color: #fff3cd"] * len(row)
            stt = str(row.get("Status", "") or "").upper()
            if stt == "APROVADO":
                return ["background-color: #d4edda"] * len(row)
            if stt == "REJEITADO":
                return ["background-color: #f8d7da"] * len(row)
            if stt == "PENDENTE":
                return ["background-color: #fff9c4"] * len(row)
            return [""] * len(row)

        df_view = df_filt.copy()

        df_view = df_view.rename(
            columns={
                "id": "ID",
                "nome": "Colaborador",
                "funcao": "Função",
                "tipo": "Tipo",
                "data_inicio_1": "Início",
                "data_fim_1": "Fim",
                "data_inicio_2": "Início 2",
                "data_fim_2": "Fim 2",
                "status": "Status",
                "indicador": "Indicador",
                "aprovado_por": "Aprovado por",
                "data_aprovacao": "Data aprovação",
                "criado_em": "Registrado",
            }
        )

        for col in [
            "Início",
            "Fim",
            "Início 2",
            "Fim 2",
            "Registrado",
            "Data aprovação",
        ]:
            if col in df_view.columns:
                df_view[col] = pd.to_datetime(
                    df_view[col], errors="coerce"
                ).dt.strftime("%d/%m/%Y")

        if "Início" in df_view.columns:
            df_view = df_view.sort_values(
                by="Início",
                na_position="last",
                key=lambda s: pd.to_datetime(
                    s, dayfirst=True, errors="coerce"
                ),
            )

        styled = df_view.style.apply(marcar_linha, axis=1).hide(
            axis="columns",
            subset=["conflito", "excesso_funcao"],
        )

        st.dataframe(styled, use_container_width=True)

        st.markdown("---")
        st.markdown("## ⚠️ Colaboradores sem programação de férias")
        if not sem_programacao:
            st.success("Todos os colaboradores já realizaram sua programação ✔")
        else:
            lista_sem = [
                {"ID": c[0], "Nome": c[1]} for c in sem_programacao
            ]
            st.dataframe(lista_sem, use_container_width=True)

        pendentes = df[df["status"] == "PENDENTE"]
        if perfil == "RH" and len(pendentes) > 0:
            st.markdown("### Ações de aprovação (pendentes)")
            for _, r in pendentes.iterrows():
                sid = int(r["id"])
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.caption(f"#{sid} — {r['nome']} ({r.get('tipo', '')})")
                quem = st.session_state.get("perfil_usuario", "RH")
                if c2.button("✔ Aprovar", key=f"aprov_{sid}"):
                    atualizar_status_solicitacao(sid, "APROVADO", quem)
                    st.rerun()
                if c3.button("✖ Rejeitar", key=f"rej_{sid}"):
                    atualizar_status_solicitacao(sid, "REJEITADO", quem)
                    st.rerun()

        buf = io.BytesIO()
        df_export = df_view.drop(
            columns=["conflito", "excesso_funcao"],
            errors="ignore",
        )
        df_export.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button(
            label="📥 Exportar Excel",
            data=buf,
            file_name="relatorio_ferias.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

except Exception as e:
    st.error(f"Erro geral: {e}")