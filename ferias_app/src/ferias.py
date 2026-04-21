from datetime import date

MSG_SAFRA = "Período de safra, proibido férias"


def is_periodo_safra(data):
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


def validar_regras(data_inicio):
    if is_periodo_safra(data_inicio):
        return False, MSG_SAFRA

    return True, "OK"
