"""Casos do interpretador de desvio dentro da etapa (usa a API real).

Foco: reclamação de preço numa confirmação SIM/NÃO é ambiguidade real
(nao_entendi), igual à hesitação — não vira "nao" por conta própria. Os
outros casos são a trava: os padrões de alta confiança ("pode ser", "o
do meio"), a pergunta respondível e a preferência da abertura da troca
continuam como estavam.

Uso: python teste_interprete.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from fluxos import Sessao, _dados_sistema  # noqa: E402
from interprete import interpreta  # noqa: E402

# plano Plus (R$ 50,00) → cobrança proporcional de R$ 25,00, o valor de
# que as mensagens reclamam
SESSAO = Sessao(plano_atual="plus")
DADOS = _dados_sistema(SESSAO)

P_CANCEL = ("Mesmo com a cobrança proporcional, quer seguir com o "
            "cancelamento? Responda SIM ou NÃO.")
P_TROCA = "Só pra confirmar: trocar para o Plus 20GB (R$ 50,00/mês)? Responda SIM ou NÃO."
P_ESCOLHA = "Me responda só com o número do plano: 1. Básico 5GB, 2. Plus 20GB, 3. Premium 50GB"

# (pergunta da etapa, tipo esperado, mensagem, tipo, valor esperado ou None)
CASOS = [
    # reclamação de preço na confirmação do cancelamento → ambiguidade
    (P_CANCEL, "sim_nao", "25 reais muito caro", "nao_entendi", None),
    (P_CANCEL, "sim_nao", "tá muito caro isso", "nao_entendi", None),
    (P_CANCEL, "sim_nao", "isso não vale a pena", "nao_entendi", None),
    (P_CANCEL, "sim_nao", "nossa, 25 reais? que absurdo", "nao_entendi", None),
    # hesitação (regra antiga) segue igual
    (P_CANCEL, "sim_nao", "sei lá", "nao_entendi", None),
    # ...mas a reclamação COM resposta junto continua sendo resposta
    (P_CANCEL, "sim_nao", "tá caro mas pode cancelar", "resposta_valida", "sim"),
    (P_CANCEL, "sim_nao", "tá caro demais, então deixa pra lá",
     "resposta_valida", "nao"),
    # alta confiança e pergunta respondível não podem regredir
    (P_CANCEL, "sim_nao", "isso aí, pode seguir", "resposta_valida", "sim"),
    (P_CANCEL, "sim_nao", "quanto vou pagar de cobrança?", "pergunta", None),
    (P_TROCA, "sim_nao", "bora", "resposta_valida", "sim"),
    (P_ESCOLHA, "escolha_plano", "o do meio", "resposta_valida", "plus"),
    # a calibração NÃO vale pra abertura da troca: ali "tá caro" é direção
    ("Qual plano o cliente quer?", "preferencia_plano",
     "tá caro demais isso, queria pagar mais barato", "preferencia", "barato"),
]


def main():
    acertos = 0
    for i, (pergunta, tipo, mensagem, esperado, valor) in enumerate(CASOS, 1):
        r = interpreta(pergunta, tipo, DADOS, mensagem)
        obtido = r.get("tipo")
        ok = obtido == esperado and (valor is None
                                     or str(r.get("valor", "")).lower() == valor)
        acertos += ok
        alvo = esperado if valor is None else f"{esperado}/{valor}"
        saiu = obtido if not r.get("valor") else f"{obtido}/{r['valor']}"
        print(f"[{'OK ' if ok else 'ERRO'}] caso {i}: esperado={alvo} "
              f"obtido={saiu}")
        print(f"       msg: {mensagem}")
        if r.get("resposta"):
            print(f"       resposta: {r['resposta']}")
    print(f"\n{acertos}/{len(CASOS)} casos corretos")
    return 0 if acertos == len(CASOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
