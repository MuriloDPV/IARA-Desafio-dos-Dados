"""Os 3 caminhos de atendimento para a tarefa única: trocar de plano.

- GUIADO: passo a passo, confirma cada etapa; 2+ respostas confusas
  seguidas -> oferece atendente humano (mensagem simulada, sem integração).
- INTERMEDIARIO: passo a passo mais rápido, menos confirmação.
- DIRETO: resolve em 1 mensagem quando possível.

O estado da sessão vive só na memória do processo do bot e é descartado
ao fim de cada fluxo — a classificação é refeita a cada nova conversa.
"""

import random
import re
from dataclasses import dataclass, field

from dados import (CLIENTE_TESTE, PLANOS, acha_plano, acha_planos,
                   lista_planos_texto)
from intencao import identifica_intencao
from interprete import interpreta

MSG_ATENDENTE = ("Percebi que está um pouco difícil por aqui, e tudo bem! 😊\n"
                 "Vou te conectar com um atendente humano pra te ajudar.\n"
                 "\n"
                 "(atendimento simulado — te conectando com um humano pra "
                 "essa parte. Se quiser pedir outra coisa, pode falar "
                 "comigo direto.)")

MSG_FORA_ESCOPO = ("Essa demonstração cobre só 4 coisas: trocar de plano, "
                   "consultar a fatura, reclamar de sinal e cancelar a "
                   "linha. 🙂\n"
                   "\n"
                   "Em outros casos, eu te conectaria com um atendente humano "
                   "(simulado). Posso ajudar com alguma dessas 4?")

MSG_NAO_ENTENDI = ("Desculpa, não entendi sua resposta. Vamos tentar de novo, "
                   "com calma. 😊")

MSG_MULTIPLOS_PLANOS = ("Nesta demonstração, cada cadastro tem só 1 plano — "
                        "não modelamos múltiplas linhas por pessoa. 🙂\n\n"
                        "Posso ajudar com o seu plano atual: trocar de "
                        "plano, ver a fatura, reclamar do sinal ou cancelar "
                        "a linha.")

DIA_VENCIMENTO = 10  # fictício

MSG_FECHAMENTO = ("\n\nPrecisa de mais alguma coisa? Se for pra outra linha "
                  "ou pessoa, digite 'novo atendimento' que eu atendo "
                  "separado.")

NOMES_TAREFA = {"TROCAR_PLANO": "a troca de plano",
                "CONSULTAR_FATURA": "a consulta de fatura",
                "RECLAMAR_SINAL": "a reclamação de sinal",
                "CANCELAR_LINHA": "o cancelamento da linha"}

# Despedidas/agradecimentos comuns após o fechamento — lista fixa
DESPEDIDAS = {"obrigado", "obrigada", "brigado", "brigada", "muito obrigado",
              "muito obrigada", "obrigado viu", "obrigada viu", "valeu",
              "valeu mesmo", "só isso", "so isso", "só isso mesmo",
              "so isso mesmo", "era só isso", "era so isso", "é só isso",
              "e só isso", "e so isso", "tchau", "tchau tchau", "até mais",
              "ate mais", "até logo", "ate logo", "falou", "de nada"}

# Recusa do "Precisa de mais alguma coisa?": só vale como despedida DEPOIS de
# uma tarefa concluída — é resposta a uma oferta de ajuda. Sem tarefa
# concluída não há oferta pra recusar, e "não obrigado" segue pro
# fora-de-escopo. Vírgula e acento saem na normalização de pontuação, então
# "não, obrigado" e "nao obrigado" caem nas mesmas chaves.
DESPEDIDAS_POS_TAREFA = {"não obrigado", "nao obrigado",
                         "não obrigada", "nao obrigada",
                         "não", "nao", "não precisa", "nao precisa", "nada"}

MSG_DESPEDIDA = "Por nada! 😊 Se precisar de algo mais, é só chamar."

# Emoji de fechamento. Depois de uma tarefa concluída, um deles sozinho é
# resposta ao "precisa de mais alguma coisa?" — vale como despedida, igual
# a "obrigado". Fora desse contexto não sustenta nada sozinho e vale só
# como cola ("obrigado 👍" segue despedida; "👍" solto, não).
# Guardados como um caractere só: o seletor de variação (❤️ = ❤ + U+FE0F)
# e o tom de pele (👍🏽) saem em _normaliza_resposta.
EMOJI_FECHAMENTO = {"👍", "👌", "🙏", "❤", "😊", "🙂"}

# modificadores que grudam no emoji sem mudar qual emoji é: seletores de
# variação (FE0E/FE0F) e os 5 tons de pele (1F3FB-1F3FF)
_MODIFICADORES_EMOJI = ({chr(0xFE0F), chr(0xFE0E)}
                        | {chr(c) for c in range(0x1F3FB, 0x1F400)})

# Palavras sem conteúdo que grudam na despedida sem mudar o sentido
# ("ok, obrigado", "tá bom, valeu mesmo", "obrigado por tudo"). A lista é
# curta de propósito: tudo que não está aqui nem nas listas acima sobra na
# decomposição e derruba o match. "não" fica de fora — quem decide se
# "não obrigado" vale é DESPEDIDAS_POS_TAREFA.
COLA_DESPEDIDA = {"ok", "okay", "ta", "tá", "bom", "blz", "beleza", "certo",
                  "então", "entao", "pronto", "aí", "ai", "viu", "hein",
                  "mesmo", "muito", "e", "por", "tudo", "era", "isso"}

# maior frase das listas, em palavras — derivado, não fixo, pra continuar
# certo se alguém acrescentar uma despedida mais longa
_MAX_TERMO_DESPEDIDA = max(len(t.split())
                           for t in DESPEDIDAS | DESPEDIDAS_POS_TAREFA)


@dataclass
class Sessao:
    caminho: str = ""            # vazio = nenhum fluxo ativo
    etapa: str = ""
    plano_escolhido: str = ""
    confusas_seguidas: int = 0
    plano_atual: str = field(default=CLIENTE_TESTE["plano_atual"])
    # v2 — identificação + tarefa ativa
    tarefa: str = ""             # TROCAR_PLANO / CONSULTAR_FATURA / RECLAMAR_SINAL
    # direção dita na mensagem de abertura da troca: barato / capacidade / ""
    preferencia: str = ""
    nivel: str = ""              # nível INAF fixado no início do fluxo ativo
    identificado: bool = False
    apresentou: bool = False     # a Iara já se apresentou neste atendimento
    pediu_id: bool = False
    pediu_4dig: bool = False     # aguardando o check simulado de 4 dígitos
    msg_pendente: str = ""       # 1ª mensagem guardada até a identificação
    # intenção JÁ classificada para msg_pendente: a 1ª mensagem passa pelo
    # classificador uma vez só. Reclassificar o mesmo texto na retomada
    # seria um segundo sorteio do modelo, que pode discordar do primeiro —
    # a Iara prometeria uma tarefa ("vou te ajudar com...") e entregaria
    # outra (ou o fora-de-escopo). Anda sempre junto com msg_pendente.
    tarefa_pendente: str = ""
    # cópia do cliente fictício da sessão — teatro da conversa, some no fim
    cliente: dict = field(default_factory=lambda: dict(CLIENTE_TESTE))
    atendimento: int = 0         # nº sequencial da sessão (pro painel)
    # tarefas já concluídas NESTE atendimento + confirmação de repetição
    tarefas_concluidas: list = field(default_factory=list)
    repetir_tarefa: str = ""
    repetir_caminho: str = ""


# Variação leve da frase de reconhecimento que ABRE a resposta depois de
# um SIM. Só a saudação muda — o texto informativo que vem em seguida
# (preço, plano, prazo) é sempre idêntico, palavra por palavra. Duas
# gravações da demo não saem decoradas iguais sem que nada de conteúdo
# mude junto.
#
# Escopo fechado de propósito: nenhum destes carrega dado, e o
# cancelamento fica de fora inteiro — "Show!" depois de "quer cancelar
# sua linha? SIM" seria comemorar a perda da linha da pessoa.
_ACEITE_ANIMADO = ("Que bom!", "Perfeito!", "Show!")
_RECONHECIMENTO = ("Entendi.", "Certo.", "Beleza.")


def _nome(chave: str) -> str:
    return PLANOS[chave]["nome"]


def _preco(chave: str) -> str:
    return f"R$ {PLANOS[chave]['preco']:.2f}".replace(".", ",")


def _normaliza_resposta(t: str) -> str:
    """Transcrição de áudio vem com pontuação ("Sim, pode.") — normaliza
    antes do match determinístico. Tira também os modificadores do emoji,
    pra "👍", "👍🏽" e "❤️" virarem a mesma chave."""
    t = t.lower().strip()
    for ch in ".,!?;:":
        t = t.replace(ch, " ")
    t = "".join(ch for ch in t if ch not in _MODIFICADORES_EMOJI)
    return " ".join(t.split())


def _so_emoji_de_fechamento(palavra: str) -> bool:
    """Token feito só de emoji de fechamento ("👍", "👍👍", "🙏❤️")."""
    return bool(palavra) and all(ch in EMOJI_FECHAMENTO for ch in palavra)


def _e_despedida(texto: str, pos_tarefa: bool) -> bool:
    """A mensagem INTEIRA se decompõe em termos de despedida (+ cola)?

    Igualdade exata contra a lista só pegava a frase inteira, então cada
    combinação nova ("era só isso obrigado", "valeu, tchau") precisava
    virar uma entrada. Aqui a mensagem é consumida termo a termo, o que
    cobre qualquer combinação e ordem sem precisar prever nenhuma.

    Não é "contém um termo": substring transformaria "trocar de plano,
    obrigado" em despedida e engoliria o pedido de tarefa. O que separa
    os dois casos é a sobra — em "era só isso obrigado" não sobra
    palavra nenhuma; em "trocar de plano, obrigado" sobra "trocar de
    plano", e sobra com conteúdo significa que não é despedida.
    """
    termos = DESPEDIDAS | DESPEDIDAS_POS_TAREFA if pos_tarefa else DESPEDIDAS
    palavras = _normaliza_resposta(texto).split()
    i, achou_termo = 0, False
    while i < len(palavras):
        # casa a frase mais longa possível a partir daqui: "era só isso"
        # antes de "isso", "não obrigado" antes de "obrigado"
        for n in range(min(_MAX_TERMO_DESPEDIDA, len(palavras) - i), 0, -1):
            if " ".join(palavras[i:i + n]) in termos:
                achou_termo = True
                i += n
                break
        else:
            if _so_emoji_de_fechamento(palavras[i]):
                # depois de uma tarefa concluída o emoji encerra sozinho
                # (é resposta à oferta de ajuda); antes disso é só cola
                achou_termo = achou_termo or pos_tarefa
            elif palavras[i] not in COLA_DESPEDIDA:
                return False
            i += 1
    # só cola ("ok", "beleza") não é despedida: exige um termo de verdade
    return achou_termo


_SIMS = {"sim", "s", "isso", "isso aí", "isso ai", "isso mesmo", "isso aí mesmo",
         "é isso", "e isso", "é isso mesmo", "e isso mesmo", "é sim", "e sim",
         "sim sim", "quero", "pode", "pode ser", "pode sim", "sim pode",
         "ok", "confirmo", "confirma", "claro", "claro que sim", "com certeza",
         "certeza", "uhum", "aham", "é", "e", "sim quero", "beleza", "bora",
         "aceito", "vamos", "quero sim", "sim por favor"}

# "cancela"/"cancelar" NÃO entram aqui: no fluxo de cancelamento seriam um
# SIM — fica pro interpretador decidir pelo contexto da pergunta da etapa
_NAOS = {"não", "nao", "n", "não quero", "nao quero", "não obrigado",
         "nao obrigado", "não obrigada", "nao obrigada", "deixa",
         "deixa pra lá", "deixa pra la", "melhor não", "melhor nao",
         "agora não", "agora nao", "não deixa", "nao deixa", "não né",
         "nao ne", "não precisa", "nao precisa"}


def _eh_sim(t: str) -> bool:
    return _normaliza_resposta(t) in _SIMS


def _eh_nao(t: str) -> bool:
    return _normaliza_resposta(t) in _NAOS


# Pedido EXPLÍCITO de atendente humano: escala na hora, em qualquer etapa
# — mecanismo separado e mais forte que a oferta de atendente por 2
# confusões seguidas (essa continua existindo pra quem nunca pede
# diretamente). Termos de 1 palavra casam por TOKEN inteiro (não
# substring), pra "humano" não disparar dentro de "desumano"/"humanoide";
# termos de mais de 1 palavra casam por substring da frase normalizada,
# que já é específico o bastante.
_TERMOS_ATENDENTE_HUMANO = {"atendente", "humano", "pessoa de verdade",
                            "gente de verdade"}


def _pede_atendente_humano(texto: str) -> bool:
    normalizado = _normaliza_resposta(texto)
    palavras = normalizado.split()
    for termo in _TERMOS_ATENDENTE_HUMANO:
        if " " in termo:
            if termo in normalizado:
                return True
        elif termo in palavras:
            return True
    return False


# Pergunta sobre EXISTÊNCIA de mais de um plano/linha no cadastro ("só
# tenho este?", "tenho outro no meu nome?", "quantas linhas eu tenho?") —
# achado na investigação de 2026-09-15: o classificador de intenção
# oscilava entre CONSULTAR_FATURA / TROCAR_PLANO / FORA_DE_ESCOPO pras
# MESMAS frases, e a consulta de fatura só pede confirmação SIM/NÃO no
# caminho GUIADO — então o comportamento também variava conforme o
# classificador INAF (instável na mesma fronteira Rudimentar x Elementar)
# caía pra cada frase. Mesmo quando CONSULTAR_FATURA "ganhava", a resposta
# (valor da fatura) não respondia a pergunta — o protótipo modela 1 único
# plano por cliente (`plano_atual` em dados.py, sem lista), então não há
# dado de "outro plano no nome" pra consultar de verdade.
#
# Checado ANTES de `tarefa`/`caminho` (INAF) serem usados pra rotear —
# mesmo padrão de `_pede_desconto`/`_pede_atendente_humano`: a resposta é
# sempre a mesma, fixa, em qualquer nível de letramento.
#
# Âncora num verbo de posse/existência ("tenho", "possuo", "existe"...)
# perto de "outro/mais de um plano": sem isso, "quero trocar para outro
# plano" (TROCAR_PLANO de verdade) seria engolido também.
_RE_TEM_OUTRO_PLANO = re.compile(
    r"\b(tenho|possuo|existe|teria|h[aá])\b.{0,15}"
    r"\b(outr[oa]|mais de um|mais de uma)\b.{0,10}\b(plano|linha)")
_RE_SO_TENHO_PLANO = re.compile(r"\bs[oó] tenho\b.{0,20}\b(plano|linha)s?\b")
_RE_QUANTOS_PLANOS = re.compile(
    r"\bquant[ao]s?\b.{0,15}\b(planos?|linhas?)\b.{0,20}\btenho\b")


def _pergunta_multiplos_planos(texto: str) -> bool:
    normalizado = _normaliza_resposta(texto)
    return bool(_RE_TEM_OUTRO_PLANO.search(normalizado)
                or _RE_SO_TENHO_PLANO.search(normalizado)
                or _RE_QUANTOS_PLANOS.search(normalizado))


# ------------------------------------------- interpretação flexível
# Quando o padrão fixo da etapa não casa, o modelo decide se foi uma
# resposta válida dita de outro jeito, uma pergunta respondível com
# dados que o sistema já tem, ou confusão de verdade.

def _dados_sistema(sessao: "Sessao") -> str:
    atual = sessao.plano_atual
    pendente = ""
    if sessao.plano_escolhido:
        pendente = (f"Plano PENDENTE DE CONFIRMAÇÃO nesta etapa: "
                    f"{_nome(sessao.plano_escolhido)} por "
                    f"{_preco(sessao.plano_escolhido)}/mês\n")
    return (pendente +
            f"Planos disponíveis (franquia e preço):\n{lista_planos_texto()}\n"
            f"Plano atual do cliente: {_nome(atual)} por {_preco(atual)}/mês\n"
            f"Fatura atual: {_preco(atual)}, vencimento dia {DIA_VENCIMENTO}\n"
            f"Prazo de chamado técnico: até 24 horas\n"
            f"Cancelamento da linha: cobrança proporcional de "
            f"{_preco_proporcional(sessao)} até o fechamento da fatura; "
            f"linha desativa em até 24 horas após o protocolo")


def _flexivel(sessao: "Sessao", texto: str, pergunta: str,
              tipo: str) -> tuple[str | None, str | None]:
    """(valor_normalizado, None) se resposta válida; (None, resposta_pronta)
    se pergunta respondida com dado do sistema; (None, None) se confusão."""
    r = interpreta(pergunta, tipo, _dados_sistema(sessao), texto)
    if r.get("tipo") == "resposta_valida":
        return str(r.get("valor", "")).lower().strip(), None
    if r.get("tipo") == "pergunta" and r.get("resposta"):
        return None, f"{r['resposta']}\n\n{pergunta}"
    return None, None


def _extrai_preferencia(sessao: "Sessao", texto: str) -> str:
    """Direção de custo/capacidade dita na mensagem que ABRE a troca de
    plano. Mesmo interpretador do desvio "tem mais barato" da etapa de
    escolha, só que aplicado à abertura. Erro de API ou preferência
    ausente caem em "" — lista neutra, comportamento antigo."""
    r = interpreta("Qual plano o cliente quer?", "preferencia_plano",
                   _dados_sistema(sessao), texto)
    valor = str(r.get("valor", "")).lower().strip()
    if r.get("tipo") == "preferencia" and valor in ("barato", "capacidade"):
        return valor
    return ""


def _prefixo_preferencia(sessao: "Sessao") -> str:
    """Reconhece em voz alta a direção que a pessoa já pediu, antes de
    listar. A lista continua completa — isso é um guia, não um filtro."""
    if sessao.preferencia == "barato":
        p = min(PLANOS, key=lambda k: PLANOS[k]["preco"])
        return (f"Como você quer pagar menos: o {_nome(p)} ({_preco(p)}) "
                f"já é o mais barato que temos.\n")
    if sessao.preferencia == "capacidade":
        p = max(PLANOS, key=lambda k: PLANOS[k]["gb"])
        return (f"Como você quer mais internet: o {_nome(p)} ({_preco(p)}) "
                f"é o de maior franquia.\n")
    return ""


def _outra_tarefa_pedida(sessao: "Sessao", texto: str) -> str | None:
    """A resposta que não bate no formato da etapa nem é pergunta
    respondível ainda pode ser o pedido de OUTRA tarefa: "quer cancelar a
    linha?" -> "na verdade meu sinal tá ruim"; "qual plano você quer?" ->
    "cancelar minha linha". Antes de contar como confusão (ou dizer que
    não achou o plano), roda o classificador de intenção na mensagem.

    Se vier uma das 4 tarefas e for DIFERENTE da que está em andamento,
    abandona a etapa pendente e devolve já a resposta da tarefa nova.
    Nada foi executado ainda, então não há o que desfazer nem o que
    avisar — mesmo padrão que roteia() usa quando alguém pede outra
    tarefa no meio da confirmação de repetição.

    Devolve None (e a etapa segue com o "não entendi" de sempre) quando:
    não há tarefa em andamento, a intenção é a MESMA tarefa, é
    FORA_DE_ESCOPO, ou o classificador falhou (que também cai em
    FORA_DE_ESCOPO).
    """
    # sem fluxo ativo não há confirmação de tarefa: é a confirmação de
    # repetição do roteia(), que já trata a troca por conta própria
    if not sessao.caminho or sessao.tarefa not in NOMES_TAREFA:
        return None
    nova = identifica_intencao(texto)
    if nova not in NOMES_TAREFA or nova == sessao.tarefa:
        return None
    caminho, nivel = sessao.caminho, sessao.nivel
    _encerra(sessao)
    sessao.nivel = nivel  # mesma pessoa, mesmo atendimento: o nível fica
    return roteia(sessao, texto, caminho, nova)


def _sim_nao(sessao: "Sessao", texto: str, pergunta: str,
             trocar_tarefa: bool = True) -> tuple[str | None, str | None]:
    """sim/não da etapa: determinístico primeiro, modelo só no desvio.

    O 2º item é a resposta pronta pra devolver sem contar confusão —
    ou a pergunta respondida com dado do sistema, ou a tarefa nova que a
    pessoa pediu no lugar de responder (ver _outra_tarefa_pedida).

    `trocar_tarefa=False` desliga só esse último passo: a mensagem já foi
    reconhecida como reação, não como pedido (ver _abertura_reacao)."""
    if _eh_sim(texto):
        return "sim", None
    if _eh_nao(texto):
        return "nao", None
    valor, pronto = _flexivel(sessao, texto, pergunta, "sim_nao")
    if valor in ("sim", "nao"):
        return valor, None
    if pronto:
        return None, pronto
    if not trocar_tarefa:
        return None, None
    return None, _outra_tarefa_pedida(sessao, texto)


def _parece_pergunta(t: str) -> bool:
    t = t.lower().strip()
    inicio = t.split()[0] if t.split() else ""
    return "?" in t or inicio in ("quanto", "quanta", "qual", "quais", "como",
                                  "quando", "onde", "cade", "cadê", "porque",
                                  "por", "tem", "existe")


# "o mais barato" / "mais em conta": seleção de alta confiança do plano de
# menor preço — equivale a digitar o número dele. Determinístico igual ao
# sim/não: tolera erro de digitação no resto da frase ("querto o mais
# barato") sem depender do modelo, que hoje devolve nao_entendi aqui.
_PEDIDOS_MAIS_BARATO = ("mais barato", "mais barata", "mais em conta",
                        "mais baratinho")


def _pede_o_mais_barato(t: str) -> bool:
    normalizado = _normaliza_resposta(t)
    return any(p in normalizado for p in _PEDIDOS_MAIS_BARATO)


def _plano_mais_barato() -> str:
    return min(PLANOS, key=lambda k: PLANOS[k]["preco"])


# Pedido de desconto PERSONALIZADO — bem diferente de "mais barato" (ver
# _pede_o_mais_barato acima), que É uma escolha determinística válida do
# plano de menor preço de tabela. Aqui a pessoa quer pagar menos SEM
# migrar pra um plano existente ("continuar com os 20gb" = ficar no Plus,
# só que mais barato) ou cita um valor arbitrário que não é preço de
# nenhum plano ("quero pagar 45" — nenhum plano custa isso). Não existe
# desconto personalizado nesta demonstração: a resposta é sempre a mesma,
# em qualquer nível de letramento.
#
# Checado ANTES de qualquer tentativa de casar a frase com plano/número
# (senão "20gb" é lido como "escolheu o Plus" e o bot troca de plano
# sozinho) e ANTES de `_outra_tarefa_pedida` rodar o classificador de
# intenção (senão "quero pagar 45" pode ser reclassificado como outra
# tarefa, ex. CONSULTAR_FATURA, e o bot abandona a troca de plano e pula
# pra lá em silêncio, sem confirmar nada com o cliente).
_PISTAS_DESCONTO = ("desconto", "pagar menos", "abaixar o valor",
                    "abaixar o preco", "abaixar o preço",
                    "diminuir o valor", "reduzir o valor")
_RE_PAGAR_VALOR = re.compile(r"\bpagar\s+\d+\b")


def _pede_desconto(texto: str) -> bool:
    normalizado = _normaliza_resposta(texto)
    if any(p in normalizado for p in _PISTAS_DESCONTO):
        return True
    if "mais barato" in normalizado and "continuar" in normalizado:
        return True
    return bool(_RE_PAGAR_VALOR.search(normalizado))


def _resposta_desconto() -> str:
    return ("Não trabalhamos com desconto personalizado, mas temos estes "
            f"planos:\n{lista_planos_texto()}")


def _escolhe_plano(sessao: "Sessao", texto: str,
                   pergunta: str) -> tuple[str | None, str | None]:
    """Escolha de plano da etapa: determinístico primeiro — EXCETO quando a
    mensagem parece pergunta ("quanto custa o plus?") ou é longa/ruidosa
    (transcrição de áudio misturando assuntos), senão um nome de plano
    citado no meio seria engolido como escolha.

    O 2º item é a resposta pronta pra devolver sem contar confusão — ou a
    pergunta respondida com dado do sistema, ou a tarefa nova que a pessoa
    pediu no lugar de escolher um plano (ver _outra_tarefa_pedida). Mesmo
    padrão da confirmação SIM/NÃO: quem diz "cancelar minha linha" no meio
    da lista está pedindo outra coisa, não errando o número do plano."""
    if _pede_desconto(texto):
        return None, _resposta_desconto()
    if not _parece_pergunta(texto) and len(texto) <= 100:
        plano = acha_plano(texto)
        if plano:
            return plano, None
        # depois do nome/número explícito, e só fora do guard de pergunta:
        # "qual o mais barato?" continua sendo pergunta respondida com dado
        # real, não escolha
        if _pede_o_mais_barato(texto):
            return _plano_mais_barato(), None
    valor, pronto = _flexivel(sessao, texto, pergunta, "escolha_plano")
    if valor in PLANOS:
        return valor, None
    if pronto:
        return None, pronto
    # interpretador não resolveu: última chance determinística
    plano = acha_plano(texto)
    if plano:
        return plano, None
    # nem plano nem pergunta respondível: antes do "não achei esse plano",
    # o classificador de intenção decide se foi pedido de outra tarefa
    return None, _outra_tarefa_pedida(sessao, texto)


def _troca_efetivada(sessao: Sessao) -> str:
    antigo = sessao.plano_atual
    sessao.plano_atual = sessao.plano_escolhido
    sessao.cliente["plano_atual"] = sessao.plano_escolhido  # só na sessão
    novo = sessao.plano_escolhido
    return _finaliza(sessao, (
        f"✅ Pronto, {sessao.cliente['nome'].split()[0]}! Seu plano foi trocado:\n"
        f"antes: {_nome(antigo)}\n"
        f"agora: {_nome(novo)} por {_preco(novo)}/mês\n"
        f"(troca simulada para a demonstração)"))


def _encerra(sessao: Sessao):
    sessao.caminho = ""
    sessao.etapa = ""
    sessao.plano_escolhido = ""
    sessao.confusas_seguidas = 0
    sessao.tarefa = ""
    sessao.nivel = ""


def _finaliza(sessao: Sessao, texto: str) -> str:
    """Conclusão de tarefa: registra na sessão (pra trava de repetição),
    encerra o fluxo e anexa o fechamento padrão."""
    if sessao.tarefa and sessao.tarefa not in sessao.tarefas_concluidas:
        sessao.tarefas_concluidas.append(sessao.tarefa)
    _encerra(sessao)
    return texto + MSG_FECHAMENTO


def processa(sessao: Sessao, texto: str, caminho_estimado: str) -> str:
    """Recebe a mensagem e devolve a resposta do bot.

    Se não há fluxo ativo, inicia um novo no caminho estimado para ESTA
    mensagem. Se há fluxo ativo, continua nele até concluir.
    """
    if _pede_atendente_humano(texto):
        _encerra(sessao)
        return MSG_ATENDENTE

    if _pergunta_multiplos_planos(texto):
        return MSG_MULTIPLOS_PLANOS

    if not sessao.caminho:
        sessao.caminho = caminho_estimado
        return _inicia(sessao, texto)

    if sessao.caminho == "GUIADO":
        return _continua_guiado(sessao, texto)
    if sessao.caminho == "INTERMEDIARIO":
        return _continua_intermediario(sessao, texto)
    return _continua_direto(sessao, texto)


# ---------------------------------------------------------------- início

def _inicia(sessao: Sessao, texto: str) -> str:
    nome = sessao.cliente["nome"].split()[0]
    atual = sessao.plano_atual

    if sessao.caminho == "DIRETO":
        # checagem de desconto ANTES do atalho de troca direta: senão
        # "continuar com os 20gb" citado na abertura seria lido como
        # "escolheu o Plus" e o bot trocaria de plano sozinho.
        if _pede_desconto(texto):
            sessao.etapa = "escolher"
            return _resposta_desconto()
        # "migrar do Básico para o Premium" cita 2 planos: o alvo é o
        # citado que NÃO é o plano atual (o último, se houver mais de um)
        alvos = [p for p in acha_planos(texto) if p != atual]
        if alvos:
            sessao.plano_escolhido = alvos[-1]
            return _troca_efetivada(sessao)
        sessao.etapa = "escolher"
        return (f"Seu plano atual é o {_nome(atual)} ({_preco(atual)}/mês).\n\n"
                f"{_prefixo_preferencia(sessao)}Opções disponíveis:\n"
                f"{lista_planos_texto()}\n\n"
                f"Qual deseja ativar?")

    if sessao.caminho == "INTERMEDIARIO":
        sessao.etapa = "escolher"
        return (f"Vamos trocar seu plano, {nome}! 👍\n\n"
                f"Hoje você tem o {_nome(atual)} ({_preco(atual)}/mês).\n"
                f"{_prefixo_preferencia(sessao)}"
                f"Estes são os planos:\n{lista_planos_texto()}\n\n"
                f"Me diga o número ou o nome do plano que você quer.")

    # GUIADO
    sessao.etapa = "confirmar_intencao"
    return (f"{nome}, eu vou te ajudar com calma, sem pressa. 😊\n\n"
            f"Pelo que entendi, você quer mexer no seu plano de celular "
            f"(o pacote de internet e ligações que você paga por mês).\n\n"
            f"É isso mesmo? Responda SIM ou NÃO.")


# ---------------------------------------------------------------- guiado

def _confusa_guiado(sessao: Sessao, pergunta_de_novo: str,
                    abertura: str = "") -> str:
    """`abertura` troca SÓ a frase de transição (ver _abertura_reacao). O
    resto do fallback é o mesmo pra todas as etapas: conta a confusão,
    repete a pergunta e oferece atendente na 2ª seguida.

    Não precisa checar `_pede_atendente_humano` aqui: só se chega até
    aqui vindo de `processa`, que só chama `_continua_guiado` depois da
    própria checagem já ter passado — um pedido explícito nunca sobrevive
    pra virar "confusão"."""
    sessao.confusas_seguidas += 1
    if sessao.confusas_seguidas >= 2:
        _encerra(sessao)
        return MSG_ATENDENTE
    return f"{abertura or MSG_NAO_ENTENDI}\n{pergunta_de_novo}"


def _continua_guiado(sessao: Sessao, texto: str) -> str:
    atual = sessao.plano_atual

    if sessao.etapa == "confirmar_intencao":
        pergunta = "Você quer mexer no seu plano de celular? Responda SIM ou NÃO."
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            sessao.confusas_seguidas = 0
            sessao.etapa = "escolher"
            return (f"{random.choice(_ACEITE_ANIMADO)} Hoje você paga o "
                    f"plano {_nome(atual)}, "
                    f"que custa {_preco(atual)} por mês.\n\n"
                    f"{_prefixo_preferencia(sessao)}"
                    f"Estes são os planos que existem:\n{lista_planos_texto()}\n\n"
                    f"Me responda só com o NÚMERO do plano que você quer "
                    f"(1, 2 ou 3).")
        if resp == "nao":
            _encerra(sessao)
            return ("Sem problema! Aqui eu consigo te ajudar a trocar de plano.\n\n"
                    "Se for outra coisa, posso te passar para um atendente humano — "
                    "é só escrever ATENDENTE.")
        if pronto:
            return pronto  # pergunta respondida com dado real: não conta confusão
        return _confusa_guiado(sessao, pergunta)

    if sessao.etapa == "escolher":
        pergunta = f"Me responda só com o número do plano:\n{lista_planos_texto()}"
        plano, pronto = _escolhe_plano(sessao, texto, pergunta)
        if plano:
            sessao.confusas_seguidas = 0
            if plano == atual:
                return (f"Esse é o plano que você já tem hoje ({_nome(atual)}).\n\n"
                        f"Quer escolher um diferente? Responda com o número:\n"
                        f"{lista_planos_texto()}")
            sessao.plano_escolhido = plano
            sessao.etapa = "confirmar_troca"
            return (f"Você escolheu o plano {_nome(plano)}, que custa "
                    f"{_preco(plano)} por mês.\n\n"
                    f"Posso fazer a troca agora? Responda SIM ou NÃO.")
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta)

    if sessao.etapa == "confirmar_troca":
        pergunta = (f"Só pra confirmar: trocar para o "
                    f"{_nome(sessao.plano_escolhido)} "
                    f"({_preco(sessao.plano_escolhido)}/mês)? "
                    f"Responda SIM ou NÃO.")
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            return _troca_efetivada(sessao)
        if resp == "nao":
            sessao.etapa = "escolher"
            sessao.confusas_seguidas = 0
            return (f"Tudo bem, nada foi trocado ainda.\n\n"
                    f"Quer escolher outro?\n"
                    f"{lista_planos_texto()}\nResponda com o número.")
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta)

    _encerra(sessao)
    return "Vamos recomeçar: me diga o que você precisa. 😊"


# ---------------------------------------------------------- intermediário

def _continua_intermediario(sessao: Sessao, texto: str) -> str:
    if sessao.etapa == "escolher":
        pergunta = f"Me diga o número ou o nome do plano:\n{lista_planos_texto()}"
        plano, pronto = _escolhe_plano(sessao, texto, pergunta)
        if plano and plano != sessao.plano_atual:
            sessao.plano_escolhido = plano
            sessao.etapa = "confirmar_troca"
            return (f"Trocar para o {_nome(plano)} por {_preco(plano)}/mês — "
                    f"confirma? (sim/não)")
        if plano == sessao.plano_atual:
            return f"Esse já é seu plano atual. Escolha outro:\n{lista_planos_texto()}"
        if pronto:
            return pronto
        return f"Não achei esse plano. {pergunta}"

    if sessao.etapa == "confirmar_troca":
        pergunta = (f"Confirma a troca para o {_nome(sessao.plano_escolhido)} "
                    f"({_preco(sessao.plano_escolhido)}/mês)? (sim/não)")
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            return _troca_efetivada(sessao)
        if resp == "nao":
            sessao.etapa = "escolher"
            return f"Ok, cancelado. Se quiser, escolha outro:\n{lista_planos_texto()}"
        if pronto:
            return pronto
        return f"Só preciso de um sim ou não. {pergunta}"

    _encerra(sessao)
    return "Me diga o que você precisa que eu te ajudo!"


# ----------------------------------------------------------------- direto

def _continua_direto(sessao: Sessao, texto: str) -> str:
    if sessao.etapa == "escolher":
        pergunta = f"Qual plano deseja ativar?\n{lista_planos_texto()}"
        plano, pronto = _escolhe_plano(sessao, texto, pergunta)
        if plano and plano != sessao.plano_atual:
            sessao.plano_escolhido = plano
            return _troca_efetivada(sessao)
        if plano == sessao.plano_atual:
            return f"Esse já é seu plano atual. Opções:\n{lista_planos_texto()}"
        if pronto:
            return pronto
        return f"Não identifiquei o plano. Opções:\n{lista_planos_texto()}"

    _encerra(sessao)
    return "Me diga qual plano deseja ativar."


# ============================================================ v2: roteador
# Entrada única do bot: decide a tarefa e reusa o mesmo padrão de
# adaptação por caminho. A lógica de troca de plano acima não muda.

def eh_despedida_ociosa(sessao: "Sessao", texto: str) -> bool:
    """Despedida/agradecimento com a sessão ociosa (sem fluxo ativo, sem
    repetição pendente) — mesma condição usada dentro de roteia() e, antes
    dela, em bot.py pra pular a classificação de intenção (economiza a
    chamada de API e evita que o evento grave FORA_DE_ESCOPO pra uma
    mensagem que era só despedida)."""
    return (not sessao.caminho and not sessao.repetir_tarefa
            and _e_despedida(texto, bool(sessao.tarefas_concluidas)))


def roteia(sessao: Sessao, texto: str, caminho_estimado: str, tarefa: str) -> str:
    if _pede_atendente_humano(texto):
        _encerra(sessao)
        return MSG_ATENDENTE

    if _pergunta_multiplos_planos(texto):
        return MSG_MULTIPLOS_PLANOS

    # despedida/agradecimento com a sessão ociosa: responde curto,
    # sem contar confusão nem acionar tarefa (nem cair no fora-de-escopo)
    if eh_despedida_ociosa(sessao, texto):
        return MSG_DESPEDIDA

    # fluxo em andamento continua até o fim, sem re-rotear
    if sessao.caminho:
        if sessao.tarefa == "CONSULTAR_FATURA":
            return _continua_fatura(sessao, texto)
        if sessao.tarefa == "RECLAMAR_SINAL":
            return _continua_sinal(sessao, texto)
        if sessao.tarefa == "CANCELAR_LINHA":
            return _continua_cancelamento(sessao, texto)
        return processa(sessao, texto, caminho_estimado)

    # confirmação pendente de repetir tarefa já concluída
    if sessao.repetir_tarefa:
        pergunta = (f"Quer mesmo repetir {NOMES_TAREFA[sessao.repetir_tarefa]} "
                    f"pra esse mesmo cadastro? Responda SIM ou NÃO.")
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            t, c = sessao.repetir_tarefa, sessao.repetir_caminho
            sessao.repetir_tarefa = ""
            sessao.repetir_caminho = ""
            return _inicia_tarefa(sessao, texto, c, t)
        if resp == "nao":
            sessao.repetir_tarefa = ""
            sessao.repetir_caminho = ""
            return "Tudo bem!" + MSG_FECHAMENTO
        if tarefa in NOMES_TAREFA and tarefa != sessao.repetir_tarefa:
            # pediu outra tarefa no meio: esquece a repetição e segue
            sessao.repetir_tarefa = ""
            sessao.repetir_caminho = ""
        else:
            if pronto:
                return pronto
            return pergunta

    # tarefa já concluída neste atendimento: avisa antes de repetir
    if tarefa in sessao.tarefas_concluidas:
        sessao.repetir_tarefa = tarefa
        sessao.repetir_caminho = caminho_estimado
        return (f"Você já concluiu {NOMES_TAREFA[tarefa]} nesse atendimento "
                f"(protocolo/valor já informado acima). Se for pra outra "
                f"linha ou pessoa, digite 'novo atendimento' que eu "
                f"identifico ela separado.\n"
                f"Quer mesmo repetir pra esse mesmo cadastro? "
                f"Responda SIM ou NÃO.")

    return _inicia_tarefa(sessao, texto, caminho_estimado, tarefa)


def _inicia_tarefa(sessao: Sessao, texto: str, caminho: str, tarefa: str) -> str:
    if tarefa == "CONSULTAR_FATURA":
        sessao.tarefa = tarefa
        return _inicia_fatura(sessao, caminho)
    if tarefa == "RECLAMAR_SINAL":
        sessao.tarefa = tarefa
        return _inicia_sinal(sessao, caminho)
    if tarefa == "CANCELAR_LINHA":
        sessao.tarefa = tarefa
        return _inicia_cancelamento(sessao, caminho)
    if tarefa == "TROCAR_PLANO":
        sessao.tarefa = tarefa
        # Lida 1x, na abertura: no GUIADO a lista só aparece um turno
        # depois (após confirmar a intenção), quando o texto original já
        # não está mais em mãos. No DIRETO com plano já nomeado a troca
        # sai sem passar por lista nenhuma — aí a chamada seria perdida.
        atalho_direto = (caminho == "DIRETO" and
                         any(p != sessao.plano_atual for p in acha_planos(texto)))
        sessao.preferencia = ("" if atalho_direto
                              else _extrai_preferencia(sessao, texto))
        return processa(sessao, texto, caminho)

    return MSG_FORA_ESCOPO


# ------------------------------------------------------------- fatura

def _texto_fatura(sessao: Sessao) -> str:
    atual = sessao.plano_atual
    return (f"🧾 Sua fatura atual é de {_preco(atual)} "
            f"(plano {_nome(atual)}), com vencimento dia {DIA_VENCIMENTO}.\n\n"
            f"(consulta simulada para a demonstração)")


def _inicia_fatura(sessao: Sessao, caminho: str) -> str:
    sessao.caminho = caminho
    nome = sessao.cliente["nome"].split()[0]
    if caminho == "GUIADO":
        sessao.etapa = "fatura_confirmar"
        return (f"{nome}, pelo que entendi, você quer saber o valor da "
                f"sua conta (a fatura que chega todo mês).\n\n"
                f"É isso mesmo? Responda SIM ou NÃO.")
    # INTERMEDIARIO e DIRETO: resolve em 1 mensagem
    return _finaliza(sessao, _texto_fatura(sessao))


def _continua_fatura(sessao: Sessao, texto: str) -> str:
    if sessao.etapa == "fatura_confirmar":
        pergunta = "Você quer ver o valor da sua conta? Responda SIM ou NÃO."
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            return _finaliza(sessao, _texto_fatura(sessao))
        if resp == "nao":
            _encerra(sessao)
            return ("Sem problema! Me conte o que você precisa: trocar de "
                    "plano, ver a fatura ou reclamar do sinal.")
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta)
    return _finaliza(sessao, _texto_fatura(sessao))


# -------------------------------------------------------------- sinal

def _protocolo() -> str:
    return f"2026{random.randint(100000, 999999)}"


def _texto_chamado_aberto() -> str:
    return (f"🔧 Chamado técnico aberto!\n"
            f"Protocolo: {_protocolo()}\n"
            f"Previsão de atendimento: até 24 horas.\n\n"
            f"(chamado simulado para a demonstração)")


def _inicia_sinal(sessao: Sessao, caminho: str) -> str:
    sessao.caminho = caminho
    nome = sessao.cliente["nome"].split()[0]
    if caminho == "DIRETO":
        return _finaliza(sessao, _texto_chamado_aberto())
    if caminho == "INTERMEDIARIO":
        sessao.etapa = "sinal_confirmar_abertura"
        return (f"Poxa, {nome}, sinto muito pelo problema no sinal. 😕\n\n"
                f"Quer que eu abra um chamado técnico agora? (sim/não)")
    # GUIADO: confirma o problema antes, depois confirma a abertura
    sessao.etapa = "sinal_confirmar_problema"
    return (f"{nome}, pelo que entendi, seu telefone ou sua internet "
            f"não está funcionando direito.\n\n"
            f"É isso mesmo? Responda SIM ou NÃO.")


def _continua_sinal(sessao: Sessao, texto: str) -> str:
    if sessao.etapa == "sinal_confirmar_problema":
        pergunta = ("Seu telefone ou internet está com problema? "
                    "Responda SIM ou NÃO.")
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            sessao.confusas_seguidas = 0
            sessao.etapa = "sinal_confirmar_abertura"
            return (f"{random.choice(_RECONHECIMENTO)} Eu posso chamar os "
                    f"técnicos pra verificarem isso pra você, sem custo.\n\n"
                    f"Posso abrir o chamado? Responda SIM ou NÃO.")
        if resp == "nao":
            _encerra(sessao)
            return ("Tudo bem! Me conte então o que você precisa: trocar de "
                    "plano, ver a fatura ou reclamar do sinal.")
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta)

    if sessao.etapa == "sinal_confirmar_abertura":
        pergunta = "Posso abrir o chamado técnico? Responda SIM ou NÃO."
        resp, pronto = _sim_nao(sessao, texto, pergunta)
        if resp == "sim":
            return _finaliza(sessao, _texto_chamado_aberto())
        if resp == "nao":
            _encerra(sessao)
            return "Ok, nenhum chamado foi aberto. Qualquer coisa é só chamar!"
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta)

    return _finaliza(sessao, _texto_chamado_aberto())


# ------------------------------------------------------- cancelar linha
# confirma intenção -> aviso de cobrança proporcional (fictícia) ->
# confirmação (sim/não) -> protocolo

def _preco_proporcional(sessao: Sessao) -> str:
    valor = PLANOS[sessao.plano_atual]["preco"] / 2  # proporcional fictício
    return f"R$ {valor:.2f}".replace(".", ",")


def _aviso_proporcional(sessao: Sessao) -> str:
    return (f"⚠️ Antes de cancelar: existe uma cobrança proporcional de "
            f"{_preco_proporcional(sessao)} pelo uso até o fechamento da "
            f"fatura (dia {DIA_VENCIMENTO}).")


def _texto_cancelado(sessao: Sessao) -> str:
    return _finaliza(sessao, (
        f"❌ Cancelamento registrado.\n"
        f"Protocolo: {_protocolo()}\n"
        f"Sua linha será desativada em até 24 horas.\n\n"
        f"(cancelamento simulado para a demonstração — nada foi "
        f"cancelado de verdade)"))


def _inicia_cancelamento(sessao: Sessao, caminho: str) -> str:
    sessao.caminho = caminho
    nome = sessao.cliente["nome"].split()[0]
    if caminho == "DIRETO":
        sessao.etapa = "cancel_confirmar_aviso"
        return (f"Entendido, {nome}. {_aviso_proporcional(sessao)}\n\n"
                f"Mesmo assim quer cancelar? (sim/não)")
    if caminho == "INTERMEDIARIO":
        sessao.etapa = "cancel_confirmar_aviso"
        return (f"{nome}, vamos lá. {_aviso_proporcional(sessao)}\n\n"
                f"Mesmo assim quer cancelar? (sim/não)")
    # GUIADO: confirma a intenção antes de qualquer aviso
    sessao.etapa = "cancel_confirmar_intencao"
    return (f"Oi, {nome}. Só pra eu ter certeza: você quer CANCELAR a sua "
            f"linha de celular — ou seja, seu número deixaria de funcionar.\n\n"
            f"É isso mesmo? Responda SIM ou NÃO.")


# Reclamação/reação nas confirmações SIM/NÃO do cancelamento. A mensagem
# ainda passa pelo sim/não determinístico e pelo interpretador — quem
# reclama E responde ("tá caro, mas pode cancelar") continua sendo lido
# como resposta. O que muda é o que acontece quando sobra só a reação: em
# vez do "não entendi" genérico, uma frase curta reconhece a reclamação
# antes de repetir a pergunta. O fallback em si é idêntico (conta
# confusão, repete a pergunta, oferece atendente na 2ª seguida).
# Determinístico de propósito: nenhuma chamada de API a mais só pra
# escolher a frase.
#
# Escopo fechado nesta confirmação: nas outras etapas o "não entendi"
# segue como sempre. Isto é texto de transição, não é o bot "entendendo
# objeção" e decidindo alguma coisa por conta própria.
_REACAO_VALOR = {"caro", "caros", "cara", "carissimo", "caríssimo",
                 "carissima", "caríssima", "salgado", "salgada", "abusivo",
                 "abusiva", "absurdo", "absurda", "roubo", "extorsao",
                 "extorsão"}
_REACAO_VALOR_FRASES = ("não vale", "nao vale", "não compensa", "nao compensa",
                        "não tenho condição", "nao tenho condicao",
                        "sem condição", "sem condicao", "muito dinheiro")
# reação sem ser ao preço: chateação com o atendimento/serviço
_REACAO_CHATEACAO = {"péssimo", "pessimo", "péssima", "pessima", "horrível",
                     "horrivel", "palhaçada", "palhacada", "revoltante",
                     "chateado", "chateada", "revoltado", "revoltada",
                     "indignado", "indignada"}

# Pedido de outra tarefa dito JUNTO com a reclamação ("tá caro, quero
# trocar de plano"): aí não é reação pura — segue pelo caminho normal, que
# roda o classificador de intenção e troca de tarefa. Sem essa checagem,
# "25 reais muito caro" sozinho vira TROCAR_PLANO no classificador e o
# cancelamento é abandonado sem ninguém ter pedido.
_PISTAS_TAREFA = {"trocar", "troca", "trocando", "mudar", "muda", "mudando",
                  "migrar", "plano", "planos", "fatura", "boleto", "conta",
                  "sinal", "internet", "chamado", "técnico", "tecnico",
                  "cancelar", "cancela", "cancelamento", "encerrar",
                  "atendente", "portabilidade"}


def _abertura_reacao(texto: str, sobre_cobranca: bool) -> str:
    """Frase curta que reconhece a reclamação antes de repetir a pergunta.

    Devolve "" — e aí vale o "não entendi" padrão, com troca de tarefa e
    tudo — quando não houve reclamação nenhuma ou quando ela veio junto
    com o pedido de outra tarefa."""
    normalizado = _normaliza_resposta(texto)
    palavras = set(normalizado.split())
    if palavras & _PISTAS_TAREFA:
        return ""
    if (palavras & _REACAO_VALOR
            or any(f in normalizado for f in _REACAO_VALOR_FRASES)):
        return ("Entendo que é um valor a mais, sim." if sobre_cobranca
                else "Entendo que o valor pesa, sim.")
    if palavras & _REACAO_CHATEACAO:
        return "Entendo a sua chateação, e sinto muito por isso."
    return ""


def _continua_cancelamento(sessao: Sessao, texto: str) -> str:
    if sessao.etapa == "cancel_confirmar_intencao":
        pergunta = "Você quer cancelar a sua linha? Responda SIM ou NÃO."
        reacao = _abertura_reacao(texto, sobre_cobranca=False)
        resp, pronto = _sim_nao(sessao, texto, pergunta,
                                trocar_tarefa=not reacao)
        if resp == "sim":
            sessao.confusas_seguidas = 0
            sessao.etapa = "cancel_confirmar_aviso"
            return (f"Entendi. {_aviso_proporcional(sessao)}\n\n"
                    f"Mesmo sabendo disso, quer seguir com o cancelamento? "
                    f"Responda SIM ou NÃO.")
        if resp == "nao":
            _encerra(sessao)
            return ("Ufa, que bom! 😊 Sua linha continua ativa. Me conte se "
                    "precisa de outra coisa.")
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta, reacao)

    if sessao.etapa == "cancel_confirmar_aviso":
        pergunta = ("Mesmo com a cobrança proporcional, quer seguir com o "
                    "cancelamento? Responda SIM ou NÃO.")
        reacao = _abertura_reacao(texto, sobre_cobranca=True)
        resp, pronto = _sim_nao(sessao, texto, pergunta,
                                trocar_tarefa=not reacao)
        if resp == "sim":
            return _texto_cancelado(sessao)
        if resp == "nao":
            _encerra(sessao)
            return ("Cancelamento abortado — sua linha continua ativa. 😊\n\n"
                    "Precisa de mais alguma coisa?")
        if pronto:
            return pronto
        return _confusa_guiado(sessao, pergunta, reacao)

    _encerra(sessao)
    return "Vamos recomeçar: me diga o que você precisa. 😊"
