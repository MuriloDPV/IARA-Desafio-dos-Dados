"""Painel web ao vivo — mostra mensagem recebida, nível INAF e caminho.

Rodar: python painel.py  (abre em http://localhost:8000)
Lê o mesmo SQLite que o bot escreve; a página faz polling a cada 2s.
"""

import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import estado

app = FastAPI(title="Motor de Letramento Digital — Painel")

PAGINA = (Path(__file__).parent / "painel.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def pagina():
    return PAGINA


@app.get("/api/eventos")
def eventos():
    return JSONResponse(estado.ultimos_eventos(limite=25))


@app.get("/api/atendimentos")
def atendimentos():
    return JSONResponse(estado.atendimentos_agrupados(limite=10))


@app.get("/api/estatisticas")
def estatisticas():
    """Resumo agregado (contagens por caminho e por tarefa), sem dado pessoal."""
    return JSONResponse(estado.estatisticas_agregadas())


@app.get("/api/versao")
def versao():
    """Versão atual do projeto, lida do VERSION.json na raiz do repositório."""
    caminho = Path(__file__).parent / "VERSION.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return JSONResponse(dados)


if __name__ == "__main__":
    estado.inicializa()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
