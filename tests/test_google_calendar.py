"""Testes da integração Google Calendar (sem rede nem credentials reais)."""
import unittest
from unittest.mock import MagicMock, patch

from google_calendar import periodo_valido, criar_evento


class TestPeriodoValido(unittest.TestCase):
    def test_valido(self):
        self.assertTrue(periodo_valido("2026-01-01", "2026-01-31"))

    def test_invalido_ordem(self):
        self.assertFalse(periodo_valido("2026-02-01", "2026-01-01"))

    def test_formato_errado(self):
        self.assertFalse(periodo_valido("01-01-2026", "2026-01-31"))


class TestCriarEvento(unittest.TestCase):
    @patch("google_calendar.get_service")
    def test_insere_evento_e_retorna_event_id(self, mock_get_service):
        mock_events_api = MagicMock()
        mock_events_api.insert.return_value.execute.return_value = {
            "id": "evt_abc123",
            "htmlLink": "https://calendar.google.com/event?eid=x",
        }
        mock_svc = MagicMock()
        mock_svc.events.return_value = mock_events_api
        mock_get_service.return_value = mock_svc

        event_id = criar_evento("Maria", "2026-06-01", "2026-06-15")
        self.assertEqual(event_id, "evt_abc123")

        mock_events_api.insert.assert_called_once()
        body = mock_events_api.insert.call_args.kwargs["body"]
        self.assertEqual(body["summary"], "Férias - Maria (15 dias)")
        self.assertIn("Colaborador: Maria", body["description"])
        self.assertIn("2026-06-01 até 2026-06-15", body["description"])
        self.assertIn("Duração: 15 dias", body["description"])
        self.assertEqual(body["colorId"], "2")
        self.assertEqual(body["start"]["date"], "2026-06-01")
        # fim inclusivo 15/06 → exclusivo 16/06 na API
        self.assertEqual(body["end"]["date"], "2026-06-16")

    @patch("google_calendar.get_service")
    def test_cor_amarela_conflito(self, mock_get_service):
        mock_events_api = MagicMock()
        mock_events_api.insert.return_value.execute.return_value = {"id": "e1"}
        mock_svc = MagicMock()
        mock_svc.events.return_value = mock_events_api
        mock_get_service.return_value = mock_svc

        criar_evento("X", "2026-01-01", "2026-01-05", conflito=True)
        body = mock_events_api.insert.call_args.kwargs["body"]
        self.assertEqual(body["colorId"], "5")

    @patch("google_calendar.get_service")
    def test_cor_vermelha_excesso(self, mock_get_service):
        mock_events_api = MagicMock()
        mock_events_api.insert.return_value.execute.return_value = {"id": "e2"}
        mock_svc = MagicMock()
        mock_svc.events.return_value = mock_events_api
        mock_get_service.return_value = mock_svc

        criar_evento(
            "Y", "2026-02-01", "2026-02-10", conflito=True, excesso_funcao=True
        )
        body = mock_events_api.insert.call_args.kwargs["body"]
        self.assertEqual(body["colorId"], "11")

    def test_periodo_invalido(self):
        with self.assertRaises(ValueError):
            criar_evento("João", "2026-01-10", "2026-01-01")


if __name__ == "__main__":
    unittest.main()
