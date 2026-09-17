"""Regressão da detecção de despedida no roteador (sessão ociosa).

Cobre também o emoji de fechamento ("👍" solto depois do "precisa de mais
alguma coisa?"), que vale como despedida SÓ com tarefa concluída — mesma
regra do "não obrigado". Sem tarefa concluída não há oferta pra encerrar,
e o emoji volta a ser só cola: sustenta "obrigado 👍", não se sustenta
sozinho.

Determinístico: não chama API nenhuma.

Uso: python teste_despedida.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

# os casos de emoji não imprimem no cp1252 padrão do console do Windows
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from fluxos import MSG_DESPEDIDA, Sessao, roteia  # noqa: E402

# (texto, tarefas_concluidas, tarefa_classificada, espera_despedida)
CASOS = [
    # --- despedidas simples (já cobertas pela lista fixa) ---
    ("obrigado", [], "FORA_DE_ESCOPO", True),
    ("Obrigada!", [], "FORA_DE_ESCOPO", True),
    ("valeu", [], "FORA_DE_ESCOPO", True),
    ("tchau", [], "FORA_DE_ESCOPO", True),
    ("era só isso", [], "FORA_DE_ESCOPO", True),
    ("obrigado viu", [], "FORA_DE_ESCOPO", True),
    ("até mais", [], "FORA_DE_ESCOPO", True),
    ("de nada", [], "FORA_DE_ESCOPO", True),

    # --- combinações: o que quebrava antes do fix estrutural ---
    ("era só isso obrigado", [], "FORA_DE_ESCOPO", True),
    ("era só isso, obrigado!", [], "FORA_DE_ESCOPO", True),
    ("Era isso, obrigado", [], "FORA_DE_ESCOPO", True),
    ("isso, obrigado", [], "FORA_DE_ESCOPO", True),
    ("valeu, tchau", [], "FORA_DE_ESCOPO", True),
    ("obrigado, tchau", [], "FORA_DE_ESCOPO", True),
    ("muito obrigado, até mais", [], "FORA_DE_ESCOPO", True),
    ("era so isso mesmo valeu falou", [], "FORA_DE_ESCOPO", True),
    ("ok, obrigado", [], "FORA_DE_ESCOPO", True),
    ("tá bom, valeu mesmo", [], "FORA_DE_ESCOPO", True),

    # --- recusa da oferta: só vale DEPOIS de uma tarefa concluída ---
    ("não obrigado", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("não, obrigado", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("não obrigado, era só isso", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("não obrigado", [], "FORA_DE_ESCOPO", False),
    ("não obrigada", [], "FORA_DE_ESCOPO", False),
    ("não", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("Não!", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("nao", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("não precisa", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("nao precisa", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("nada", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("não", [], "FORA_DE_ESCOPO", False),
    ("nao", [], "FORA_DE_ESCOPO", False),
    ("não precisa", [], "FORA_DE_ESCOPO", False),
    ("nada", [], "FORA_DE_ESCOPO", False),

    # --- emoji de fechamento: só encerra DEPOIS de uma tarefa concluída ---
    ("👍", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("🙏", ["RECLAMAR_SINAL"], "FORA_DE_ESCOPO", True),
    ("❤️", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("😊", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("👍🏽", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),   # com tom de pele
    ("👍👍", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("👍 🙏", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("obrigado 👍", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("ok 👍", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", True),
    ("👍", [], "FORA_DE_ESCOPO", False),      # sem tarefa não há oferta
    ("😊", [], "FORA_DE_ESCOPO", False),
    ("obrigado 👍", [], "FORA_DE_ESCOPO", True),   # o "obrigado" é que vale
    ("😡", ["CONSULTAR_FATURA"], "FORA_DE_ESCOPO", False),   # não é fechamento
    ("👍 quero trocar de plano", ["CONSULTAR_FATURA"], "TROCAR_PLANO", False),

    # --- falso positivo: pedido de tarefa com agradecimento educado ---
    ("trocar de plano, obrigado", [], "TROCAR_PLANO", False),
    ("queria ver minha fatura, obrigado", [], "CONSULTAR_FATURA", False),
    ("obrigado, mas quero cancelar minha linha", [], "CANCELAR_LINHA", False),
    ("valeu, mas meu sinal continua ruim", [], "RECLAMAR_SINAL", False),
    ("obrigado pela paciência, onde fica a loja?", [], "FORA_DE_ESCOPO", False),
]


def main():
    acertos = 0
    for i, (texto, concluidas, tarefa, espera) in enumerate(CASOS, start=1):
        sessao = Sessao(tarefas_concluidas=list(concluidas))
        resposta = roteia(sessao, texto, "INTERMEDIARIO", tarefa)
        obtido = resposta == MSG_DESPEDIDA
        ok = obtido == espera
        acertos += ok
        status = "OK " if ok else "ERRO"
        rotulo = "despedida" if espera else "NÃO despedida"
        print(f"[{status}] caso {i}: esperado={rotulo} msg={texto!r}")
        if not ok:
            print(f"       resposta: {resposta[:90]!r}")
    print(f"\n{acertos}/{len(CASOS)} casos corretos")
    return 0 if acertos == len(CASOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
