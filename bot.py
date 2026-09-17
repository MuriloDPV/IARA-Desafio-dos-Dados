"""Bot Telegram do Motor de Letramento Digital (protótipo de demonstração).

Pipeline por mensagem:
  texto (ou áudio -> transcrição) -> classificador INAF -> fluxo adaptado
  -> resposta + evento gravado no SQLite (lido pelo painel).

Rodar: python bot.py  (exige TELEGRAM_BOT_TOKEN e OPENAI_API_KEY no .env)
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import re

import estado
from classificador import classifica
from dados import (PLANOS, extrai_nome, identificacao_plausivel,
                   nome_ancorado, nome_plausivel, sorteia_plano, tem_letra)
from fluxos import (MSG_DESPEDIDA, MSG_FORA_ESCOPO, NOMES_TAREFA, Sessao,
                    eh_despedida_ociosa, roteia)
from intencao import identifica_intencao

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


class _MascaraCredenciais(logging.Filter):
    """Nenhum token/chave em texto puro no log (ex: URL da API do
    Telegram contém o token do bot)."""
    PADROES = (re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}"),
               re.compile(r"sk-[A-Za-z0-9_-]{10,}"))

    def filter(self, record):
        msg = record.getMessage()
        mascarado = msg
        for p in self.PADROES:
            mascarado = p.sub("***", mascarado)
        if mascarado != msg:
            record.msg = mascarado
            record.args = ()
        return True


for _h in logging.getLogger().handlers:
    _h.addFilter(_MascaraCredenciais())
# httpx loga a URL completa (com token) em INFO — só warnings pra cima
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

log = logging.getLogger("bot")

MODELO_TRANSCRICAO = "gpt-4o-mini-transcribe"

# Estado de conversa por chat, só em memória — some ao reiniciar o bot.
sessoes: dict[int, Sessao] = {}


def _sessao(chat_id: int) -> Sessao:
    if chat_id not in sessoes:
        s = Sessao()
        s.atendimento = estado.proximo_atendimento()
        sessoes[chat_id] = s
    return sessoes[chat_id]


MSG_START_CURTA = "🤖 Iara iniciada. Mande uma mensagem pra começar."
MSG_MENU = ("Como posso te ajudar? Posso: trocar seu plano, mostrar sua "
            "fatura, registrar uma reclamação de sinal ou cancelar sua "
            "linha.")

# Abertura da conversa: saudação + apresentação + as 4 capacidades, uma
# por parágrafo (linha em branco entre elas — no Telegram fica legível de
# relance, que é o que a demonstração precisa mostrar). O bloco termina
# SEM a última frase: quem chama decide o fecho — combinado com o
# reconhecimento de tarefa (quando há) e sempre com o pedido de
# identificação, porque é isso que dispara este bloco (ver _msg_pede_id).
BLOCO_ABERTURA = (
    "Oi! Que bom te ver por aqui. 😊\n"
    "Sou a Iara, assistente (de demonstração) da operadora — tô aqui pra "
    "te ajudar com seu plano de celular.\n"
    "\n"
    "Posso te ajudar com:\n"
    "\n"
    "📱 Trocar de plano\n"
    "\n"
    "🧾 Consultar sua fatura\n"
    "\n"
    "📡 Reclamar de sinal\n"
    "\n"
    "❌ Cancelar sua linha\n"
    "\n")


def _msg_pede_id(tarefa: str = "", apresentou: bool = False) -> str:
    """Pergunta de identificação. Com tarefa já reconhecida na 1ª
    mensagem, confirma que entendeu antes de pedir os dados — quem já
    disse o que quer não deve sentir que falou no vazio.

    A apresentação completa (bloco com as 4 capacidades) só entra se a
    Iara ainda não se apresentou neste atendimento — o /start agora só
    manda uma confirmação curta, então é a 1ª mensagem substantiva do
    cliente que dispara a apresentação completa, aqui dentro; repetir
    depois disso soa robótico, daí o corte por `apresentou`."""
    if tarefa:
        pedido = ("Só preciso te identificar antes — me diga seu nome ou o "
                  "número do seu telefone, sem pressa.")
        if apresentou:
            abertura = f"Claro, vou te ajudar com {NOMES_TAREFA[tarefa]}! 😊"
        else:
            # Tarefa já reconhecida na 1ª mensagem: marca + reconhecimento
            # específico, sem a lista genérica das 4 capacidades (BLOCO_
            # ABERTURA) — quem já disse o que quer não precisa do cardápio.
            abertura = (f"Oi! Sou a Iara, vou te ajudar com "
                        f"{NOMES_TAREFA[tarefa]}. 😊")
        return f"{abertura}\n\n{pedido}"
    if apresentou:
        # Esta mensagem também É o pedido de identificação (quem chama já
        # marcou pediu_id=True, e a resposta seguinte será lida como
        # nome). Convidar a "contar o que precisa" aqui faria a pessoa
        # mandar uma tarefa e ouvir "não consegui entender seu nome".
        return ("Oi! Pra eu te ajudar, me diga seu nome ou o número do "
                "seu telefone, sem pressa.")
    return (BLOCO_ABERTURA +
            "Pra eu te atender direitinho, me diga seu nome ou o número "
            "do seu telefone — sem pressa.")


async def _envia(update: Update, texto: str):
    """Envio com 1 retry em engasgo de rede: a demo é gravada ao vivo e
    um timeout de um segundo não pode derrubar o atendimento. Se a 2ª
    tentativa falhar, deixa subir (o PTB loga e o bot segue rodando).
    Nota: um TimedOut pode ocorrer com a mensagem já aceita pelo
    Telegram — nesse caso o retry duplica. Numa demo, mensagem repetida
    é bem menos ruim que atendimento travado."""
    try:
        await update.message.reply_text(texto)
    except (TimedOut, NetworkError) as e:
        log.warning("falha de rede no envio (%s) — tentando 1x de novo",
                    type(e).__name__)
        await asyncio.sleep(2)
        await update.message.reply_text(texto)

SAUDACOES = {"oi", "ola", "olá", "bom dia", "boa tarde", "boa noite", "opa",
             "eae", "e ai", "e aí", "hey", "hello", "oi bot", "oi tudo bem",
             "oi, tudo bem?", "tudo bem", "tudo bem?"}


def _eh_saudacao(texto: str) -> bool:
    return texto.lower().strip(" .,!?") in SAUDACOES


# Telefone brasileiro tem 8-9 dígitos (11 com DDD). O piso de 8 é o que
# separa telefone de número solto do próprio pedido ("20GB", "R$ 50").
MIN_DIGITOS_TELEFONE = 8


def _identificacao_embutida(texto: str) -> str:
    """O que a 1ª mensagem já traz de identificação, quando traz.

    Quem abre com "bom dia, meu nome é Murilo, quero cancelar meu plano"
    disse as duas coisas de uma vez — perguntar o nome depois disso é
    fazer a pessoa repetir o que acabou de falar.

    A frase inteira não serve como identificação: ela é o pedido. Só
    valem as duas partes que a própria pessoa marcou — o nome ancorado
    ("meu nome é X") e o telefone. Devolve essa parte isolada, que é o
    que segue para a identificação no lugar da mensagem toda; "" quando
    não há nenhuma das duas, e aí a pergunta separada acontece como
    antes. Nome solto não conta: aqui ninguém perguntou o nome, e
    qualquer palavra da frase viraria "nome"."""
    nome = nome_ancorado(texto)
    if nome:
        return nome
    digitos = re.sub(r"\D", "", texto)
    return digitos if len(digitos) >= MIN_DIGITOS_TELEFONE else ""


# Gatilho explícito de novo atendimento na mesma conversa (lista fixa e
# curta de propósito — sem interpretação livre de "troca de pessoa")
GATILHOS_NOVO_ATENDIMENTO = {"novo atendimento", "outro atendimento",
                             "atender outra pessoa"}


def _eh_novo_atendimento(texto: str) -> bool:
    t = texto.lower().strip()
    for ch in ".,!?;:":
        t = t.replace(ch, " ")
    return " ".join(t.split()) in GATILHOS_NOVO_ATENDIMENTO


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reseta a sessão e confirma que reiniciou, sem se apresentar ainda —
    a apresentação completa só vem na 1ª mensagem substantiva do cliente
    (ver `_msg_pede_id`), pra não gastar a apresentação com quem só
    testou o comando."""
    chat_id = update.effective_chat.id
    sessoes.pop(chat_id, None)
    _sessao(chat_id)
    await _envia(update, MSG_START_CURTA)


async def _classifica_tudo(sessao: Sessao, texto: str,
                           tarefa_conhecida: str = "") -> tuple[dict, str]:
    """Classifica INAF + intenção 1x quando a tarefa começa; com fluxo
    em andamento, mantém nível/caminho/tarefa fixados até o fim (sem
    chamada de API). Nada persiste entre conversas: /start ou fim do
    fluxo descartam e a próxima mensagem reclassifica do zero.

    `tarefa_conhecida` é a intenção já classificada para ESTE texto (a 1ª
    mensagem, guardada em tarefa_pendente antes da identificação): o INAF
    ainda roda, o classificador de intenção não roda de novo."""
    if sessao.caminho:
        return ({"nivel": sessao.nivel, "caminho": sessao.caminho,
                 "justificativa": ""}, sessao.tarefa)
    if tarefa_conhecida:
        resultado = await asyncio.to_thread(classifica, texto)
        tarefa = tarefa_conhecida
    else:
        resultado, tarefa = await asyncio.gather(
            asyncio.to_thread(classifica, texto),
            asyncio.to_thread(identifica_intencao, texto))
    sessao.nivel = resultado["nivel"]  # vale enquanto o fluxo durar
    return resultado, tarefa


async def _responde(update: Update, texto_usuario: str, origem: str):
    """Pipeline comum a texto e áudio: identifica (1x), classifica
    INAF + intenção, roda o fluxo, registra pro painel."""
    chat_id = update.effective_chat.id
    sessao = _sessao(chat_id)

    # --- "novo atendimento" na mesma conversa: só vale com tarefa
    # encerrada (nunca no meio de um fluxo). Reset igual ao /start, mas
    # sem a saudação cheia — vai direto pra identificação, com número
    # novo de atendimento (card novo no painel).
    if (sessao.identificado and not sessao.caminho
            and _eh_novo_atendimento(texto_usuario)):
        nova = Sessao()
        nova.atendimento = estado.proximo_atendimento()
        nova.pediu_id = True  # a pergunta de identificação já vai agora
        sessoes[chat_id] = nova
        msg = ("Certo, vamos começar um novo atendimento! 🔄\n\n"
               "Pra eu atender essa nova solicitação, me diga o nome ou "
               "o número de telefone.")
        await asyncio.to_thread(
            estado.registra_evento, origem, texto_usuario, "—", "—",
            msg, "IDENTIFICACAO", nova.atendimento,
            nome_cliente=nova.cliente.get("nome", ""))
        await _envia(update, msg)
        return

    # --- identificação simulada (1x por conversa): bate o número contra
    # a lista fixa de clientes fictícios; desconhecido vira "cadastro
    # novo" só desta conversa (nada persiste). Nome/telefone informados
    # NÃO vão pro log de eventos — o painel mostra só a etapa.
    MSG_ID_OMITIDA = "🪪 (dados de identificação não registrados)"

    if not sessao.identificado:
        # O que vale como identificação. Em geral é a mensagem inteira
        # (a pessoa está respondendo "qual seu nome?"); na 1ª mensagem,
        # que vem com o pedido junto, é só o pedaço identificador.
        texto_id = texto_usuario

        if not sessao.pediu_id:
            sessao.pediu_id = True
            # só guarda como pendente se a 1ª mensagem já é uma das 4
            # tarefas — abertura/saudação sem tarefa segue pro menu depois
            # de identificar, sem cair no texto de fora-de-escopo
            tarefa_inicial = ""
            if not _eh_saudacao(texto_usuario):
                intencao_inicial = await asyncio.to_thread(
                    identifica_intencao, texto_usuario)
                if intencao_inicial in NOMES_TAREFA:
                    sessao.msg_pendente = texto_usuario  # retoma após identificar
                    # guarda a intenção junto: na retomada o mesmo texto
                    # não passa pelo classificador uma segunda vez
                    sessao.tarefa_pendente = intencao_inicial
                    tarefa_inicial = intencao_inicial

            # A mensagem já se identificou sozinha? Então não há o que
            # perguntar: segue direto para a identificação abaixo, que
            # resolve tudo (e retoma a tarefa pendente) numa etapa só.
            embutida = _identificacao_embutida(texto_usuario)
            if not embutida:
                msg_id = _msg_pede_id(tarefa_inicial, sessao.apresentou)
                sessao.apresentou = True
                await asyncio.to_thread(
                    estado.registra_evento, origem, MSG_ID_OMITIDA, "—", "—",
                    msg_id, "IDENTIFICACAO", sessao.atendimento,
                    nome_cliente=sessao.cliente.get("nome", ""))
                await _envia(update, msg_id)
                return
            sessao.apresentou = True
            texto_id = embutida

        # Mesma resposta para toda identificação que não serve (texto
        # longo demais, só emoji, dígitos de menos): pede de novo sem
        # criar cadastro, sem avançar de etapa e sem ecoar nada do que
        # veio. Fica aqui em cima porque vale para as duas etapas.
        PEDE_DE_NOVO = ("Não consegui entender seu nome. Pode me mandar seu "
                        "nome ou telefone, por favor? 😊")

        async def _pede_identificacao_de_novo():
            await asyncio.to_thread(
                estado.registra_evento, origem, MSG_ID_OMITIDA, "—", "—",
                PEDE_DE_NOVO, "IDENTIFICACAO", sessao.atendimento,
                nome_cliente=sessao.cliente.get("nome", ""))
            await _envia(update, PEDE_DE_NOVO)

        async def _tenta_reconhecer_tarefa() -> bool:
            """Antes de desistir com "não consegui entender": classifica a
            mensagem original e, se for uma das 4 tarefas, guarda como
            pendente e reenvia o pedido de identificação já reconhecendo o
            que a pessoa quer. True se respondeu (recuperou); False se não
            há tarefa reconhecível — quem chama segue para o pedido
            genérico. No check dos 4 dígitos não entra (etapa de
            confirmação, corte absoluto), nem quando já há tarefa pendente
            (não reclassifica de novo)."""
            if sessao.pediu_4dig or sessao.tarefa_pendente:
                return False
            tarefa = await asyncio.to_thread(
                identifica_intencao, texto_usuario)
            if tarefa not in NOMES_TAREFA:
                return False
            sessao.msg_pendente = texto_usuario
            sessao.tarefa_pendente = tarefa
            msg_id = _msg_pede_id(tarefa, sessao.apresentou)
            sessao.apresentou = True
            await asyncio.to_thread(
                estado.registra_evento, origem, MSG_ID_OMITIDA, "—", "—",
                msg_id, "IDENTIFICACAO", sessao.atendimento,
                nome_cliente=sessao.cliente.get("nome", ""))
            await _envia(update, msg_id)
            return True

        # PORTA DE ENTRADA: nome de pessoa (ou telefone) não é texto
        # longo. Nada de busca, extração ou eco antes deste corte.
        #
        # Exceção: quem escreve "meu nome é X" no meio da frase marcou
        # ele mesmo onde o nome está ("bom dia, meu nome é Murilo e quero
        # cancelar a linha"). Aí a mensagem passa, mas o que vira nome —
        # e volta ecoado — é só a captura ancorada, nunca o texto todo.
        # O resto da mensagem continua fora do log (MSG_ID_OMITIDA) e
        # longe de qualquer LLM, que é o que o corte protege. No check
        # dos 4 dígitos não há nome a marcar: lá o corte é absoluto.
        if not identificacao_plausivel(texto_id) and (
                sessao.pediu_4dig or not nome_ancorado(texto_id)):
            log.warning("identificação rejeitada por tamanho (%d chars, "
                        "%d palavras) — conteúdo não registrado",
                        len(texto_id), len(texto_id.split()))
            # Barrado como identificação, mas ainda pode ser o PEDIDO.
            # Quem já ouviu "me diga seu nome" às vezes manda a tarefa
            # inteira em vez do nome ("meu 4G caiu há 3 horas, abre um
            # chamado") — e é justamente quem escreve assim, com todo o
            # contexto, que a demo precisa atender bem. Antes de desistir,
            # classifica: se for uma das 4 tarefas, guarda como pendente e
            # repete o pedido de identificação já reconhecendo o que a
            # pessoa quer, em vez do "não consegui entender seu nome".
            #
            # O corte acima continua valendo: o texto não vira nome, não
            # volta ecoado e não entra no log — daqui só sai um rótulo.
            if await _tenta_reconhecer_tarefa():
                return
            await _pede_identificacao_de_novo()
            return

        if not sessao.pediu_4dig:
            if not tem_letra(texto_id) and not re.search(r"\d{4,}", texto_id):
                # nem nome (só emoji/símbolo/pontuação) nem telefone:
                # pede de novo sem criar cadastro nem avançar de etapa
                await _pede_identificacao_de_novo()
                return
            nome = extrai_nome(texto_id)
            if not nome_plausivel(nome):
                # 2ª barreira: o que sobrou da extração ainda não tem
                # cara de nome. Nunca ecoar isso de volta. Mesma saída de
                # emergência do corte de tamanho acima: antes de desistir,
                # classifica — pode ser uma das 4 tarefas em vez de nome.
                if await _tenta_reconhecer_tarefa():
                    return
                await _pede_identificacao_de_novo()
                return
            plano = sorteia_plano()  # varia a demo; some com a sessão
            sessao.cliente = {"nome": nome, "telefone": "",
                              "plano_atual": plano}
            reconhecimento = (f"Prontinho, {nome}! Vou te atender aqui — "
                              f"hoje seu plano é o {PLANOS[plano]['nome']}. "
                              f"✅\n\n(simulado — nada fica salvo depois desta "
                              f"conversa)")
            sessao.plano_atual = sessao.cliente["plano_atual"]

            if re.search(r"\d{4,}", texto_id):
                # telefone informado: pede o check dos 4 dígitos
                sessao.pediu_4dig = True
                resposta_id = (reconhecimento + "\n\nPor segurança, me confirme "
                               "os 4 últimos números do seu telefone.")
                await asyncio.to_thread(
                    estado.registra_evento, origem, MSG_ID_OMITIDA, "—", "—",
                    resposta_id, "IDENTIFICACAO", sessao.atendimento,
                    nome_cliente=sessao.cliente.get("nome", ""))
                await _envia(update, resposta_id)
                return
            # só nome, sem telefone: não há o que confirmar — pula o check
            confirmacao = reconhecimento
        else:
            # check simulado: qualquer resposta com 4+ dígitos é aceita
            if len(re.sub(r"\D", "", texto_id)) < 4:
                await _envia(
                    update,
                    "Me envie só os 4 últimos números do seu telefone, "
                    "por favor. 😊")
                return
            # sem repetir "(simulado)": a mensagem anterior já marcou que
            # a identificação toda é teatro da demo
            confirmacao = "Verificado! ✅"

        sessao.identificado = True
        pendente = sessao.msg_pendente
        tarefa_retomada = sessao.tarefa_pendente
        sessao.msg_pendente = ""
        sessao.tarefa_pendente = ""
        await asyncio.to_thread(
            estado.registra_evento, origem, MSG_ID_OMITIDA, "—", "—",
            confirmacao, "IDENTIFICACAO", sessao.atendimento,
            nome_cliente=sessao.cliente.get("nome", ""))

        if not pendente:
            await _envia(update, confirmacao + "\n\n" + MSG_MENU)
            return
        # retoma o pedido original guardado
        texto_usuario = pendente
        prefixo = confirmacao + "\n\n"
    else:
        prefixo = ""
        tarefa_retomada = ""

    # despedida/agradecimento com a sessão ociosa: mesma checagem que
    # roteia() faria, mas ANTES de classificar — poupa a chamada de
    # intencao.py (API) e evita que o evento grave FORA_DE_ESCOPO pra uma
    # mensagem que era só um "valeu, era isso" sem pedido nenhum.
    if eh_despedida_ociosa(sessao, texto_usuario):
        await asyncio.to_thread(
            estado.registra_evento, origem, texto_usuario, "—", "—",
            MSG_DESPEDIDA, "DESPEDIDA", sessao.atendimento,
            nome_cliente=sessao.cliente.get("nome", ""))
        await _envia(update, prefixo + MSG_DESPEDIDA)
        return

    resultado, tarefa = await _classifica_tudo(sessao, texto_usuario,
                                               tarefa_retomada)
    log.info("nivel=%s caminho=%s tarefa=%s msg=%r", resultado["nivel"],
             resultado["caminho"], tarefa, texto_usuario)

    # to_thread: os fluxos podem chamar o interpretador (API) em desvios
    resposta = await asyncio.to_thread(
        roteia, sessao, texto_usuario, resultado["caminho"], tarefa)

    await asyncio.to_thread(
        estado.registra_evento, origem, texto_usuario,
        resultado["nivel"], resultado["caminho"], resposta, tarefa,
        sessao.atendimento, nome_cliente=sessao.cliente.get("nome", ""))
    await _envia(update, prefixo + resposta)


async def trata_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _responde(update, update.message.text, "texto")


async def trata_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Baixa o áudio do Telegram e transcreve ANTES de classificar —
    o classificador só vê texto, nunca o áudio direto."""
    voice = update.message.voice or update.message.audio
    arquivo = await voice.get_file()

    with tempfile.TemporaryDirectory() as pasta:
        caminho_ogg = Path(pasta) / "audio.ogg"
        await arquivo.download_to_drive(caminho_ogg)

        def transcreve() -> str:
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            with open(caminho_ogg, "rb") as f:
                r = client.audio.transcriptions.create(
                    model=MODELO_TRANSCRICAO, file=f, language="pt")
            return r.text

        try:
            texto = await asyncio.to_thread(transcreve)
        except Exception as e:
            log.error("falha na transcrição: %s", type(e).__name__)
            await _envia(
                update,
                "Não consegui ouvir seu áudio. 😕 Pode tentar de novo, "
                "ou me escrever por texto?")
            return

    log.info("áudio transcrito: %r", texto)
    await _responde(update, texto, "audio")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Faltam credenciais no .env "
                         "(TELEGRAM_BOT_TOKEN e/ou OPENAI_API_KEY). "
                         "Copie o .env.example para .env e preencha.")

    estado.inicializa()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, trata_texto))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, trata_audio))

    # Python 3.14 não cria mais event loop automático no MainThread,
    # mas o python-telegram-bot ainda espera um (issue #4874)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    log.info("Bot rodando (polling). Ctrl+C para parar.")
    app.run_polling()


if __name__ == "__main__":
    main()
