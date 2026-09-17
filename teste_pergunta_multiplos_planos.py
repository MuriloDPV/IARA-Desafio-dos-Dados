"""Regressão da investigação: "Só tenho este plano?" e "Tenho outro plano
em meu nome?" caíam no classificador de intenção, que oscilava entre
CONSULTAR_FATURA / TROCAR_PLANO / FORA_DE_ESCOPO pras MESMAS frases (ver
relatório da investigação, 2026-09-15). E como a consulta de fatura só
pede confirmação SIM/NÃO no caminho GUIADO, o comportamento também variava
conforme o classificador INAF (instável na mesma fronteira Rudimentar x
Elementar) caía pra cada frase — daí uma pedir SIM/NÃO e a outra não, na
mesma intenção.

A correção adiciona uma checagem determinística (`_pergunta_multiplos_planos`)
ANTES de `tarefa`/`caminho` (INAF) serem usados pra rotear em `roteia`/
`processa` — mesmo padrão de `_pede_desconto`/`_pede_atendente_humano`. A
resposta é fixa, não depende de nível de letramento nem de intenção.

Determinístico: o stub de `identifica_intencao` devolve, a cada chamada, um
valor DIFERENTE dos observados na investigação (cicla entre eles); o
`caminho` passado pra `roteia` também cicla entre os valores observados.
Se a checagem não rodasse ANTES do roteamento, a resposta variaria (ou
pediria SIM/NÃO) dependendo de qual valor caiu naquela rodada — é
exatamente esse sorteio que o teste teria que pegar rodando 100% das
vezes, não só na maioria.

Uso: python teste_pergunta_multiplos_planos.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import itertools  # noqa: E402

import fluxos  # noqa: E402
from fluxos import MSG_MULTIPLOS_PLANOS, Sessao, roteia  # noqa: E402

# ---- stubs: ciclam pelos valores REAIS observados na investigação --------
_TAREFAS_INSTAVEIS = itertools.cycle(
    ["TROCAR_PLANO", "CONSULTAR_FATURA", "FORA_DE_ESCOPO"])
_CAMINHOS_INSTAVEIS = itertools.cycle(["GUIADO", "INTERMEDIARIO", "DIRETO"])
CHAMADAS_INTENCAO = []


def _fake_intencao(mensagem):
    CHAMADAS_INTENCAO.append(mensagem)
    return next(_TAREFAS_INSTAVEIS)


fluxos.identifica_intencao = _fake_intencao

# as 2 frases exatas da investigação
FRASES_INVESTIGACAO = [
    "Só tenho este plano?",
    "Tenho outro plano em meu nome?",
]

# variações próximas pedidas junto com a correção
FRASES_VARIACOES = [
    "quantas linhas eu tenho",
    "tenho mais de um plano",
    "existe outro plano no meu nome?",
    "eu tenho mais de uma linha?",
]

N_REPETICOES = 20


def _caso_frases_investigacao():
    """As 2 frases exatas, cada uma repetida N vezes com tarefa/caminho
    instáveis (simulando o sorteio real do modelo) — tem que dar a MESMA
    resposta fixa 100% das vezes, nunca pedir SIM/NÃO, e nunca chamar o
    classificador de intenção."""
    erros = []
    for frase in FRASES_INVESTIGACAO:
        for i in range(N_REPETICOES):
            CHAMADAS_INTENCAO.clear()
            sessao = Sessao()
            caminho = next(_CAMINHOS_INSTAVEIS)
            tarefa = next(_TAREFAS_INSTAVEIS)
            resposta = roteia(sessao, frase, caminho, tarefa)

            if resposta != MSG_MULTIPLOS_PLANOS:
                erros.append(
                    f"{frase!r} (rodada {i + 1}, caminho={caminho}, "
                    f"tarefa={tarefa}): resposta não foi a fixa: "
                    f"{resposta[:100]!r}")
            if "SIM" in resposta.upper() and "NÃO" in resposta.upper():
                erros.append(
                    f"{frase!r} (rodada {i + 1}): pediu confirmação "
                    f"SIM/NÃO em vez de responder direto")
            if CHAMADAS_INTENCAO:
                erros.append(
                    f"{frase!r} (rodada {i + 1}): classificador de "
                    f"intenção foi chamado ({CHAMADAS_INTENCAO}) — "
                    f"deveria ter sido barrado pela checagem "
                    f"determinística")
    return erros


def _caso_variacoes():
    erros = []
    for frase in FRASES_VARIACOES:
        CHAMADAS_INTENCAO.clear()
        sessao = Sessao()
        resposta = roteia(sessao, frase, "GUIADO", "TROCAR_PLANO")
        if resposta != MSG_MULTIPLOS_PLANOS:
            erros.append(f"{frase!r}: resposta não foi a fixa: "
                         f"{resposta[:100]!r}")
        if CHAMADAS_INTENCAO:
            erros.append(f"{frase!r}: classificador de intenção foi "
                         f"chamado — deveria ter sido barrado")
    return erros


def _caso_nao_intercepta_frase_normal():
    """A checagem não pode ser ampla demais: um pedido real de troca de
    plano que cita "outro plano" continua indo pra TROCAR_PLANO, não pra
    resposta fixa de múltiplos planos."""
    erros = []
    frases_normais = [
        "quero trocar para outro plano mais barato",
        "quero mudar de plano",
        "quanto tá minha conta esse mês?",
        "meu celular tá sem sinal",
    ]
    for frase in frases_normais:
        CHAMADAS_INTENCAO.clear()
        sessao = Sessao()
        resposta = roteia(sessao, frase, "DIRETO", "TROCAR_PLANO")
        if resposta == MSG_MULTIPLOS_PLANOS:
            erros.append(f"{frase!r}: foi engolida pela checagem de "
                         f"múltiplos planos (falso positivo)")
    return erros


def main():
    resultados = [
        (f"{N_REPETICOES}x cada frase da investigação, tarefa/caminho "
         f"instáveis (100% determinístico)", _caso_frases_investigacao()),
        ("variações próximas (quantas linhas / mais de um plano / etc.)",
         _caso_variacoes()),
        ("não intercepta frases normais (sem falso positivo)",
         _caso_nao_intercepta_frase_normal()),
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
