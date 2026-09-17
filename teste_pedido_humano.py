"""Regressão do bug relatado: pedido EXPLÍCITO de humano só escalava na
hora quando a mensagem continha literalmente a palavra "atendente"
(`"atendente" in texto.lower()`, em `roteia` e `processa`). Sinônimos
igualmente explícitos como "humano", "pessoa de verdade" ou "gente de
verdade" não batiam em nada — caíam na classificação normal de intenção,
viravam FORA_DE_ESCOPO, e só escalariam de verdade depois de 2 respostas
confusas seguidas (mecanismo totalmente diferente, por repetição, não
por pedido explícito).

A correção troca a checagem por `_pede_atendente_humano`, que reconhece
um conjunto pequeno de termos ({"atendente", "humano", "pessoa de
verdade", "gente de verdade"}) e escala IMEDIATAMENTE, nos dois pontos
reais de entrada (`roteia`, chamado por bot.py; `processa`, chamado só
de dentro de `roteia`). Determinístico por palavra/frase completa — não
substring solta —, pra não confundir "humano" dentro de "desumano" com
um pedido de atendente.

Determinístico: nenhuma chamada de API (a checagem intercepta antes de
qualquer classificação; o caso negativo usa tarefa FORA_DE_ESCOPO, que
também não chama API).

Uso: python teste_pedido_humano.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from fluxos import MSG_ATENDENTE, Sessao, roteia  # noqa: E402

FRASES_HUMANO = [
    "preciso de um humano",
    "quero falar com uma pessoa de verdade",
    "quero falar com gente de verdade",
]

# regressão: continua funcionando pra quem já usava "atendente"
FRASES_ATENDENTE_JA_FUNCIONAVA = [
    "quero falar com atendente",
    "atendente",
]

# não pode virar falso positivo: "humano"/"atendente" como SUBSTRING de
# outra palavra não é pedido de atendente
FRASES_SEM_PEDIDO = [
    "isso é desumano",
    "sou super humanoide, adoro tecnologia",
]


def _caso_escalonamento_imediato_sessao_ociosa():
    """Sessão nova, sem fluxo ativo: pedido explícito escala na hora,
    sem precisar de nenhuma confusão antes."""
    erros = []
    for frase in FRASES_HUMANO:
        sessao = Sessao()
        resposta = roteia(sessao, frase, "GUIADO", "FORA_DE_ESCOPO")
        if resposta != MSG_ATENDENTE:
            erros.append(f"{frase!r}: não escalou — resposta: "
                         f"{resposta[:100]!r}")
        if sessao.caminho:
            erros.append(f"{frase!r}: sessão não foi encerrada "
                         f"(caminho={sessao.caminho!r})")
    return erros


def _caso_escalonamento_imediato_meio_do_fluxo():
    """No MEIO de um fluxo em andamento (GUIADO, confirmar_intencao),
    o pedido explícito escala na hora — sem precisar de 2 confusões
    seguidas. confusas_seguidas tem que continuar em 0: a mensagem nunca
    chega a ser tratada como confusão, é interceptada antes disso."""
    erros = []
    for frase in FRASES_HUMANO:
        sessao = Sessao()
        sessao.caminho = "GUIADO"
        sessao.tarefa = "TROCAR_PLANO"
        sessao.etapa = "confirmar_intencao"
        sessao.confusas_seguidas = 0
        resposta = roteia(sessao, frase, "GUIADO", "TROCAR_PLANO")
        if resposta != MSG_ATENDENTE:
            erros.append(f"{frase!r} (meio do fluxo): não escalou na "
                         f"hora — resposta: {resposta[:100]!r}")
        if sessao.confusas_seguidas != 0:
            erros.append(f"{frase!r}: contou como confusão "
                         f"(confusas_seguidas={sessao.confusas_seguidas}) "
                         f"em vez de escalar direto")
    return erros


def _caso_atendente_continua_funcionando():
    erros = []
    for frase in FRASES_ATENDENTE_JA_FUNCIONAVA:
        sessao = Sessao()
        resposta = roteia(sessao, frase, "GUIADO", "FORA_DE_ESCOPO")
        if resposta != MSG_ATENDENTE:
            erros.append(f"{frase!r}: regressão — não escalou mais — "
                         f"resposta: {resposta[:100]!r}")
    return erros


def _caso_sem_falso_positivo():
    erros = []
    for frase in FRASES_SEM_PEDIDO:
        sessao = Sessao()
        resposta = roteia(sessao, frase, "GUIADO", "FORA_DE_ESCOPO")
        if resposta == MSG_ATENDENTE:
            erros.append(f"{frase!r}: falso positivo — escalou sem "
                         f"pedido explícito de atendente")
    return erros


def main():
    resultados = [
        ("pedido explícito de humano escala na hora (sessão ociosa)",
         _caso_escalonamento_imediato_sessao_ociosa()),
        ("pedido explícito de humano escala na hora (meio do fluxo, "
         "sem contar como confusão)", _caso_escalonamento_imediato_meio_do_fluxo()),
        ("'atendente' continua escalando (regressão)",
         _caso_atendente_continua_funcionando()),
        ("'humano'/'atendente' dentro de outra palavra não é falso positivo",
         _caso_sem_falso_positivo()),
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
