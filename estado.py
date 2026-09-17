"""Estado compartilhado entre bot e painel via SQLite.

Grava EVENTOS por interação (mensagem, nível estimado, caminho ativado).
A preferência de atendimento é recalculada a cada mensagem — nenhum
rótulo permanente fica vinculado à pessoa.
"""

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PADRAO = Path(__file__).parent / "eventos.db"


def caminho_db() -> Path:
    """Arquivo do banco em uso.

    Resolvido a cada chamada (não no import) para que scripts de teste
    possam apontar EVENTOS_DB_PATH para outro arquivo sem depender da
    ordem dos imports. Sem a variável, é o eventos.db do bot/painel.
    """
    valor = os.environ.get("EVENTOS_DB_PATH")
    return Path(valor) if valor else DB_PADRAO


def _conecta() -> sqlite3.Connection:
    con = sqlite3.connect(caminho_db(), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")  # bot e painel leem/escrevem juntos
    return con


def inicializa():
    with _conecta() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                origem TEXT NOT NULL,          -- 'texto' ou 'audio'
                mensagem TEXT NOT NULL,
                nivel TEXT NOT NULL,           -- nível INAF (nome oficial)
                caminho TEXT NOT NULL,         -- GUIADO / INTERMEDIARIO / DIRETO
                resposta_bot TEXT,
                tarefa TEXT DEFAULT '',        -- tarefa identificada na interação
                atendimento INTEGER DEFAULT 0  -- nº sequencial da sessão (sem
                                               -- identificador de pessoa)
            )
        """)
        # migra bancos criados em versões anteriores
        for coluna in ("tarefa TEXT DEFAULT ''", "atendimento INTEGER DEFAULT 0"):
            try:
                con.execute(f"ALTER TABLE eventos ADD COLUMN {coluna}")
            except sqlite3.OperationalError:
                pass


def _mascara_nome(texto: str, nome_cliente: str) -> str:
    """Troca o nome do cliente (completo ou só o primeiro nome) por um
    rótulo genérico em QUALQUER texto de resposta do bot, não importa a
    etapa ou a função que gerou a mensagem — identificação, troca de
    plano, fatura, sinal, cancelamento etc. Centralizado aqui (em vez de
    em cada f-string de fluxos.py/bot.py) porque é o ponto único por
    onde toda resposta passa antes de virar evento persistido; a
    mensagem que o Telegram efetivamente envia ao usuário não passa por
    aqui e continua natural, com o nome de verdade.

    Nome completo entra na alternância ANTES do primeiro nome (mais
    específico primeiro) para não sobrar um "Cliente Cliente" quando o
    texto tem o nome completo por extenso."""
    if not texto or not nome_cliente:
        return texto
    partes = nome_cliente.split()
    variantes = sorted({nome_cliente, partes[0]}, key=len, reverse=True)
    padrao = "|".join(re.escape(v) for v in variantes)
    return re.sub(rf"\b(?:{padrao})\b", "Cliente", texto, flags=re.IGNORECASE)


# Mesmo piso de bot.MIN_DIGITOS_TELEFONE (8 dígitos separa telefone/CPF de
# número solto do pedido — "20GB", "R$ 50", escolha de plano "1"/"2"/"3").
# Duplicado aqui (em vez de importado) porque bot.py importa estado, não o
# contrário — e porque este piso vale pra QUALQUER mensagem, não só a de
# identificação, que é o ponto fraco que motivou este mascaramento.
MIN_DIGITOS_SENSIVEIS = 8

# Sequência de dígitos com separadores plausíveis de telefone/CPF (espaço,
# ponto, traço, parênteses). Sem "/" nem ":" no conjunto — evita colar data
# ("01/02/2026") ou hora ("10:30") num único candidato.
_PADRAO_NUMERO_LONGO = re.compile(r"\d[\d\s.\-()]{6,}\d")


def _mascara_numeros_sensiveis(texto: str) -> str:
    """Mascara telefone/CPF (ou qualquer sequência longa de dígitos) que o
    usuário digitar em QUALQUER mensagem, não só nas etapas de
    identificação — aquela proteção é por ETAPA da conversa (o texto nem
    chega a ser gravado ali, vira MSG_ID_OMITIDA em bot.py) e não cobre
    alguém digitando um número por engano em resposta a outra coisa (ex.:
    confirmação SIM/NÃO). Esta roda no mesmo ponto único por onde toda
    mensagem passa antes de virar evento persistido — igual _mascara_nome
    faz para resposta_bot."""
    if not texto:
        return texto

    def _troca(m: re.Match) -> str:
        so_digitos = re.sub(r"\D", "", m.group(0))
        return ("[número removido]" if len(so_digitos) >= MIN_DIGITOS_SENSIVEIS
                else m.group(0))

    return _PADRAO_NUMERO_LONGO.sub(_troca, texto)


def registra_evento(origem: str, mensagem: str, nivel: str, caminho: str,
                    resposta_bot: str = "", tarefa: str = "",
                    atendimento: int = 0, nome_cliente: str = ""):
    mensagem = _mascara_numeros_sensiveis(mensagem)
    resposta_bot = _mascara_nome(resposta_bot, nome_cliente)
    with _conecta() as con:
        con.execute(
            "INSERT INTO eventos (ts, origem, mensagem, nivel, caminho, "
            "resposta_bot, tarefa, atendimento) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%H:%M:%S"), origem, mensagem, nivel,
             caminho, resposta_bot, tarefa, atendimento),
        )


def proximo_atendimento() -> int:
    """Próximo número sequencial de atendimento (nada de dado pessoal)."""
    with _conecta() as con:
        (m,) = con.execute(
            "SELECT COALESCE(MAX(atendimento), 0) FROM eventos").fetchone()
    return m + 1


def atendimentos_agrupados(limite: int = 10) -> list[dict]:
    """Últimos atendimentos com seus eventos em ordem cronológica."""
    with _conecta() as con:
        con.row_factory = sqlite3.Row
        nums = [r[0] for r in con.execute(
            "SELECT DISTINCT atendimento FROM eventos WHERE atendimento > 0 "
            "ORDER BY atendimento DESC LIMIT ?", (limite,))]
        grupos = []
        for n in nums:
            evs = [dict(r) for r in con.execute(
                "SELECT * FROM eventos WHERE atendimento = ? ORDER BY id",
                (n,))]
            grupos.append({"atendimento": n, "eventos": evs})
    return grupos


CAMINHOS = ("GUIADO", "INTERMEDIARIO", "DIRETO")

# IDENTIFICACAO é ritual de abertura, não tarefa — fica fora da distribuição
# (mesmo critério dos badges do painel)
TAREFAS = ("TROCAR_PLANO", "CONSULTAR_FATURA", "RECLAMAR_SINAL",
           "CANCELAR_LINHA", "FORA_DE_ESCOPO")

NIVEIS = ("Analfabeto", "Rudimentar", "Elementar", "Intermediário",
          "Proficiente")

# Trecho literal da MSG_ATENDENTE (fluxos.py) — é o que fica gravado em
# resposta_bot quando o atendimento é de fato encaminhado (2 respostas
# confusas seguidas, ou o usuário escrevendo ATENDENTE). Não dá pra importar
# de fluxos: aquele módulo puxa a API, e o painel roda sem chave.
# A frase é escolhida a dedo — a MSG_FORA_ESCOPO também fala em "atendente
# humano", mas no condicional ("eu te conectaria"), e não é encaminhamento.
MARCADOR_ATENDENTE = "Vou te conectar com um atendente humano"


def _segundos(ts: str | None) -> int | None:
    """HH:MM:SS -> segundos desde a meia-noite. Fora do formato, None."""
    try:
        h, m, s = (int(p) for p in ts.split(":"))
    except (AttributeError, ValueError):
        return None
    return h * 3600 + m * 60 + s


GAP_MAXIMO_ATIVO = 300  # segundos (5min) — ver _duracao_ativa


def _gap(inicio: int, fim: int) -> int:
    """Segundos entre dois horários do mesmo dia, fim após inicio.

    O ts guarda só a hora (sem data), então uma virada de meia-noite
    chega aqui como diferença negativa — vale a volta do relógio.
    """
    return fim - inicio if fim >= inicio else fim - inicio + 86400


def _duracao_ativa(tss: list[int]) -> int:
    """Soma os intervalos entre eventos consecutivos do atendimento.

    Não é só (último - primeiro): um atendimento real não fica minutos a
    fio "ativo" no silêncio entre uma mensagem e a próxima. Quando o
    intervalo estoura GAP_MAXIMO_ATIVO, é sessão abandonada e retomada
    depois (às vezes horas depois) — não conversa contínua — então cada
    intervalo conta até esse teto, e o resto vira pausa, não atendimento.
    Sem o teto, um único evento tardio (ex.: usuário reabrindo o chat
    90min depois pra mandar uma mensagem solta) infla a média do nível
    inteiro, que é exatamente o bug que motivou isso aqui.
    """
    return sum(min(_gap(a, b), GAP_MAXIMO_ATIVO) for a, b in zip(tss, tss[1:]))


def estatisticas_agregadas() -> dict:
    """Resumo agregado por ATENDIMENTO — só contagens, nada pessoal.

    Conta atendimentos distintos, não eventos soltos: a mesma conversa não
    entra várias vezes. O caminho de um atendimento é o último definido nele
    (mesma regra do resumo() do painel); a tarefa conta uma vez por
    atendimento, e um atendimento com duas tarefas aparece nas duas.

    Também devolve duas leituras por atendimento:
    - `resolucao`: quantos chegaram ao fim sem encaminhar pra atendente
      humano (detectado pelo MARCADOR_ATENDENTE na resposta do bot);
    - `tempo_por_nivel`: soma dos intervalos entre eventos consecutivos do
      atendimento (cada um até GAP_MAXIMO_ATIVO — ver _duracao_ativa),
      média agrupada pelo nível INAF final. Ordem de grandeza, não
      cronômetro.
    """
    with _conecta() as con:
        linhas = con.execute(
            "SELECT atendimento, caminho, tarefa, nivel, ts, resposta_bot "
            "FROM eventos WHERE atendimento > 0 ORDER BY id").fetchall()

    caminho_final: dict[int, str] = {}
    nivel_final: dict[int, str] = {}
    tarefas_por_atendimento: dict[int, set[str]] = {}
    encaminhados: set[int] = set()
    timestamps: dict[int, list[int]] = {}   # atendimento -> ts em ordem
    for atendimento, caminho, tarefa, nivel, ts, resposta in linhas:
        tarefas_por_atendimento.setdefault(atendimento, set())
        if caminho in CAMINHOS:
            caminho_final[atendimento] = caminho
        if nivel in NIVEIS:
            nivel_final[atendimento] = nivel
        if tarefa in TAREFAS:
            tarefas_por_atendimento[atendimento].add(tarefa)
        if resposta and MARCADOR_ATENDENTE in resposta:
            encaminhados.add(atendimento)
        seg = _segundos(ts)
        if seg is not None:
            timestamps.setdefault(atendimento, []).append(seg)

    caminhos = {c: 0 for c in CAMINHOS}
    for c in caminho_final.values():
        caminhos[c] += 1

    tarefas = {t: 0 for t in TAREFAS}
    for conjunto in tarefas_por_atendimento.values():
        for t in conjunto:
            tarefas[t] += 1

    # duração só faz sentido pra quem tem nível definido — é o eixo do grupo
    duracoes: dict[str, list[int]] = {}
    for atendimento, nivel in nivel_final.items():
        if atendimento in timestamps:
            duracoes.setdefault(nivel, []).append(
                _duracao_ativa(timestamps[atendimento]))
    tempo_por_nivel = {
        nivel: {"segundos": round(sum(v) / len(v)), "n": len(v)}
        for nivel in NIVEIS if (v := duracoes.get(nivel))
    }

    total = len(tarefas_por_atendimento)
    return {
        "total": total,
        "com_caminho": len(caminho_final),   # base honesta pros percentuais
        "caminhos": caminhos,
        "tarefas": tarefas,
        # taxa de resolução, não acurácia: mede quantos atendimentos a Iara
        # levou até o fim sozinha, não se ela classificou certo
        "resolucao": {
            "base": total,
            "encaminhados": len(encaminhados),
            "sem_atendente": total - len(encaminhados),
            # mais recente primeiro — é o que interessa pra revisão manual
            "ids_encaminhados": sorted(encaminhados, reverse=True),
        },
        "tempo_por_nivel": tempo_por_nivel,
    }


def ultimos_eventos(limite: int = 20) -> list[dict]:
    with _conecta() as con:
        con.row_factory = sqlite3.Row
        linhas = con.execute(
            "SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(l) for l in linhas]
