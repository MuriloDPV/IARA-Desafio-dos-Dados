"""Roda os casos de teste do classificador de intenção.

Uso: python teste_intencao.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from intencao import identifica_intencao  # noqa: E402

CASOS = [
    # TROCAR_PLANO
    ("quero mudar meu plano", "TROCAR_PLANO"),
    ("queria um plano com mais internet, como faço?", "TROCAR_PLANO"),
    ("Quero migrar do Básico 5GB para o Premium 50GB", "TROCAR_PLANO"),
    # CONSULTAR_FATURA
    ("quanto tá minha conta esse mês?", "CONSULTAR_FATURA"),
    ("quero ver minha fatura, quando vence?", "CONSULTAR_FATURA"),
    # RECLAMAR_SINAL
    ("meu celular ta sem sinal desde ontem", "RECLAMAR_SINAL"),
    ("a internet aqui ta muito lenta, não carrega nada", "RECLAMAR_SINAL"),
    # CANCELAR_LINHA
    ("quero cancelar minha linha de vez", "CANCELAR_LINHA"),
    ("não quero mais esse número, pode encerrar o contrato", "CANCELAR_LINHA"),
    # ...mas "linha" sem sinal de encerramento é o PLANO, não o cancelamento
    # (trocar e cancelar são ações opostas — errar aqui é caro)
    ("mudar a linha", "TROCAR_PLANO"),
    ("mudar minha linha", "TROCAR_PLANO"),
    ("trocar minha linha", "TROCAR_PLANO"),
    ("quero mudar de linha", "TROCAR_PLANO"),
    # FORA_DE_ESCOPO
    ("onde fica a loja de vocês?", "FORA_DE_ESCOPO"),
    ("quero passar meu número pra outra operadora", "FORA_DE_ESCOPO"),
    # mudar vencimento é alteração, não consulta — não é tarefa suportada
    ("mudar vencimento", "FORA_DE_ESCOPO"),
    ("trocar data de pagamento", "FORA_DE_ESCOPO"),
    ("mudar dia do vencimento", "FORA_DE_ESCOPO"),
    ("quero mudar a data de vencimento da minha fatura", "FORA_DE_ESCOPO"),
    ("da pra mudar o dia que vence o boleto?", "FORA_DE_ESCOPO"),
    # ...mas perguntar QUANDO vence continua sendo consulta
    ("qual a data de vencimento da minha fatura?", "CONSULTAR_FATURA"),
    # atendimento #24 real do painel: saiu FORA_DE_ESCOPO uma vez, mas não
    # reproduziu em 16/16 tentativas de investigação — ruído isolado do
    # modelo, não falha do prompt (a regra de "conta" já cobre o caso).
    # Casos fixados aqui como guarda de regressão, não porque houve ajuste.
    ('- "oi filho minha conta veio errada acho, sei la"', "CONSULTAR_FATURA"),
    ("oi mana minha conta ta errada acho, sei la", "CONSULTAR_FATURA"),
    ("oi acho que a conta veio diferente esse mes, sei la", "CONSULTAR_FATURA"),
    ("minha conta veio errada acho, sei la", "CONSULTAR_FATURA"),
]


def main():
    acertos = 0
    for i, (mensagem, esperado) in enumerate(CASOS, start=1):
        obtido = identifica_intencao(mensagem)
        ok = obtido == esperado
        acertos += ok
        status = "OK " if ok else "ERRO"
        print(f"[{status}] caso {i}: esperado={esperado} obtido={obtido}")
        print(f"       msg: {mensagem}")
    print(f"\n{acertos}/{len(CASOS)} casos corretos")


if __name__ == "__main__":
    main()
