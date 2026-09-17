"""Regressão do bug relatado: na etapa de escolha de plano (depois que a
Iara lista as 3 opções numeradas), "Eu quero trocar para o plano dois"
caía em "não entendi" — a confirmação só reconhecia dígito isolado (ou
como 1º token da mensagem), nunca número por extenso, isolado ou dentro
de frase.

Duas partes:
1. `acha_plano` (dados.py) isolado — dígito e número por extenso, sozinho
   ou dentro de frase, incluindo o caso exato do relato.
2. Um caso de ponta a ponta via `roteia`, com o mesmo stub de
   `teste_troca_tarefa.py`, provando que o reconhecimento continua
   determinístico (0 chamadas de API) mesmo por extenso.

Determinístico: interpretador é substituído por stub que nunca resolve o
desvio — se um caso passar, foi o parsing determinístico que resolveu.

Uso: python teste_escolha_plano.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import fluxos  # noqa: E402
from fluxos import Sessao, roteia  # noqa: E402
from dados import acha_plano  # noqa: E402

# ---- stubs --------------------------------------------------------------
CHAMADAS_INTERPRETA = []


def _fake_interpreta(pergunta, tipo, dados, mensagem):
    CHAMADAS_INTERPRETA.append(mensagem)
    if tipo == "preferencia_plano":
        return {"tipo": "preferencia", "valor": "nenhuma"}
    return {"tipo": "nao_entendi"}


def _fake_intencao(mensagem):
    return "FORA_DE_ESCOPO"


fluxos.interpreta = _fake_interpreta
fluxos.identifica_intencao = _fake_intencao


# ---- casos: acha_plano isolado ------------------------------------------
CASOS_ACHA_PLANO = [
    # dígito, formatos já suportados antes do fix (regressão)
    ("1", "basico"),
    ("2", "plus"),
    ("3", "premium"),
    ("2.", "plus"),
    ("2 gb", "plus"),

    # número por extenso, sozinho
    ("um", "basico"),
    ("dois", "plus"),
    ("tres", "premium"),
    ("três", "premium"),
    ("dois.", "plus"),

    # o caso exato do relato
    ("Eu quero trocar para o plano dois", "plus"),

    # dígito dentro de frase completa (também não era achado antes do fix)
    ("quero o plano 2", "plus"),
    ("quero trocar para o plano 3", "premium"),

    # número por extenso dentro de frase completa
    ("quero trocar para o plano um", "basico"),
    ("plano dois, por favor", "plus"),
    ("prefiro o dois", "plus"),
    ("prefiro o um", "basico"),
    ("quero o terceiro", "premium"),
    ("quero o primeiro", "basico"),
    ("quero a segunda opção", "plus"),

    # nome/GB do plano — não podem quebrar com o fix
    ("plus", "plus"),
    ("Básico", "basico"),
    ("premium", "premium"),
    ("20gb", "plus"),
    ("5 giga", "basico"),

    # não deve virar falso positivo
    ("quero um plano mais barato", None),   # "um" é artigo, não escolha
    ("espera um segundo", None),            # "segundo" é tempo, não opção
    ("oi tudo bem", None),
]


def _roda_casos_acha_plano():
    erros = []
    for texto, esperado in CASOS_ACHA_PLANO:
        obtido = acha_plano(texto)
        if obtido != esperado:
            erros.append(f"acha_plano({texto!r}) = {obtido!r}, "
                         f"esperado {esperado!r}")
    return erros


# ---- caso de ponta a ponta: o relato original, via roteia ---------------
def _caso_ponta_a_ponta():
    CHAMADAS_INTERPRETA.clear()
    sessao = Sessao()
    roteia(sessao, "quero mudar meu plano", "GUIADO", "TROCAR_PLANO")
    roteia(sessao, "sim", "GUIADO", "TROCAR_PLANO")  # confirmar_intencao -> escolher

    erros = []
    if sessao.etapa != "escolher":
        return [f"preparo falhou: etapa {sessao.etapa!r}, esperada 'escolher'"]

    resposta = roteia(sessao, "Eu quero trocar para o plano dois",
                      "GUIADO", "TROCAR_PLANO")

    if sessao.plano_escolhido != "plus":
        erros.append(f"plano_escolhido={sessao.plano_escolhido!r}, "
                     f"esperado 'plus'")
    if sessao.etapa != "confirmar_troca":
        erros.append(f"etapa={sessao.etapa!r}, esperada 'confirmar_troca'")
    if "não entendi" in resposta.lower() or "nao entendi" in resposta.lower():
        erros.append(f"caiu em não entendi: {resposta[:80]!r}")
    if "Plus 20GB" not in resposta:
        erros.append(f"resposta não confirma o Plus 20GB: {resposta[:80]!r}")
    return erros


def main():
    resultados = [("acha_plano: dígito e extenso, isolado e em frase",
                   _roda_casos_acha_plano()),
                  ("ponta a ponta: 'Eu quero trocar para o plano dois' (relato)",
                   _caso_ponta_a_ponta())]

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
