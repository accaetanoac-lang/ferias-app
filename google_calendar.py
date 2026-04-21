"""
Integração com Google Calendar (OAuth instalado: credentials.json → token.json).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from google.auth.exceptions import GoogleAuthError
except ImportError:  # pragma: no cover
    GoogleAuthError = Exception  # type: ignore[misc, assignment]

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = _BASE_DIR / "credentials.json"
TOKEN_PATH = _BASE_DIR / "token.json"


class GoogleCalendarAuthError(Exception):
    """Falha de configuração ou autenticação do Google Calendar."""


def _parse_yyyy_mm_dd(s: str) -> Optional[date]:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def periodo_valido(inicio: str, fim: str) -> bool:
    """Datas inclusivas em YYYY-MM-DD; exige início <= fim."""
    di = _parse_yyyy_mm_dd(inicio)
    df = _parse_yyyy_mm_dd(fim)
    if di is None or df is None:
        return False
    return di <= df


def get_service():
    """
    Retorna o serviço Calendar v3.
    Usa credentials.json na pasta do projeto e persiste token.json automaticamente.
    """
    creds: Optional[Credentials] = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except GoogleAuthError as e:
                raise GoogleCalendarAuthError(
                    "Não foi possível renovar o token do Google Calendar. "
                    "Verifique a conexão ou apague token.json e garanta que "
                    "credentials.json é válido."
                ) from e
        else:
            if not CREDENTIALS_PATH.exists():
                raise GoogleCalendarAuthError(
                    "Arquivo credentials.json não encontrado na pasta do projeto. "
                    "Baixe as credenciais OAuth (Desktop app) no Google Cloud Console "
                    f"e salve como: {CREDENTIALS_PATH}"
                )
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
                creds = flow.run_local_server(port=0)
            except GoogleAuthError as e:
                raise GoogleCalendarAuthError(
                    "Falha na autenticação Google Calendar. Confira credentials.json, "
                    "escopos do projeto e se a API Calendar está habilitada."
                ) from e

        try:
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except OSError as e:
            raise GoogleCalendarAuthError(
                f"Não foi possível gravar token.json em {TOKEN_PATH}: {e}"
            ) from e

    try:
        return build("calendar", "v3", credentials=creds)
    except GoogleAuthError as e:
        raise GoogleCalendarAuthError(
            "Erro ao inicializar o cliente Google Calendar."
        ) from e


def criar_evento(
    nome: str,
    inicio: str,
    fim: str,
    *,
    conflito: bool = False,
    excesso_funcao: bool = False,
) -> str:
    """
    Cria evento de dia inteiro no calendário principal.
    ``inicio`` e ``fim`` são o primeiro e o último dia de férias (inclusivos), YYYY-MM-DD.
    A API do Google usa data de término exclusiva; o último dia útil é enviado como fim+1.
    Cores: excesso (11), conflito (5), ok (2).
    Retorna o ``id`` do evento na API.
    """
    if not periodo_valido(inicio, fim):
        raise ValueError(
            "Período inválido para o calendário: use YYYY-MM-DD com início <= fim."
        )

    d1 = datetime.fromisoformat(inicio.strip())
    d2 = datetime.fromisoformat(fim.strip())
    quantidade_dias = (d2 - d1).days + 1

    di = _parse_yyyy_mm_dd(inicio)
    df = _parse_yyyy_mm_dd(fim)
    assert di is not None and df is not None
    fim_exclusivo = df + timedelta(days=1)

    description = f"""
📅 Programação de Férias

👤 Colaborador: {nome}
📆 Período: {inicio} até {fim}
📊 Duração: {quantidade_dias} dias

⚙️ Gerado automaticamente pelo sistema de férias
"""

    if excesso_funcao:
        color_id = "11"
    elif conflito:
        color_id = "5"
    else:
        color_id = "2"

    service = get_service()
    body = {
        "summary": f"Férias - {nome} ({quantidade_dias} dias)",
        "description": description,
        "colorId": color_id,
        "start": {"date": di.isoformat()},
        "end": {"date": fim_exclusivo.isoformat()},
    }

    try:
        created = (
            service.events()
            .insert(calendarId="primary", body=body)
            .execute()
        )
    except HttpError as e:
        status = getattr(e.resp, "status", None) if e.resp is not None else None
        if status == 401:
            raise GoogleCalendarAuthError(
                "Google Calendar recusou a autenticação (401). "
                "Token pode estar revogado: apague token.json e autentique novamente."
            ) from e
        raise GoogleCalendarAuthError(
            f"Erro da API Google Calendar ao criar evento: {e}"
        ) from e
    except GoogleAuthError as e:
        raise GoogleCalendarAuthError(
            "Falha de autenticação ao criar evento no Google Calendar."
        ) from e

    return str(created.get("id") or "")
