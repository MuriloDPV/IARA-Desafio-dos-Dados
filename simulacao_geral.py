"""Simulação geral: 9 personas fictícias contra o pipeline completo,
sem Telegram real. Gera transcript legível pra revisão humana antes da
gravação. Usa a API real (gpt-5.4-nano) — volume pequeno.

Uso: python simulacao_geral.py

Não corrige nada automaticamente: imprime a conversa, o nível INAF, o
caminho e a tarefa de cada interação, e fecha cada persona com
"✅ comportamento esperado" ou "⚠️ revisar: ...".
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import asyncio  # noqa: E402
import sys  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import bot  # noqa: E402
import dados  # noqa: E402
import estado  # noqa: E402
import fluxos  # noqa: E402

# ---- espiões: registram o que os classificadores devolveram (e fallbacks)
registro_inaf: list[tuple[str, dict]] = []
registro_intencao: list[tuple[str, str]] = []
fallbacks: list[str] = []

_classifica_orig = bot.classifica
_intencao_orig = bot.identifica_intencao


def _classifica_espiao(msg):
    r = _classifica_orig(msg)
    registro_inaf.append((msg, r))
    if "fallback" in r.get("justificativa", ""):
        fallbacks.append(f"INAF caiu em fallback na msg: {msg!r}")
    return r


def _intencao_espiao(msg):
    t = _intencao_orig(msg)
    registro_intencao.append((msg, t))
    return t


bot.classifica = _classifica_espiao
bot.identifica_intencao = _intencao_espiao
# fluxos também classifica intenção: na confirmação SIM/NÃO, quando a
# resposta não é sim, não nem pergunta respondível (troca de tarefa)
fluxos.identifica_intencao = _intencao_espiao

# Plano do cadastro novo FIXO aqui: os roteiros são escritos ("o do meio")
# e travariam se o sorteio calhasse de dar o plano que a persona já tem —
# o fluxo devolve "esse é o plano que você já tem hoje" e nunca conclui.
# O sorteio de verdade é verificado em _check_sorteio_planos().
bot.sorteia_plano = lambda: "basico"


class FakeMsg:
    def __init__(self):
        self.enviadas = []

    async def reply_text(self, t):
        self.enviadas.append(t)


class FakeUpdate:
    def __init__(self, chat_id):
        self.msg = FakeMsg()

        class C:
            id = chat_id
        self.effective_chat = C()
        self.message = self.msg


def _indenta(texto, prefixo="   │ "):
    return "\n".join(prefixo + l for l in texto.splitlines())


async def manda(u, texto):
    antes_inaf = len(registro_inaf)
    antes_int = len(registro_intencao)
    await bot._responde(u, texto, "texto")
    resposta = u.msg.enviadas[-1]
    print(f"\n   👤 {texto}")
    novos = registro_inaf[antes_inaf:]
    if novos:
        r = novos[-1][1]
        tarefa = registro_intencao[antes_int:]
        t = tarefa[-1][1] if tarefa else "(fluxo ativo)"
        print(f"      [INAF: {r['nivel']} → {r['caminho']} | intenção: {t}]")
    print(_indenta(f"🤖 {resposta}", "   "))
    return resposta


async def roda_persona(p):
    print("\n" + "=" * 72)
    print(f"PERSONA: {p['nome']}")
    print(f"esperado: {p['descricao_esperado']}")
    print("=" * 72)

    u = FakeUpdate(p["chat"])
    inaf_antes = len(registro_inaf)
    int_antes = len(registro_intencao)
    avisos = []
    ultima = ""

    for passo in p["roteiro"]:
        if passo[0] == "m":
            ultima = await manda(u, passo[1])
        elif passo[0] == "ate":
            _, marcador, resposta = passo
            tentativas = 0
            while marcador not in ultima and tentativas < 4:
                ultima = await manda(u, resposta)
                tentativas += 1
        elif passo[0] == "check":
            aviso = passo[1](u, bot.sessoes.get(p["chat"]))
            if aviso:
                avisos.append(aviso)

    esperado = p["esperado"]

    # caminho/nível da 1ª classificação de tarefa da persona
    classificacoes = registro_inaf[inaf_antes:]
    if esperado.get("caminhos"):
        if not classificacoes:
            avisos.append("nenhuma classificação INAF registrada")
        else:
            caminho = classificacoes[0][1]["caminho"]
            if caminho not in esperado["caminhos"]:
                avisos.append(f"caminho {caminho}, esperado "
                              f"{'/'.join(sorted(esperado['caminhos']))}")

    intencoes = [t for _, t in registro_intencao[int_antes:]]
    for tarefa in esperado.get("tarefas", []):
        if tarefa not in intencoes:
            avisos.append(f"intenção {tarefa} não foi detectada "
                          f"(detectadas: {intencoes})")

    for marcador in esperado.get("marcadores", []):
        if not any(marcador in r for r in u.msg.enviadas):
            avisos.append(f"resposta esperada não apareceu: {marcador!r}")

    if avisos:
        print(f"\n   ⚠️ revisar: " + "; ".join(avisos))
    else:
        print(f"\n   ✅ comportamento esperado")
    return (p["nome"], avisos)


# ------------------------------------------------------------- personas

def _check_sem_confusao(u, sessao):
    if sessao and sessao.confusas_seguidas != 0:
        return f"pergunta contou como confusão ({sessao.confusas_seguidas})"
    return None


def _check_resposta_com_preco_basico(u, sessao):
    if "R$ 30,00" not in u.msg.enviadas[-1]:
        return "interpretador não respondeu o preço do Básico"
    return None


def _check_sorteio_planos():
    """Cadastro novo sorteia entre os 3 planos. Como as personas rodam com
    o sorteio fixado, ele é conferido aqui direto na função real."""
    vistos = {dados.sorteia_plano() for _ in range(60)}
    if vistos != set(dados.ORDEM_PLANOS):
        return f"sorteio não cobriu os 3 planos em 60 tentativas: {sorted(vistos)}"
    return None


_atendimentos_p7 = []


def _anota_atendimento(u, sessao):
    if sessao:
        _atendimentos_p7.append(sessao.atendimento)
    return None


def _check_dois_atendimentos(u, sessao):
    if len(set(_atendimentos_p7)) != 2:
        return f"esperados 2 nºs de atendimento, veio {sorted(set(_atendimentos_p7))}"
    return None


def _check_trocou_pro_sinal(u, sessao):
    if not sessao or sessao.tarefa != "RECLAMAR_SINAL":
        return (f"não trocou pro fluxo de sinal "
                f"(tarefa={sessao.tarefa if sessao else None!r})")
    return None


def _check_sem_atendente(u, sessao):
    if "atendente humano" in u.msg.enviadas[-1]:
        return "caiu no atendente humano em vez de trocar de tarefa"
    return None


def _check_reclamacao_reconhecida(u, sessao):
    """Reclamar do valor não é responder: o bot reconhece a reclamação,
    repete a pergunta e NÃO decide nada sozinho."""
    ultima = u.msg.enviadas[-1]
    problemas = []
    if "Entendo que é um valor a mais" not in ultima:
        problemas.append("não reconheceu a reclamação antes de repetir")
    if "quer seguir com o cancelamento" not in ultima:
        problemas.append("não repetiu a pergunta da etapa")
    for indevido in ("abortado", "continua ativa", "Cancelamento registrado"):
        if indevido in ultima:
            problemas.append(f"decidiu sozinho: resposta traz {indevido!r}")
    if not sessao or sessao.etapa != "cancel_confirmar_aviso":
        problemas.append(f"saiu da confirmação "
                         f"(etapa={sessao.etapa if sessao else None!r})")
    return "; ".join(problemas) or None


PERSONAS = [
    {"nome": "1. Dona Marli — baixo letramento, troca de plano",
     "chat": 101,
     "descricao_esperado": "GUIADO / TROCAR_PLANO / troca concluída",
     "esperado": {"caminhos": {"GUIADO"}, "tarefas": ["TROCAR_PLANO"],
                  "marcadores": ["Pronto"]},
     "roteiro": [("m", "oi moço tudo bem"),
                 ("m", "marli"),
                 ("m", "aa moço sei la ta caro demais isso queria paga "
                       "mais barato num entendo desses plano"),
                 ("ate", "1.", "é sim"),
                 ("m", "o do meio pode ser"),
                 ("ate", "Pronto", "pode ser")]},

    {"nome": "2. Seu João — elementar, consulta de fatura",
     "chat": 102,
     "descricao_esperado": "INTERMEDIARIO / CONSULTAR_FATURA / fatura R$ 50",
     "esperado": {"caminhos": {"INTERMEDIARIO"},
                  "tarefas": ["CONSULTAR_FATURA"],
                  "marcadores": ["R$ 50,00"]},
     "roteiro": [("m", "oi"),
                 ("m", "11988881111"),
                 ("m", "1111"),
                 ("m", "queria saber quanto veio minha conta esse mês"),
                 ("ate", "R$ 50,00", "sim")]},

    {"nome": "3. Camila — intermediário, reclamação de sinal",
     "chat": 103,
     "descricao_esperado": "INTERMEDIARIO ou DIRETO / RECLAMAR_SINAL / protocolo",
     "esperado": {"caminhos": {"INTERMEDIARIO", "DIRETO"},
                  "tarefas": ["RECLAMAR_SINAL"],
                  "marcadores": ["Protocolo: 2026"]},
     "roteiro": [("m", "boa tarde"),
                 ("m", "sou a camila"),
                 ("m", "meu celular tá sem sinal aqui em casa desde ontem, "
                       "consegue verificar pra mim?"),
                 ("ate", "Protocolo: 2026", "sim, pode")]},

    {"nome": "4. Dr. Ricardo — proficiente, cancelamento",
     "chat": 104,
     "descricao_esperado": "DIRETO / CANCELAR_LINHA / protocolo de cancelamento",
     "esperado": {"caminhos": {"DIRETO"}, "tarefas": ["CANCELAR_LINHA"],
                  "marcadores": ["Cancelamento registrado"]},
     "roteiro": [("m", "boa tarde"),
                 ("m", "11966663333"),
                 ("m", "3333"),
                 ("m", "Quero cancelar definitivamente a linha do plano "
                       "Premium 50GB. Estou ciente da cobrança proporcional; "
                       "pode processar e me informar o protocolo."),
                 ("ate", "cobrança proporcional", "sim"),
                 ("ate", "Cancelamento registrado", "sim")]},

    {"nome": "5. Paula — desvio: pergunta no meio do fluxo",
     "chat": 105,
     "descricao_esperado": "pergunta respondida com dado real, sem contar confusão",
     "esperado": {"caminhos": set(), "tarefas": ["TROCAR_PLANO"],
                  "marcadores": ["Pronto"]},
     "roteiro": [("m", "oi"),
                 ("m", "paula"),
                 ("m", "quero trocar meu plano"),
                 ("ate", "1.", "sim"),
                 ("m", "qual o mais barato?"),
                 ("check", _check_resposta_com_preco_basico),
                 ("check", _check_sem_confusao),
                 ("m", "o do meio então"),
                 ("ate", "Pronto", "pode ser")]},

    {"nome": "6. Pedro — fora de escopo (portabilidade)",
     "chat": 106,
     "descricao_esperado": "bot admite o limite do protótipo, sem adivinhar",
     "esperado": {"caminhos": set(), "tarefas": ["FORA_DE_ESCOPO"],
                  "marcadores": ["demonstração cobre"]},
     "roteiro": [("m", "olá"),
                 ("m", "pedro"),
                 ("m", "quero passar meu número pra outra operadora")]},

    {"nome": "7. Multi-atendimento — Maria (fatura) + Rosa (sinal)",
     "chat": 107,
     "descricao_esperado": "2 atendimentos separados na mesma conversa",
     "esperado": {"caminhos": set(),
                  "tarefas": ["CONSULTAR_FATURA", "RECLAMAR_SINAL"],
                  "marcadores": ["R$ 30,00", "Protocolo: 2026",
                                 "nova solicitação"]},
     "roteiro": [("m", "oi"),
                 ("m", "11999990000"),
                 ("m", "0000"),
                 ("m", "quanto tá minha conta?"),
                 ("ate", "R$ 30,00", "sim"),
                 ("check", _anota_atendimento),
                 ("m", "novo atendimento"),
                 ("check", _anota_atendimento),
                 ("m", "11977772222"),
                 ("m", "2222"),
                 ("m", "meu chip tá sem sinal faz umas duas horas"),
                 ("ate", "Protocolo: 2026", "sim"),
                 ("check", _check_dois_atendimentos)]},

    {"nome": "8. Antônio — muda de ideia na confirmação SIM/NÃO",
     "chat": 108,
     "descricao_esperado": "pede outra tarefa na confirmação do cancelamento: "
                           "troca pro fluxo de sinal, sem confusão nem atendente",
     "esperado": {"caminhos": {"GUIADO", "INTERMEDIARIO"},
                  "tarefas": ["CANCELAR_LINHA", "RECLAMAR_SINAL"],
                  "marcadores": ["Protocolo: 2026"]},
     "roteiro": [("m", "oi"),
                 ("m", "antonio"),
                 ("m", "quero cancelar minha linha"),
                 ("m", "na verdade quero reclamar do sinal"),
                 ("check", _check_trocou_pro_sinal),
                 ("check", _check_sem_confusao),
                 ("check", _check_sem_atendente),
                 ("ate", "Protocolo: 2026", "sim")]},

    {"nome": "9. Seu João — reclama do valor na confirmação do cancelamento",
     "chat": 109,
     "descricao_esperado": "reclamação de preço não vira 'não': o bot "
                           "reconhece, repete a pergunta e segue quando ele "
                           "confirma",
     "esperado": {"caminhos": {"GUIADO", "INTERMEDIARIO"},
                  "tarefas": ["CANCELAR_LINHA"],
                  "marcadores": ["Entendo que é um valor a mais",
                                 "Cancelamento registrado"]},
     "roteiro": [("m", "oi"),
                 ("m", "11988881111"),
                 ("m", "1111"),
                 ("m", "quero cancelar minha linha"),
                 ("ate", "cobrança proporcional", "sim"),
                 ("m", "25 reais muito caro"),
                 ("check", _check_reclamacao_reconhecida),
                 ("ate", "Cancelamento registrado", "sim")]},
]


async def main():
    bot.sessoes.clear()
    estado.inicializa()
    resultados = []
    for p in PERSONAS:
        resultados.append(await roda_persona(p))

    print("\n" + "=" * 72)
    print("RESUMO GERAL")
    print("=" * 72)
    for nome, avisos in resultados:
        status = "✅" if not avisos else "⚠️"
        print(f"{status} {nome}")
        for a in avisos:
            print(f"     → {a}")
    aviso_sorteio = _check_sorteio_planos()
    if aviso_sorteio:
        print(f"⚠️ sorteio de plano do cadastro novo → {aviso_sorteio}")
    else:
        print("✅ sorteio de plano do cadastro novo cobre os 3 planos")

    if fallbacks:
        print("\n⚠️ FALLBACKS DE API DETECTADOS:")
        for f in fallbacks:
            print(f"   → {f}")
    else:
        print("\nNenhum fallback de API detectado (classificador INAF).")


if __name__ == "__main__":
    asyncio.run(main())
