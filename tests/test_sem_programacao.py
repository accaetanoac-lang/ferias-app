"""Contrato e integração leve: colaboradores sem nenhuma solicitação (LEFT JOIN)."""

from repository import listar_colaboradores_sem_programacao


def test_listar_colaboradores_sem_programacao_retorno():
    rows = listar_colaboradores_sem_programacao()
    assert isinstance(rows, list)
    for r in rows:
        assert len(r) == 2
        assert isinstance(r[0], int)
        assert isinstance(r[1], str)
