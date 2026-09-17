"""Regressão da reclamação de preço na confirmação do cancelamento.

Reclamar do valor ("25 reais muito caro") não é responder: o
interpretador devolve nao_entendi (calibração em interprete.py, igual à
regra da hesitação) e o fluxo faz o de sempre — conta a confusão, repete
a pergunta e oferece atendente na 2ª seguida. Nada é abortado nem
executado por conta própria.

A única diferença é a frase de ABERTURA: em vez do "não entendi"
genérico, uma linha curta que reconhece a reclamação antes de repetir a
pergunta. Escopo fechado nas duas confirmações SIM/NÃO do cancelamento —
nas outras etapas (troca de plano, sinal, fatura) o texto segue
como sempre.

Determinístico: interpretador e classificador de intenção são
substituídos por stubs — nenhuma chamada de API.

Uso: python teste_reclamacao_cancelamento.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import fluxos  # noqa: E402
from fluxos import MSG_ATENDENTE, MSG_NAO_ENTENDI, Sessao, roteia  # noqa: E402

# ---- stubs -------------------------------------------------------------
# interpreta: por padrão nao_entendi — é exatamente o que a calibração
# faz com uma reclamação de preço numa etapa sim/não. intencao: o que o
# caso pedir, com as chamadas registradas (reclamação pura não pode nem
# chegar no classificador).
CFG = {"interpreta": {"tipo": "nao_entendi"}, "intencao": "FORA_DE_ESCOPO",
       "chamadas": []}


def _fake_interpreta(pergunta, tipo, dados, mensagem):
    if tipo == "preferencia_plano":       # abertura da troca de plano
        return {"tipo": "preferencia", "valor": "nenhuma"}
    return CFG["interpreta"]


def _fake_intencao(mensagem):
    CFG["chamadas"].append(mensagem)
    return CFG["intencao"]


fluxos.interpreta = _fake_interpreta
fluxos.identifica_intencao = _fake_intencao


# ---- casos -------------------------------------------------------------
# plano_atual "plus" (R$ 50,00) deixa a cobrança proporcional em R$ 25,00
# — é o valor de que a persona do caso reclama.
CASOS = [
    {"nome": "aviso de cobrança: '25 reais muito caro' reconhece e repete",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA", "plano_atual": "plus",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": ["25 reais muito caro"],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 1,
                "contem": ["Entendo que é um valor a mais",
                           "quer seguir com o cancelamento",
                           "SIM ou NÃO"],
                "nao_contem": ["não entendi", "abortado", "continua ativa",
                               "Cancelamento registrado", "CPF"]}},

    {"nome": "aviso de cobrança: 'isso não vale a pena' também reconhece",
     "caminho": "INTERMEDIARIO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": ["isso não vale a pena"],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 1,
                "contem": ["Entendo que é um valor a mais",
                           "quer seguir com o cancelamento"],
                "nao_contem": ["não entendi", "abortado"]}},

    {"nome": "confirmação de intenção: 'tá muito caro isso' reconhece e repete",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "desvios": ["tá muito caro isso"],
     "espera": {"tarefa": "CANCELAR_LINHA",
                "etapa": "cancel_confirmar_intencao", "confusas": 1,
                "contem": ["Entendo que o valor pesa",
                           "Você quer cancelar a sua linha?", "SIM ou NÃO"],
                "nao_contem": ["não entendi", "continua ativa"]}},

    {"nome": "reação sem ser ao preço ganha a frase de chateação",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": ["que palhaçada isso"],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 1,
                "contem": ["Entendo a sua chateação",
                           "quer seguir com o cancelamento"],
                "nao_contem": ["não entendi", "abortado"]}},

    # --- reclamação pura não é pedido de outra tarefa ---
    # sem isso, "25 reais muito caro" vira TROCAR_PLANO no classificador de
    # intenção e o cancelamento é abandonado sem ninguém ter pedido
    {"nome": "reclamação pura não vira troca de plano (nem chama a intenção)",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA", "plano_atual": "plus",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "intencao": "TROCAR_PLANO",
     "desvios": ["25 reais muito caro"],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 1, "chamadas": 0,
                "contem": ["Entendo que é um valor a mais"],
                "nao_contem": ["Vamos trocar seu plano", "Estes são os planos"]}},

    {"nome": "reclamação COM pedido de outra tarefa ainda troca de tarefa",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA", "plano_atual": "plus",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "intencao": "TROCAR_PLANO",
     "desvios": ["tá muito caro, quero trocar de plano"],
     "espera": {"tarefa": "TROCAR_PLANO", "confusas": 0, "chamadas": 1,
                "contem": ["plano"], "nao_contem": ["Entendo que"]}},

    # --- o que NÃO muda ---
    {"nome": "hesitação continua com o 'não entendi' de sempre",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": ["sei lá"],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 1,
                "contem": [MSG_NAO_ENTENDI, "quer seguir com o cancelamento"],
                "nao_contem": ["Entendo que", "Entendo a sua"]}},

    {"nome": "resposta clara junto com a reclamação continua sendo resposta",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA", "plano_atual": "plus",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "interpreta": {"tipo": "resposta_valida", "valor": "sim"},
     "desvios": ["25 reais é caro mas pode cancelar"],
     "espera": {"tarefa": "", "etapa": "",
                "confusas": 0, "contem": ["Cancelamento registrado"],
                "nao_contem": ["Entendo que", "não entendi", "CPF"]}},

    {"nome": "2 reclamações seguidas ainda oferecem atendente",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA", "plano_atual": "plus",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": ["25 reais muito caro", "continua caro do mesmo jeito"],
     "espera": {"tarefa": "", "etapa": "", "confusas": 0,
                "contem": [MSG_ATENDENTE], "nao_contem": ["Entendo que"]}},

    # --- escopo fechado: outras etapas seguem com o texto genérico ---
    {"nome": "reclamação na confirmação da TROCA não ganha reconhecimento",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["sim", "3"],
     "etapa_alvo": "confirmar_troca",
     "desvios": ["tá muito caro"],
     "espera": {"tarefa": "TROCAR_PLANO", "etapa": "confirmar_troca",
                "confusas": 1, "contem": [MSG_NAO_ENTENDI],
                "nao_contem": ["Entendo que", "Entendo a sua"]}},

    {"nome": "reclamação na confirmação do SINAL não ganha reconhecimento",
     "caminho": "GUIADO", "tarefa": "RECLAMAR_SINAL",
     "abertura": "meu celular não pega", "passos": ["sim"],
     "etapa_alvo": "sinal_confirmar_abertura",
     "desvios": ["que palhaçada"],
     "espera": {"tarefa": "RECLAMAR_SINAL", "etapa": "sinal_confirmar_abertura",
                "confusas": 1, "contem": [MSG_NAO_ENTENDI],
                "nao_contem": ["Entendo que", "Entendo a sua"]}},
]


def _roda_caso(caso) -> list[str]:
    CFG["interpreta"] = caso.get("interpreta", {"tipo": "nao_entendi"})
    CFG["intencao"] = "FORA_DE_ESCOPO"
    CFG["chamadas"] = []

    sessao = Sessao()
    if caso.get("plano_atual"):
        sessao.plano_atual = caso["plano_atual"]
    roteia(sessao, caso["abertura"], caso["caminho"], caso["tarefa"])
    for passo in caso["passos"]:
        roteia(sessao, passo, caso["caminho"], sessao.tarefa)

    if sessao.etapa != caso["etapa_alvo"]:
        return [f"preparo falhou: etapa {sessao.etapa!r}, "
                f"esperada {caso['etapa_alvo']!r}"]

    CFG["intencao"] = caso.get("intencao", "FORA_DE_ESCOPO")
    CFG["chamadas"] = []  # só conta as chamadas do desvio
    resposta = ""
    for mensagem in caso["desvios"]:
        resposta = roteia(sessao, mensagem, caso["caminho"], sessao.tarefa)

    e = caso["espera"]
    obtido = {"tarefa": sessao.tarefa, "etapa": sessao.etapa,
              "confusas": sessao.confusas_seguidas,
              "chamadas": len(CFG["chamadas"])}
    erros = []
    for chave, esperado in e.items():
        if chave == "contem":
            erros += [f"resposta não contém {m[:45]!r}"
                      for m in esperado if m not in resposta]
        elif chave == "nao_contem":
            erros += [f"resposta contém {m[:45]!r} e não devia"
                      for m in esperado if m in resposta]
        elif obtido[chave] != esperado:
            erros.append(f"{chave}={obtido[chave]!r}, esperado {esperado!r}")
    return erros


def _caso_valor_certo_na_pergunta() -> list[str]:
    """A pergunta repetida tem que continuar sendo a pergunta da etapa —
    com a cobrança proporcional real (R$ 25,00 pro plano Plus), não uma
    resposta improvisada pra reclamação."""
    CFG["interpreta"] = {"tipo": "nao_entendi"}
    CFG["intencao"] = "FORA_DE_ESCOPO"

    sessao = Sessao()
    sessao.plano_atual = "plus"
    r1 = roteia(sessao, "quero cancelar minha linha", "INTERMEDIARIO",
                "CANCELAR_LINHA")
    erros = []
    if "R$ 25,00" not in r1:
        erros.append(f"aviso não trouxe a cobrança de R$ 25,00: {r1[:80]!r}")
    r2 = roteia(sessao, "25 reais muito caro", "INTERMEDIARIO", "CANCELAR_LINHA")
    if not r2.startswith("Entendo que é um valor a mais, sim."):
        erros.append(f"não abriu com o reconhecimento: {r2[:60]!r}")
    if "Mesmo com a cobrança proporcional" not in r2:
        erros.append(f"não repetiu a pergunta da etapa: {r2[:80]!r}")
    return erros


def main():
    resultados = [(caso["nome"], _roda_caso(caso)) for caso in CASOS]
    resultados.append(("pergunta repetida mantém o valor real da cobrança",
                       _caso_valor_certo_na_pergunta()))

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
