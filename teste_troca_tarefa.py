"""Regressão da troca de tarefa no meio de uma etapa.

Numa etapa de confirmação ("quer cancelar a linha? sim/não", "posso abrir
o chamado? sim/não") ou na escolha de plano ("qual plano você quer?"), a
resposta que não bate no formato da etapa nem como pergunta respondível
passa pelo classificador de intenção ANTES de contar como confusão (ou de
dizer que não achou o plano): se a pessoa pediu OUTRA das 4 tarefas, o
fluxo troca em vez de insistir na pergunta. Nada foi executado ainda,
então a etapa pendente é abandonada em silêncio.

Determinístico: interpretador e classificador de intenção são
substituídos por stubs — nenhuma chamada de API.

Uso: python teste_troca_tarefa.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import fluxos  # noqa: E402
from fluxos import MSG_ATENDENTE, Sessao, roteia  # noqa: E402

# ---- stubs -------------------------------------------------------------
# interpreta: por padrão nunca resolve o desvio (é o caso que leva ao
# classificador de intenção). intencao: devolve o que o caso pedir e
# registra as chamadas — casos que NÃO podem gastar uma chamada de API
# conferem essa lista.
CFG = {"interpreta": {"tipo": "nao_entendi"},
       "intencao": "FORA_DE_ESCOPO",
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
# abertura + passos levam a sessão até a etapa alvo; cada desvio é uma
# (mensagem, intenção que o classificador devolveria).
CASOS = [
    {"nome": "cancelamento GUIADO na confirmação de intenção → sinal",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "desvios": [("na verdade meu sinal tá ruim", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "RECLAMAR_SINAL", "etapa": "sinal_confirmar_problema",
                "confusas": 0, "marcador": "não está funcionando direito",
                "chamadas": 1}},

    {"nome": "cancelamento INTERMEDIARIO no aviso de cobrança → sinal",
     "caminho": "INTERMEDIARIO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": [("meu sinal tá ruim", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "RECLAMAR_SINAL", "etapa": "sinal_confirmar_abertura",
                "confusas": 0, "marcador": "chamado técnico", "chamadas": 1}},

    {"nome": "cancelamento GUIADO no aviso de cobrança → fatura",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": ["sim"],
     "etapa_alvo": "cancel_confirmar_aviso",
     "desvios": [("queria ver minha fatura", "CONSULTAR_FATURA")],
     "espera": {"tarefa": "CONSULTAR_FATURA", "etapa": "fatura_confirmar",
                "confusas": 0, "marcador": "valor da", "chamadas": 1}},

    {"nome": "sinal GUIADO na confirmação do problema → troca de plano",
     "caminho": "GUIADO", "tarefa": "RECLAMAR_SINAL",
     "abertura": "meu celular não pega", "passos": [],
     "etapa_alvo": "sinal_confirmar_problema",
     "desvios": [("quero trocar de plano", "TROCAR_PLANO")],
     "espera": {"tarefa": "TROCAR_PLANO", "etapa": "confirmar_intencao",
                "confusas": 0, "marcador": "mexer no seu plano",
                "chamadas": 1}},

    {"nome": "sinal GUIADO no 'posso abrir o chamado?' → cancelamento",
     "caminho": "GUIADO", "tarefa": "RECLAMAR_SINAL",
     "abertura": "meu celular não pega", "passos": ["sim"],
     "etapa_alvo": "sinal_confirmar_abertura",
     "desvios": [("melhor cancelar essa linha", "CANCELAR_LINHA")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_intencao",
                "confusas": 0, "marcador": "CANCELAR", "chamadas": 1}},

    {"nome": "sinal INTERMEDIARIO no 'posso abrir o chamado?' → cancelamento",
     "caminho": "INTERMEDIARIO", "tarefa": "RECLAMAR_SINAL",
     "abertura": "meu celular não pega", "passos": [],
     "etapa_alvo": "sinal_confirmar_abertura",
     "desvios": [("melhor cancelar essa linha", "CANCELAR_LINHA")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 0, "marcador": "cobrança proporcional",
                "chamadas": 1}},

    {"nome": "fatura GUIADO na confirmação → cancelamento",
     "caminho": "GUIADO", "tarefa": "CONSULTAR_FATURA",
     "abertura": "quanto veio minha conta", "passos": [],
     "etapa_alvo": "fatura_confirmar",
     "desvios": [("quero cancelar a linha", "CANCELAR_LINHA")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_intencao",
                "confusas": 0, "marcador": "CANCELAR", "chamadas": 1}},

    {"nome": "troca GUIADO na confirmação de intenção → sinal",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": [],
     "etapa_alvo": "confirmar_intencao",
     "desvios": [("meu sinal tá ruim", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "RECLAMAR_SINAL", "etapa": "sinal_confirmar_problema",
                "confusas": 0, "marcador": "não está funcionando direito",
                "chamadas": 1}},

    {"nome": "troca GUIADO na confirmação da troca → sinal (plano some)",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["sim", "2"],
     "etapa_alvo": "confirmar_troca",
     "desvios": [("meu sinal tá ruim", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "RECLAMAR_SINAL", "etapa": "sinal_confirmar_problema",
                "confusas": 0, "marcador": "não está funcionando direito",
                "chamadas": 1, "plano_escolhido": "", "plano_atual": "basico"}},

    {"nome": "troca INTERMEDIARIO na confirmação da troca → fatura resolvida",
     "caminho": "INTERMEDIARIO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["2"],
     "etapa_alvo": "confirmar_troca",
     "desvios": [("quanto tá minha conta?", "CONSULTAR_FATURA")],
     "espera": {"tarefa": "", "etapa": "", "confusas": 0, "marcador": "🧾",
                "chamadas": 1, "plano_atual": "basico",
                "concluidas": ["CONSULTAR_FATURA"]}},

    # --- sem troca: mantém o comportamento antigo ---
    {"nome": "mesma tarefa detectada → não troca, conta confusão",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "desvios": [("sei lá isso aí de cancelar", "CANCELAR_LINHA")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_intencao",
                "confusas": 1, "marcador": "não entendi", "chamadas": 1}},

    {"nome": "FORA_DE_ESCOPO (ou falha da API) → não troca, conta confusão",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "desvios": [("onde fica a loja de vocês", "FORA_DE_ESCOPO")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_intencao",
                "confusas": 1, "marcador": "não entendi", "chamadas": 1}},

    {"nome": "2 confusões seguidas ainda oferecem atendente",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "desvios": [("hmmm", "FORA_DE_ESCOPO"), ("ahn", "FORA_DE_ESCOPO")],
     "espera": {"tarefa": "", "etapa": "", "confusas": 0,
                "marcador": MSG_ATENDENTE, "chamadas": 2}},

    {"nome": "sim continua sim — não gasta chamada de intenção",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "desvios": [("sim", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_aviso",
                "confusas": 0, "marcador": "cobrança proporcional",
                "chamadas": 0}},

    {"nome": "pergunta respondível vem antes — não gasta chamada de intenção",
     "caminho": "GUIADO", "tarefa": "CANCELAR_LINHA",
     "abertura": "quero cancelar minha linha", "passos": [],
     "etapa_alvo": "cancel_confirmar_intencao",
     "interpreta": {"tipo": "pergunta",
                    "resposta": "A cobrança proporcional é de R$ 15,00."},
     "desvios": [("quanto vou pagar?", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_intencao",
                "confusas": 0, "marcador": "R$ 15,00", "chamadas": 0}},

    # --- escolha de plano: mesmo padrão da confirmação SIM/NÃO ---
    {"nome": "escolha de plano GUIADO → cancelamento (o caso do relato)",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["sim"],
     "etapa_alvo": "escolher",
     "desvios": [("cancelar minha linha", "CANCELAR_LINHA")],
     "espera": {"tarefa": "CANCELAR_LINHA", "etapa": "cancel_confirmar_intencao",
                "confusas": 0, "marcador": "CANCELAR", "chamadas": 1}},

    {"nome": "escolha de plano INTERMEDIARIO → sinal (some o 'não achei')",
     "caminho": "INTERMEDIARIO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": [],
     "etapa_alvo": "escolher",
     "desvios": [("meu sinal tá ruim", "RECLAMAR_SINAL")],
     "espera": {"tarefa": "RECLAMAR_SINAL", "etapa": "sinal_confirmar_abertura",
                "confusas": 0, "marcador": "chamado técnico", "chamadas": 1}},

    {"nome": "escolha de plano DIRETO → fatura resolvida",
     "caminho": "DIRETO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": [],
     "etapa_alvo": "escolher",
     "desvios": [("quanto tá minha conta?", "CONSULTAR_FATURA")],
     "espera": {"tarefa": "", "etapa": "", "confusas": 0, "marcador": "🧾",
                "chamadas": 1, "plano_atual": "basico",
                "concluidas": ["CONSULTAR_FATURA"]}},

    {"nome": "escolha de plano: mesma tarefa → não troca, conta confusão",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["sim"],
     "etapa_alvo": "escolher",
     "desvios": [("sei lá qual plano", "TROCAR_PLANO")],
     "espera": {"tarefa": "TROCAR_PLANO", "etapa": "escolher",
                "confusas": 1, "marcador": "não entendi", "chamadas": 1}},

    {"nome": "escolha de plano: FORA_DE_ESCOPO → não troca, conta confusão",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["sim"],
     "etapa_alvo": "escolher",
     "desvios": [("onde fica a loja de vocês", "FORA_DE_ESCOPO")],
     "espera": {"tarefa": "TROCAR_PLANO", "etapa": "escolher",
                "confusas": 1, "marcador": "não entendi", "chamadas": 1}},

    {"nome": "número do plano continua escolha — não gasta chamada",
     "caminho": "GUIADO", "tarefa": "TROCAR_PLANO",
     "abertura": "quero mudar meu plano", "passos": ["sim"],
     "etapa_alvo": "escolher",
     "desvios": [("2", "CANCELAR_LINHA")],
     "espera": {"tarefa": "TROCAR_PLANO", "etapa": "confirmar_troca",
                "confusas": 0, "plano_escolhido": "plus", "chamadas": 0}},
]


def _roda_caso(caso) -> list[str]:
    CFG["interpreta"] = caso.get("interpreta", {"tipo": "nao_entendi"})
    CFG["intencao"] = "FORA_DE_ESCOPO"
    CFG["chamadas"] = []

    sessao = Sessao()
    roteia(sessao, caso["abertura"], caso["caminho"], caso["tarefa"])
    for passo in caso["passos"]:
        roteia(sessao, passo, caso["caminho"], sessao.tarefa)

    erros = []
    if sessao.etapa != caso["etapa_alvo"]:
        return [f"preparo falhou: etapa {sessao.etapa!r}, "
                f"esperada {caso['etapa_alvo']!r}"]

    CFG["chamadas"] = []  # só conta as chamadas do desvio
    resposta = ""
    for mensagem, intencao in caso["desvios"]:
        CFG["intencao"] = intencao
        resposta = roteia(sessao, mensagem, caso["caminho"], sessao.tarefa)

    e = caso["espera"]
    obtido = {"tarefa": sessao.tarefa, "etapa": sessao.etapa,
              "confusas": sessao.confusas_seguidas,
              "chamadas": len(CFG["chamadas"]),
              "plano_escolhido": sessao.plano_escolhido,
              "plano_atual": sessao.plano_atual,
              "concluidas": sessao.tarefas_concluidas}
    for chave, esperado in e.items():
        if chave == "marcador":
            if esperado not in resposta:
                erros.append(f"resposta não contém {esperado[:40]!r}")
        elif obtido[chave] != esperado:
            erros.append(f"{chave}={obtido[chave]!r}, esperado {esperado!r}")
    return erros


def _caso_confirmacao_repeticao() -> list[str]:
    """A confirmação de repetir tarefa (sem fluxo ativo) não passa pelo
    classificador interno: quem decide ali é a intenção que o bot já
    classificou pra ESTA mensagem."""
    CFG["interpreta"] = {"tipo": "nao_entendi"}
    CFG["intencao"] = "FORA_DE_ESCOPO"
    CFG["chamadas"] = []

    sessao = Sessao(tarefas_concluidas=["CONSULTAR_FATURA"])
    r1 = roteia(sessao, "quanto tá minha conta?", "INTERMEDIARIO",
                "CONSULTAR_FATURA")
    erros = []
    if "repetir" not in r1:
        erros.append(f"não pediu confirmação de repetição: {r1[:60]!r}")
    r2 = roteia(sessao, "meu sinal tá ruim", "INTERMEDIARIO", "RECLAMAR_SINAL")
    if sessao.tarefa != "RECLAMAR_SINAL":
        erros.append(f"não trocou pro sinal: tarefa={sessao.tarefa!r}")
    if "chamado" not in r2:
        erros.append(f"resposta não abriu o fluxo de sinal: {r2[:60]!r}")
    if CFG["chamadas"]:
        erros.append(f"gastou {len(CFG['chamadas'])} chamada(s) de intenção "
                     f"na confirmação de repetição")
    return erros


def main():
    resultados = []
    for caso in CASOS:
        resultados.append((caso["nome"], _roda_caso(caso)))
    resultados.append(("confirmação de repetição segue como antes",
                       _caso_confirmacao_repeticao()))

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
