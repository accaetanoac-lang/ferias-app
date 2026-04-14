from datetime import datetime

def validar_regras(data_inicio):
    # Regra de safra (16/07 a 31/08)
    if (data_inicio.month == 7 and data_inicio.day >= 16) or data_inicio.month == 8:
        return False, "Período de safra - férias bloqueadas"

    return True, "OK"
