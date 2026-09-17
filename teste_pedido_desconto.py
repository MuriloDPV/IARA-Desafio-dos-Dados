"""Regressão do bug relatado: pedido de desconto personalizado dentro do
fluxo TROCAR_PLANO não tinha tratamento nenhum. Dependendo de onde a
frase caía, o resultado variava — e nenhum deles reconhecia o pedido:

- "quero pagar menos mas continuar com os 20gb": "20gb" batia com o
  apelido do Plus (`acha_plano`/`acha_planos`) e o bot trocava o plano
  EM SILÊNCIO, sem nunca reconhecer o pedido de pagar menos.
- "eu quero um desconto": não bate com plano/número/pergunta, caía no
  "não achei esse plano" (DIRETO/INTERMEDIÁRIO) ou no "não entendi"
  genérico contando como confusão (GUIADO).
- "quero pagar 45": podia ser reclassificado por `_outra_tarefa_pedida`
  como uma tarefa DIFERENTE (ex: CONSULTAR_FATURA) e o bot abandonava a
  troca de plano e pulava pra essa tarefa em silêncio, sem confirmar
  com o cliente.

A correção adiciona uma checagem determinística (`_pede_desconto`) ANTES
de `_escolhe_plano` tentar casar número/nome/"mais barato" e ANTES de
`_outra_tarefa_pedida` rodar o classificador de intenção — em qualquer
caminho (GUIADO/INTERMEDIÁRIO/DIRETO) e também no atalho de abertura do
DIRETO (`_inicia`).

Determinístico: interpretador e classificador de intenção são stubs —
nenhuma chamada de API. O stub de intenção devolve CONSULTAR_FATURA de
propósito (o caso real observado na investigação) pra provar que o
desconto barra esse salto ANTES do classificador ser chamado.

Uso: python teste_pedido_desconto.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import fluxos  # noqa: E402
from fluxos import Sessao, processa, roteia  # noqa: E402

# ---- stubs ---------------------------------------------------------------
CHAMADAS_INTENCAO = []


def _fake_interpreta(pergunta, tipo, dados, mensagem):
    if tipo == "preferencia_plano":
        return {"tipo": "preferencia", "valor": "nenhuma"}
    return {"tipo": "nao_entendi"}


def _fake_intencao(mensagem):
    # devolve uma tarefa DIFERENTE de propósito: é o caso real da
    # investigação (reclassificar "quero pagar 45" como CONSULTAR_FATURA
    # e pular a troca de plano em silêncio). Se a checagem de desconto
    # não rodar ANTES disso, o teste de salto de tarefa vai pegar.
    CHAMADAS_INTENCAO.append(mensagem)
    return "CONSULTAR_FATURA"


fluxos.interpreta = _fake_interpreta
fluxos.identifica_intencao = _fake_intencao

FRASES_DESCONTO = [
    "quero pagar menos mas continuar com os 20gb",
    "eu quero um desconto",
    "quero pagar 45",
]


# ---- caso 1: já na etapa de escolher plano, os 3 caminhos -----------------
def _caso_escolher_guiado():
    erros = []
    for frase in FRASES_DESCONTO:
        CHAMADAS_INTENCAO.clear()
        sessao = Sessao()
        sessao.plano_atual = "basico"
        sessao.caminho = "GUIADO"
        sessao.tarefa = "TROCAR_PLANO"
        sessao.etapa = "escolher"
        resposta = processa(sessao, frase, "GUIADO")

        if "desconto" not in resposta.lower():
            erros.append(f"[GUIADO] {frase!r}: resposta não menciona "
                         f"desconto: {resposta[:100]!r}")
        if sessao.plano_escolhido:
            erros.append(f"[GUIADO] {frase!r}: plano foi escolhido/trocado "
                         f"em silêncio ({sessao.plano_escolhido!r})")
        if sessao.etapa != "escolher":
            erros.append(f"[GUIADO] {frase!r}: etapa mudou pra "
                         f"{sessao.etapa!r} (esperado seguir em 'escolher')")
        if CHAMADAS_INTENCAO:
            erros.append(f"[GUIADO] {frase!r}: classificador de intenção "
                         f"foi chamado ({CHAMADAS_INTENCAO}) — deveria ter "
                         f"sido barrado pela checagem de desconto")
    return erros


def _caso_escolher_intermediario():
    erros = []
    for frase in FRASES_DESCONTO:
        CHAMADAS_INTENCAO.clear()
        sessao = Sessao()
        sessao.plano_atual = "basico"
        sessao.caminho = "INTERMEDIARIO"
        sessao.tarefa = "TROCAR_PLANO"
        sessao.etapa = "escolher"
        resposta = processa(sessao, frase, "INTERMEDIARIO")

        if "desconto" not in resposta.lower():
            erros.append(f"[INTERMEDIARIO] {frase!r}: resposta não menciona "
                         f"desconto: {resposta[:100]!r}")
        if "não achei esse plano" in resposta.lower():
            erros.append(f"[INTERMEDIARIO] {frase!r}: ainda cai no "
                         f"'não achei esse plano' genérico")
        if sessao.plano_escolhido:
            erros.append(f"[INTERMEDIARIO] {frase!r}: plano foi escolhido "
                         f"em silêncio ({sessao.plano_escolhido!r})")
        if CHAMADAS_INTENCAO:
            erros.append(f"[INTERMEDIARIO] {frase!r}: classificador de "
                         f"intenção foi chamado — deveria ter sido barrado")
    return erros


def _caso_escolher_direto():
    erros = []
    for frase in FRASES_DESCONTO:
        CHAMADAS_INTENCAO.clear()
        sessao = Sessao()
        sessao.plano_atual = "basico"
        sessao.caminho = "DIRETO"
        sessao.tarefa = "TROCAR_PLANO"
        sessao.etapa = "escolher"
        resposta = processa(sessao, frase, "DIRETO")

        if "desconto" not in resposta.lower():
            erros.append(f"[DIRETO] {frase!r}: resposta não menciona "
                         f"desconto: {resposta[:100]!r}")
        if sessao.plano_atual != "basico":
            erros.append(f"[DIRETO] {frase!r}: TROCOU DE PLANO em silêncio "
                         f"(plano_atual={sessao.plano_atual!r})")
        if "trocado" in resposta.lower() or "✅" in resposta:
            erros.append(f"[DIRETO] {frase!r}: resposta parece confirmar "
                         f"uma troca de plano: {resposta[:100]!r}")
        if CHAMADAS_INTENCAO:
            erros.append(f"[DIRETO] {frase!r}: classificador de intenção "
                         f"foi chamado — deveria ter sido barrado")
    return erros


# ---- caso 2: atalho de abertura do DIRETO (_inicia) -----------------------
# "20gb" citado na 1ª mensagem, com o plano atual != Plus: sem a
# checagem, `_inicia` chamaria acha_planos direto e trocaria de plano
# antes mesmo de chegar em _escolhe_plano.
def _caso_abertura_direto():
    erros = []
    frase = "quero pagar menos mas continuar com os 20gb"
    sessao = Sessao()
    sessao.plano_atual = "basico"
    resposta = roteia(sessao, frase, "DIRETO", "TROCAR_PLANO")

    if sessao.plano_atual != "basico":
        erros.append(f"abertura DIRETO: TROCOU DE PLANO em silêncio na "
                     f"1ª mensagem (plano_atual={sessao.plano_atual!r})")
    if "desconto" not in resposta.lower():
        erros.append(f"abertura DIRETO: resposta não menciona desconto: "
                     f"{resposta[:120]!r}")
    return erros


# ---- caso 3: depois do desconto, uma escolha real de plano ainda funciona -
def _caso_segue_funcionando_depois():
    erros = []
    sessao = Sessao()
    sessao.plano_atual = "basico"
    sessao.caminho = "GUIADO"
    sessao.tarefa = "TROCAR_PLANO"
    sessao.etapa = "escolher"
    processa(sessao, "eu quero um desconto", "GUIADO")
    resposta = processa(sessao, "2", "GUIADO")

    if sessao.plano_escolhido != "plus":
        erros.append(f"depois do desconto, escolher '2' não funcionou: "
                     f"plano_escolhido={sessao.plano_escolhido!r}, "
                     f"resposta={resposta[:100]!r}")
    return erros


def main():
    resultados = [
        ("desconto na etapa 'escolher' — GUIADO", _caso_escolher_guiado()),
        ("desconto na etapa 'escolher' — INTERMEDIÁRIO",
         _caso_escolher_intermediario()),
        ("desconto na etapa 'escolher' — DIRETO", _caso_escolher_direto()),
        ("desconto citando '20gb' na abertura do DIRETO (_inicia)",
         _caso_abertura_direto()),
        ("depois do desconto, escolha real de plano ainda funciona",
         _caso_segue_funcionando_depois()),
    ]

    ok = 0
    for nome, erros in resultados:
        if erros:
            print(f"[ERRO] {nome}")
            for e in erros:
                print(f"       → {e}")
        else:
            ok += 1
            print(f"[OK  ] {nome}")
    print(f"\n{ok}/{len(resultados)} casos corretos")
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
