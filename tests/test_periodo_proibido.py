"""Regras de safra por intervalo (15/04–30/05 e 15/07–30/08)."""
from datetime import date

import pytest

from ferias import MSG_SAFRA, periodo_proibido_intervalo, validar_ferias_sem_saldo


@pytest.mark.parametrize(
    "di,df,esperado_bloqueado",
    [
        (date(2026, 4, 20), date(2026, 4, 20), True),
        (date(2026, 5, 10), date(2026, 5, 10), True),
        (date(2026, 6, 1), date(2026, 6, 1), False),
        (date(2026, 7, 20), date(2026, 7, 20), True),
        (date(2026, 9, 1), date(2026, 9, 1), False),
    ],
)
def test_periodo_proibido_intervalo_casos_solicitados(di, df, esperado_bloqueado):
    assert periodo_proibido_intervalo(di, df) is esperado_bloqueado


def test_intervalo_que_cruza_apenas_final_da_safra():
    # 10–14/04 permitido; 10–20/04 bloqueia por sobreposição com 15/04–30/05
    assert periodo_proibido_intervalo(date(2026, 4, 10), date(2026, 4, 14)) is False
    assert periodo_proibido_intervalo(date(2026, 4, 10), date(2026, 4, 20)) is True


def test_validar_ferias_sem_saldo_retorna_mensagem_padrao():
    colab = {"dias_disponiveis": 30}
    err = validar_ferias_sem_saldo(
        colab, date(2026, 4, 20), date(2026, 5, 19)
    )  # 30 dias dentro da safra
    assert err == MSG_SAFRA
