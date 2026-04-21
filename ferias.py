import csv
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import holidays
import sqlite3

import repository

br_holidays = holidays.Brazil()

MSG_SAFRA = "Período de safra, proibido férias"


def is_periodo_safra(data: date) -> bool:
    ano = data.year

    inicio_1 = date(ano, 4, 1)
    fim_1 = date(ano, 5, 30)

    inicio_2 = date(ano, 7, 1)
    fim_2 = date(ano, 8, 30)

    if inicio_1 <= data <= fim_1:
        return True

    if inicio_2 <= data <= fim_2:
        return True

    return False


def is_feriado(data: date) -> bool:
    return data in br_holidays


def validar_data_inicio(data: date) -> Optional[str]:
    if is_periodo_safra(data):
        return MSG_SAFRA

    if data.weekday() == 4:
        return "Não é permitido iniciar férias na sexta-feira"

    if data.weekday() in [5, 6]:
        return "Não é permitido iniciar férias no fim de semana"

    if is_feriado(data):
        return "Não é permitido iniciar férias em feriado"

    if is_feriado(data + timedelta(days=1)):
        return "Não é permitido iniciar férias na véspera de feriado"

    return None


def get_colaborador(nome: Optional[str]) -> Optional[Dict[str, Any]]:
    if nome is None:
        return None
    row = repository.buscar_colaborador_por_nome(str(nome).strip())
    return repository.colaborador_row_para_dict(row)


def listar_colaboradores() -> List[Dict[str, Any]]:
    rows = repository.listar_colaboradores()
    out: List[Dict[str, Any]] = []
    for r in rows:
        cid, nome, funcao, _ = r
        out.append(
            {
                "id": cid,
                "nome": str(nome).strip(),
                "cargo": funcao,
            }
        )
    return out


def get_janela_ferias(data_ref: Optional[date] = None) -> Tuple[date, date]:
    if not data_ref:
        data_ref = date.today()

    ano = data_ref.year

    if data_ref.month >= 2:
        return date(ano, 2, 1), date(ano + 1, 1, 31)
    return date(ano - 1, 2, 1), date(ano, 1, 31)


def _dias_entre(data_inicio: date, data_fim: date) -> int:
    return (data_fim - data_inicio).days + 1


def validar_ferias_sem_saldo(
    _colab: Dict[str, Any], data_inicio: date, data_fim: date
) -> Optional[str]:
    """Regras de calendário, duração e janela — sem checagem de saldo (para fracionamento)."""
    dias = _dias_entre(data_inicio, data_fim)

    if data_fim < data_inicio:
        return "Data fim menor que início"

    if dias not in [10, 15, 20, 30]:
        return "Permitido apenas: 30, 20+10 ou 15+15"

    err_inicio = validar_data_inicio(data_inicio)
    if err_inicio:
        return err_inicio

    inicio_j, fim_j = get_janela_ferias()

    if data_inicio < inicio_j:
        return f"Início permitido após {inicio_j}"

    if data_inicio > fim_j:
        return f"Fora da janela ({inicio_j} a {fim_j})"

    return None


def validar_ferias(
    colab: Dict[str, Any], data_inicio: date, data_fim: date
) -> Optional[str]:
    err = validar_ferias_sem_saldo(colab, data_inicio, data_fim)
    if err:
        return err

    dias = _dias_entre(data_inicio, data_fim)
    saldo = int(colab.get("dias_disponiveis") or 0)
    if dias > saldo:
        return "Saldo insuficiente"

    return None


def periodos_se_sobrepõem(
    a: Tuple[date, date], b: Tuple[date, date]
) -> bool:
    ai, af = a
    bi, bf = b
    if af < ai or bf < bi:
        return False
    return ai <= bf and bi <= af


def validar_sem_sobreposicao_periodos(
    periodos: List[Tuple[date, date]],
) -> Optional[str]:
    for i in range(len(periodos)):
        for j in range(i + 1, len(periodos)):
            if periodos_se_sobrepõem(periodos[i], periodos[j]):
                return "Os períodos não podem se sobrepor"
    return None


def validar_solicitacao_ferias_fracionadas(
    colab: Dict[str, Any],
    tipo_codigo: str,
    periodos: List[Tuple[date, date]],
) -> Optional[str]:
    """
    tipo_codigo: "30", "15+15", "20+10"
    periodos: lista de (início, fim) em ordem.
    """
    saldo = int(colab.get("dias_disponiveis") or 0)

    if not periodos:
        return "Informe as datas dos períodos"

    for di, df in periodos:
        if di is None or df is None:
            return "Preencha todas as datas"

    if tipo_codigo == "30":
        esperados = {"periodos": 1, "dias": [30]}
    elif tipo_codigo == "15+15":
        esperados = {"periodos": 2, "dias": [15, 15]}
    elif tipo_codigo == "20+10":
        esperados = {"periodos": 2, "dias": [20, 10]}
    else:
        return "Tipo de férias inválido"

    if len(periodos) != esperados["periodos"]:
        return "Quantidade de períodos inválida para o tipo escolhido"

    total_dias = 0
    for idx, (di, df) in enumerate(periodos):
        err = validar_ferias_sem_saldo(colab, di, df)
        if err:
            return err

        d = _dias_entre(di, df)
        esperado = esperados["dias"][idx]
        total_dias += d
        if d != esperado:
            if tipo_codigo == "30":
                msg = "O período deve ter exatamente 30 dias"
            elif tipo_codigo == "15+15":
                msg = (
                    "O primeiro período deve ter exatamente 15 dias"
                    if idx == 0
                    else "O segundo período deve ter exatamente 15 dias"
                )
            else:
                msg = (
                    "O primeiro período deve ter exatamente 20 dias"
                    if idx == 0
                    else "O segundo período deve ter exatamente 10 dias"
                )
            return msg

    if total_dias > saldo:
        return "Saldo insuficiente"

    return validar_sem_sobreposicao_periodos(periodos)


def validar_conflito_funcao(
    conn: sqlite3.Connection, funcao: Any, data_inicio: date, data_fim: date
) -> Optional[str]:
    cursor = conn.execute(
        """
        SELECT COUNT(*)
        FROM ferias f
        INNER JOIN colaboradores c ON c.id = f.colaborador_id
        WHERE c.funcao = ?
        AND f.status IN ('PENDENTE','APROVADO')
        AND (
            date(f.data_inicio) <= date(?)
            AND date(f.data_fim) >= date(?)
        )
    """,
        (str(funcao), str(data_fim), str(data_inicio)),
    )

    total = cursor.fetchone()[0]

    if total >= 2:
        return "Já existem 2 colaboradores dessa função em férias nesse período"

    return None


def validar_solicitacao_ferias(
    nome: str, data_inicio: date, data_fim: date
) -> Tuple[bool, str]:
    colab = get_colaborador(nome)
    if not colab:
        return False, "Colaborador não encontrado"
    err = validar_ferias(colab, data_inicio, data_fim)
    if err:
        return False, err
    return True, "Solicitação válida."


def processar_arquivo_respostas() -> None:
    pasta = "respostas_forms"

    if not os.path.exists(pasta):
        os.makedirs(pasta)
        print(f"Pasta '{pasta}' criada. Coloque o CSV do Forms lá dentro.")
        return

    arquivos = [f for f in os.listdir(pasta) if f.endswith(".csv")]

    if not arquivos:
        print("Aguardando arquivo CSV na pasta 'respostas_forms'...")
        return

    resultados_finais: List[Dict[str, Any]] = []

    for arquivo in arquivos:
        print(f"\n--- Analisando: {arquivo} ---")
        caminho = os.path.join(pasta, arquivo)
        with open(caminho, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                nome = row.get("Nome")
                colab = get_colaborador(nome)
                if not colab:
                    msg = f"Funcionário '{nome}' não localizado no cadastro."
                    print(f"❌ {nome}: {msg}")
                    resultados_finais.append(
                        {
                            "Nome": nome,
                            "Status": "REPROVADO",
                            "Mensagem": msg,
                            "Arquivo_Origem": arquivo,
                        }
                    )
                    continue

                try:
                    inicio = datetime.strptime(
                        str(row["Inicio"]).strip(), "%d/%m/%Y"
                    ).date()
                except Exception:
                    msg = "Data de início inválida (use DD/MM/AAAA)."
                    print(f"❌ {nome}: {msg}")
                    resultados_finais.append(
                        {
                            "Nome": nome,
                            "Status": "REPROVADO",
                            "Mensagem": msg,
                            "Arquivo_Origem": arquivo,
                        }
                    )
                    continue

                dias_solicitados = row.get("Dias", None)
                try:
                    nd = (
                        int(dias_solicitados)
                        if dias_solicitados is not None
                        and str(dias_solicitados).strip() != ""
                        else 0
                    )
                except (TypeError, ValueError):
                    nd = 0
                if nd <= 0:
                    msg = "Quantidade de dias inválida."
                    print(f"❌ {nome}: {msg}")
                    resultados_finais.append(
                        {
                            "Nome": nome,
                            "Status": "REPROVADO",
                            "Mensagem": msg,
                            "Arquivo_Origem": arquivo,
                        }
                    )
                    continue

                data_fim = inicio + timedelta(days=nd - 1)
                erro = validar_ferias(colab, inicio, data_fim)
                if erro:
                    print(f"❌ {nome}: {erro}")
                    resultados_finais.append(
                        {
                            "Nome": nome,
                            "Status": "REPROVADO",
                            "Mensagem": erro,
                            "Arquivo_Origem": arquivo,
                        }
                    )
                else:
                    print(f"✅ {nome}: VALIDADO ({nd} dias)")
                    resultados_finais.append(
                        {
                            "Nome": nome,
                            "Status": "APROVADO",
                            "Mensagem": f"VALIDADO: {nd} dias",
                            "Arquivo_Origem": arquivo,
                        }
                    )

    if resultados_finais:
        out_path = "relatorio_final_ferias.csv"
        with open(out_path, "w", newline="", encoding="latin-1") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["Nome", "Status", "Mensagem", "Arquivo_Origem"],
                delimiter=";",
            )
            w.writeheader()
            w.writerows(resultados_finais)
        print(f"\n✅ Relatório '{out_path}' gerado com sucesso!")


if __name__ == "__main__":
    processar_arquivo_respostas()
