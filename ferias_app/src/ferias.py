from datetime import date

MSG_SAFRA = "Período de safra, proibido férias"


def periodo_proibido_intervalo(inicio, fim):
    ano = inicio.year

    periodos = [
        (date(ano, 4, 15), date(ano, 5, 30)),
        (date(ano, 7, 15), date(ano, 8, 30)),
    ]

    for p_inicio, p_fim in periodos:
        if inicio <= p_fim and fim >= p_inicio:
            return True

    return False


def validar_regras(data_inicio):
    if periodo_proibido_intervalo(data_inicio, data_inicio):
        return False, MSG_SAFRA

    return True, "OK"
