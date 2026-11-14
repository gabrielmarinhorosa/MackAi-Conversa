"""Configuração lida das variáveis de ambiente."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mackai:mackai@localhost:5432/conversas_db")

ORQUESTRADOR_URL = os.getenv("ORQUESTRADOR_URL", "http://localhost:8001")
ORQUESTRADOR_TIMEOUT_S = float(os.getenv("ORQUESTRADOR_TIMEOUT_S", "60"))
STATUS_TIMEOUT_S = float(os.getenv("STATUS_TIMEOUT_S", "5"))

# Módulo 1 (identidade e projetos). Os padrões são os endereços publicados pelo Módulo 1
# (docs/integracao-outros-modulos.md, release 0.5.0). Issuer, audiência e JWKS vêm daqui,
# nunca do token recebido.
MOD1_AUTH_URL = os.getenv("MOD1_AUTH_URL", "https://mod1-auth.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io")
MOD1_PROJECTS_URL = os.getenv(
    "MOD1_PROJECTS_URL", "https://mod1-projects.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io"
)
MOD1_JWT_ISSUER = os.getenv("MOD1_JWT_ISSUER", MOD1_AUTH_URL)
MOD1_JWT_AUDIENCE = os.getenv("MOD1_JWT_AUDIENCE", "engenharia-software-api")
MOD1_JWKS_URL = os.getenv("MOD1_JWKS_URL", MOD1_AUTH_URL + "/.well-known/jwks.json")
MOD1_TIMEOUT_S = float(os.getenv("MOD1_TIMEOUT_S", "5"))
# Por quanto tempo o resultado de GET /auth/me e de GET /projects/{id}/access/v2 é reaproveitado.
# Uma sessão revogada no Módulo 1 deixa de funcionar aqui em até esse tempo.
MOD1_CACHE_S = float(os.getenv("MOD1_CACHE_S", "60"))

CHAT_LIMIT_PER_USER = int(os.getenv("CHAT_LIMIT_PER_USER", "10"))
CHAT_LIMIT_GLOBAL = int(os.getenv("CHAT_LIMIT_GLOBAL", "60"))

MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "20000"))
HISTORY_MAX_MESSAGES = 10
HISTORY_MAX_CHARS = 4000
TITLE_MAX_CHARS = 60

# Vazio = sem CORS (front e API na mesma origem). Preencha com as origens exatas dos fronts
# de outros módulos que chamam esta API pelo navegador. Separe por vírgula.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend_dist"))
