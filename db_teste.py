"""Isola o banco de eventos usado pelos testes.

Importar ESTE módulo antes de qualquer módulo do projeto (bot, painel,
estado) manda toda a persistência para eventos_teste.db. O eventos.db
que o painel ao vivo lê fica intacto, mesmo que o teste rode o pipeline
completo do bot.

Uso, como PRIMEIRO import do script de teste:

    import db_teste  # noqa: F401
"""

import os
from pathlib import Path

CAMINHO = Path(__file__).parent / "eventos_teste.db"

# setdefault: se alguém já apontou para outro arquivo (ex.: um runner de
# CI), respeita a escolha — só nunca deixa cair no eventos.db real.
os.environ.setdefault("EVENTOS_DB_PATH", str(CAMINHO))


def limpa():
    """Apaga o banco de teste e seus arquivos WAL, se existirem."""
    alvo = Path(os.environ["EVENTOS_DB_PATH"])
    for p in (alvo, Path(f"{alvo}-wal"), Path(f"{alvo}-shm")):
        p.unlink(missing_ok=True)
