"""Detecção de sobreposição e excesso por função (período 1)."""

from typing import Any, Optional

import pandas as pd


def _status_ativo_para_escala(s: Any) -> bool:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return True
    t = str(s).strip().upper()
    if t == "":
        return True
    return t in ("PENDENTE", "APROVADO")


def aplicar_flags_escala(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche colunas conflito e excesso_funcao (mesma função, período 1)."""
    df = df.copy()
    if "status" not in df.columns:
        df["status"] = "PENDENTE"
    df["conflito"] = False
    df["excesso_funcao"] = False
    if "funcao" not in df.columns:
        df["funcao"] = ""

    for i, row_i in df.iterrows():
        if not _status_ativo_para_escala(row_i.get("status")):
            continue
        for j, row_j in df.iterrows():
            if i == j:
                continue
            if not _status_ativo_para_escala(row_j.get("status")):
                continue
            if str(row_i["funcao"] or "") != str(row_j["funcao"] or ""):
                continue
            if (
                pd.isna(row_i["data_inicio_1"])
                or pd.isna(row_i["data_fim_1"])
                or pd.isna(row_j["data_inicio_1"])
                or pd.isna(row_j["data_fim_1"])
            ):
                continue
            if (
                row_i["data_inicio_1"] <= row_j["data_fim_1"]
                and row_i["data_fim_1"] >= row_j["data_inicio_1"]
            ):
                df.at[i, "conflito"] = True

    for funcao in df["funcao"].fillna("").unique():
        df_func = df[
            (df["funcao"] == funcao)
            & (df["status"].map(_status_ativo_para_escala))
        ]
        if len(df_func) == 0:
            continue

        for i, row in df_func.iterrows():
            if pd.isna(row["data_inicio_1"]) or pd.isna(row["data_fim_1"]):
                continue
            simultaneos = df_func[
                (df_func["data_inicio_1"] <= row["data_fim_1"])
                & (df_func["data_fim_1"] >= row["data_inicio_1"])
            ]
            if len(simultaneos) > 2:
                df.loc[simultaneos.index, "excesso_funcao"] = True

    return df


def obter_flags_nova_solicitacao_escala(
    colab: dict,
    periodos: list,
) -> tuple[bool, bool]:
    """
    Simula inclusão da nova solicitação (período 1) na base e retorna
    (excesso_funcao, conflito), considerando apenas PENDENTE/APROVADO.
    """
    from repository import listar_solicitacoes_com_status

    rows = listar_solicitacoes_com_status()
    if not rows:
        rows = []

    di, dfim = periodos[0]
    novo = {
        "id": -1,
        "nome": colab.get("nome", ""),
        "funcao": colab.get("funcao") or "",
        "tipo": "",
        "data_inicio_1": di,
        "data_fim_1": dfim,
        "data_inicio_2": None,
        "data_fim_2": None,
        "status": "PENDENTE",
        "aprovado_por": None,
        "data_aprovacao": None,
        "criado_em": None,
    }

    existentes = []
    for r in rows:
        st = r.get("status")
        if st is not None and str(st).strip().upper() == "REJEITADO":
            continue
        existentes.append(r)
    existentes.append(novo)

    dfp = pd.DataFrame(existentes)
    dfp.columns = [str(c).strip().lower() for c in dfp.columns]
    for col in ["data_inicio_1", "data_fim_1", "data_inicio_2", "data_fim_2"]:
        if col in dfp.columns:
            dfp[col] = pd.to_datetime(dfp[col], errors="coerce")

    dfp = aplicar_flags_escala(dfp)
    u = dfp.iloc[-1]
    return bool(u["excesso_funcao"]), bool(u["conflito"])


def validar_nova_solicitacao_escala(
    colab: dict,
    periodos: list,
) -> Optional[str]:
    """
    Retorna mensagem de erro se a nova solicitação gerar conflito ou excesso,
    considerando apenas solicitações PENDENTE/APROVADO.
    """
    ex, co = obter_flags_nova_solicitacao_escala(colab, periodos)
    if ex or co:
        return "Conflito de escala ou limite excedido"
    return None
