"""Exporta o OpenAPI do serviço para contracts/ (rode depois de mudar o contrato).

    python scripts/exportar_openapi.py
"""

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("SESSION_SECRET", "x" * 32)  # só para importar o app; nada é assinado aqui

from assistente_conversacional.main import app  # noqa: E402

destino = RAIZ / "contracts" / "mackai-conversas.openapi.json"
destino.parent.mkdir(exist_ok=True)
destino.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"OpenAPI exportado para {destino.relative_to(RAIZ)}")
