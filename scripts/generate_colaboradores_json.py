"""
Gera data/colaboradores.json a partir de data/base.xlsx (uso offline / CI).
Requer: pandas, openpyxl
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")
XLSX = os.path.join(DATA, "base.xlsx")
OUT = os.path.join(DATA, "colaboradores.json")


def main():
    if not os.path.isfile(XLSX):
        print("ERRO: Arquivo data/base.xlsx não encontrado", file=sys.stderr)
        sys.exit(1)

    import pandas as pd

    xls = pd.ExcelFile(XLSX)
    print("Abas disponíveis:", xls.sheet_names)

    sheet_escolhida = None
    for nome in xls.sheet_names:
        n = str(nome).lower()
        if any(x in n for x in ["controle", "ferias", "colaborador"]):
            sheet_escolhida = nome
            break

    if not sheet_escolhida:
        raise Exception(
            f"Nenhuma aba válida encontrada. Abas disponíveis: {xls.sheet_names}"
        )

    print("Usando aba:", sheet_escolhida)

    df_raw = pd.read_excel(xls, sheet_name=sheet_escolhida, header=None)
    print("Preview bruto:")
    print(df_raw.head(10))

    header_row = None
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        if any(x in row_str for x in ["nome", "funcionario", "colaborador"]):
            header_row = i
            break

    if header_row is None:
        raise Exception("Não foi possível identificar a linha de cabeçalho")

    print("Header detectado na linha:", header_row)

    df = pd.read_excel(xls, sheet_name=sheet_escolhida, header=header_row)
    print("Colunas reais:", list(df.columns))
    print(df.head())

    col_nome = None
    for c in df.columns:
        nome_col = str(c).lower()
        if any(x in nome_col for x in ["nome", "funcionario", "colaborador"]):
            col_nome = c
            break

    if not col_nome:
        raise Exception(
            f"Nenhuma coluna de nome encontrada. Colunas disponíveis: {list(df.columns)}"
        )

    out_list = []
    count = 0

    for val in df[col_nome]:
        if pd.isna(val):
            continue

        nome = str(val).strip()
        if not nome:
            continue

        out_list.append({"nome": nome, "funcao": "", "dias": 30})
        count += 1

    if count == 0:
        raise Exception("Nenhum colaborador encontrado no Excel")

    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out_list, f, ensure_ascii=False, indent=2)

    print(f"{count} colaboradores gerados")
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
