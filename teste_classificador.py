"""Roda os 6 casos de teste no classificador, sem precisar do Telegram.

Uso: python teste_classificador.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from classificador import classifica  # noqa: E402

CASOS = [
    ("oi moço o telefone ta sem nada aqui nao pega nada nao sei mexer", "GUIADO"),
    ("minha internet acabou de novo não sei o que fazer", "GUIADO"),
    ("quero mudar meu plano", "INTERMEDIARIO"),
    ("oi, queria um plano com mais internet, como faço?", "INTERMEDIARIO"),
    ("Quero trocar meu plano de 5GB por um com mais dados. "
     "Qual é a opção intermediária de vocês?", "DIRETO"),
    ("Quero migrar do plano Básico 5GB para o Premium 50GB. "
     "Pode confirmar o valor de R$ 80 e já ativar?", "DIRETO"),
]

# Fronteira Elementar x Intermediário: caminho DIRETO sozinho não prova nada
# aqui (Intermediário e Proficiente caem os dois em DIRETO), por isso estes
# casos checam o NÍVEL exato. Investigação mostrou a mensagem abaixo
# escorregando pra Elementar em 10/12 tentativas antes do reforço da regra
# de calibração em classificador.py; depois do ajuste, 12/12 em Intermediário.
CASOS_NIVEL = [
    ("quero um plano com mais internet, umas 20GB", "Intermediário"),
    # controle: sem o dado quantificável, continua Elementar
    ("quero um plano com mais internet", "Elementar"),
]


def main():
    acertos = 0
    for i, (mensagem, esperado) in enumerate(CASOS, start=1):
        r = classifica(mensagem)
        ok = r["caminho"] == esperado
        acertos += ok
        status = "OK " if ok else "ERRO"
        print(f"[{status}] caso {i}: esperado={esperado} obtido={r['caminho']} "
              f"nivel={r['nivel']}")
        print(f"       msg: {mensagem}")
        print(f"       justificativa: {r['justificativa']}")

    for i, (mensagem, esperado) in enumerate(CASOS_NIVEL, start=1):
        r = classifica(mensagem)
        ok = r["nivel"] == esperado
        acertos += ok
        status = "OK " if ok else "ERRO"
        print(f"[{status}] caso nivel {i}: esperado={esperado} obtido={r['nivel']} "
              f"caminho={r['caminho']}")
        print(f"       msg: {mensagem}")
        print(f"       justificativa: {r['justificativa']}")

    total = len(CASOS) + len(CASOS_NIVEL)
    print(f"\n{acertos}/{total} casos no caminho/nível esperado")


if __name__ == "__main__":
    main()
