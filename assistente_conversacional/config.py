"""Configuração lida das variáveis de ambiente (seção 8 do documento do serviço)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mackai:mackai@localhost:5432/conversas_db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

ORQUESTRADOR_URL = os.getenv("ORQUESTRADOR_URL", "http://localhost:8001")
ORQUESTRADOR_TIMEOUT_S = float(os.getenv("ORQUESTRADOR_TIMEOUT_S", "60"))
STATUS_TIMEOUT_S = float(os.getenv("STATUS_TIMEOUT_S", "5"))

CHAT_LIMIT_PER_USER = int(os.getenv("CHAT_LIMIT_PER_USER", "10"))
CHAT_LIMIT_GLOBAL = int(os.getenv("CHAT_LIMIT_GLOBAL", "60"))
SESSION_LIMIT_PER_IP = int(os.getenv("SESSION_LIMIT_PER_IP", "10"))

MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "20000"))
HISTORY_MAX_MESSAGES = 10
HISTORY_MAX_CHARS = 4000
TITLE_MAX_CHARS = 60

# Vazio = sem CORS (front e API na mesma origem). Preencha só se outro módulo
# chamar esta API direto do navegador, em outra origem. Separe por vírgula.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend_dist"))
