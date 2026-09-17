"""Dados 100% fictícios para a demonstração — nenhum dado real de cliente."""

import random

PLANOS = {
    "basico": {"nome": "Básico 5GB", "gb": 5, "preco": 30.00},
    "plus": {"nome": "Plus 20GB", "gb": 20, "preco": 50.00},
    "premium": {"nome": "Premium 50GB", "gb": 50, "preco": 80.00},
}

# Ordem de exibição nos menus (1, 2, 3)
ORDEM_PLANOS = ["basico", "plus", "premium"]

# Cliente-modelo usado só como valor-padrão de sessão (antes de identificar);
# a identificação real nunca bate contra uma lista fixa — ver sorteia_plano.
CLIENTE_TESTE = {"nome": "Maria da Silva", "telefone": "", "plano_atual": "basico"}


def sorteia_plano() -> str:
    """Plano do 'cadastro novo' (telefone fora da lista fixa): sorteado
    entre os 3, só pra aquela sessão — nada persiste. Fica como função
    (e não inline no bot) pra poder ser fixada nos testes, que têm
    roteiro escrito e precisam de plano previsível."""
    return random.choice(ORDEM_PLANOS)


def _normaliza(t: str) -> str:
    return (t.lower().replace("á", "a").replace("â", "a").replace("ã", "a")
            .replace("à", "a").replace("é", "e").replace("ê", "e")
            .replace("í", "i").replace("ó", "o").replace("ô", "o")
            .replace("õ", "o").replace("ú", "u").replace("ü", "u")
            .replace("ç", "c"))


def tem_letra(texto: str) -> bool:
    """Há pelo menos uma letra de verdade? Emoji, símbolo (🅼) e pontuação
    não contam — `str.isalpha()` é False para categorias de símbolo."""
    return any(ch.isalpha() for ch in texto)


# --- limites do campo de identificação ---------------------------------
# Nome de pessoa (ou telefone) nunca é um texto longo. Qualquer coisa
# acima disso não é identificação: é outra coisa se passando por nome —
# e como o nome informado volta ecoado na resposta ("criei um cadastro
# novo pra você, <nome>"), texto longo aqui vira eco de texto arbitrário.
# Rejeitar ANTES de qualquer processamento (busca, extração, LLM).
MAX_CHARS_IDENTIFICACAO = 60   # mensagem inteira, como chegou
MAX_PALAVRAS_IDENTIFICACAO = 8
MAX_CHARS_NOME = 50            # nome já extraído
MAX_PALAVRAS_NOME = 5


def identificacao_plausivel(texto: str) -> bool:
    """A mensagem tem tamanho de identificação? Checagem de porta de
    entrada: roda antes de buscar cadastro ou extrair nome."""
    t = " ".join(texto.split())
    return bool(t) and (len(t) <= MAX_CHARS_IDENTIFICACAO
                        and len(t.split()) <= MAX_PALAVRAS_IDENTIFICACAO)


# --- ruído que a extração devolve com cara de nome ---------------------
# `extrai_nome` só tira dígitos, emoji e as sobras da lista curta de
# enrolação, então qualquer palavra solta vira "nome" e volta ecoada na
# resposta ("criei um cadastro novo pra você, Quero"). Em teste real
# apareceram capturas assim vindas de áudio e de mensagens picadas.
#
# O crivo abaixo é de baixa ambição de propósito: derruba o óbvio (palavra
# sem vogal, risada, letra repetida, palavra do próprio atendimento) e
# deixa passar qualquer coisa com forma de nome. Não tem dicionário de
# nomes — captura errada mas plausível ("Carlão") continua passando, e
# isso é aceitável: o custo de barrar um nome de verdade é maior.
_VOGAIS = set("aeiouy")

# Palavras que aparecem no lugar do nome quando a pessoa não respondeu à
# pergunta (verbo do pedido, saudação, palavra do domínio). Lista curta:
# só o que não é nome de gente em nenhuma leitura.
_NAO_SAO_NOMES = {
    "quero", "queria", "quer", "preciso", "precisa", "gostaria", "pode",
    "poderia", "sim", "nao", "ok", "okay", "oi", "ola", "alo", "opa",
    "eae", "bom", "boa", "dia", "tarde", "noite", "obrigado", "obrigada",
    "valeu", "tchau", "favor", "ajuda", "ajudar", "socorro", "sei",
    "nada", "tudo", "bem", "senhor", "senhora", "moco", "moca",
    "plano", "planos", "fatura", "faturas", "boleto", "conta", "contas",
    "sinal", "internet", "celular", "linha", "chip", "pacote", "gb",
    "cancelar", "cancela", "trocar", "troca", "mudar", "muda", "pagar",
    "atendente", "atendimento", "operadora"}
# "cliente" fica FORA da lista de propósito: é o nome que `extrai_nome`
# devolve quando a pessoa se identificou só pelo telefone (não sobrou
# palavra nenhuma). Barrar ali derrubaria identificação legítima.


def _palavra_de_nome(palavra: str) -> bool:
    """Esta palavra pode ser (parte de) um nome de pessoa?"""
    import re
    base = _normaliza(palavra.strip("-'"))
    if len(base) < 2:                       # "J", "-": inicial solta não vale
        return False
    if not any(ch in _VOGAIS for ch in base):   # "hmm", "kkk", "rsrs"
        return False
    if re.search(r"(.)\1\1", base):             # "aaaa", "kkkk", "eeee"
        return False
    return base not in _NAO_SAO_NOMES


def nome_plausivel(nome: str) -> bool:
    """O nome extraído parece nome de gente? Segunda barreira, para o
    caso de a extração devolver algo grande a partir de uma entrada que
    passou pelo limite bruto (ex.: muita pontuação removida) — ou ruído
    que não é nome nenhum (ver _palavra_de_nome).

    A 1ª palavra é a que volta ecoada como primeiro nome, então ela
    precisa passar; as demais podem ser abreviação ou partícula."""
    palavras = nome.split()
    if not (palavras and len(nome) <= MAX_CHARS_NOME
            and len(palavras) <= MAX_PALAVRAS_NOME):
        return False
    return _palavra_de_nome(palavras[0])


# --- âncoras de auto-apresentação --------------------------------------
# A pessoa que diz "meu nome é X" marca ela mesma onde o nome começa.
# Sem isso só sobra apagar a enrolação conhecida e devolver o resto —
# o que basta quando a mensagem é só o nome, mas devolve a frase inteira
# quando vem pedido junto ("meu nome é Murilo e quero cancelar a linha").
#
# Lista curta de propósito: só marcador que introduz nome e nada mais.
# "sou" ficou de fora — sozinho ele abre casos como "não sou o titular",
# em que a captura ficaria com cara de nome; e "sou o João Pereira" já
# sai certo pelo caminho antigo.
_ANCORAS = (
    ("pode", "me", "chamar", "de"),
    ("meu", "nome"),
    ("me", "chamo"),
    ("chamo", "me"),
)

# Partícula que pode aparecer entre a âncora e o nome ("meu nome É o ...").
_LIGACAO = {"e", "eh", "o", "a", "os", "as", "um", "uma", "sr", "sra",
            "seu", "dona"}


def _nome_apos_ancora(palavras: list[str]) -> str:
    """Nome que vem depois de um "meu nome é"/"me chamo" na frase.

    Para na primeira palavra que não tem cara de nome — é o que separa o
    nome do resto do pedido ("... Murilo E QUERO cancelar"). Devolve ""
    quando não há âncora ou quando não sobrou nome atrás dela, e aí quem
    decide é o caminho antigo."""
    base = [_normaliza(p) for p in palavras]
    for i in range(len(base)):
        for ancora in _ANCORAS:
            if tuple(base[i:i + len(ancora)]) != ancora:
                continue
            j = i + len(ancora)
            while j < len(base) and base[j] in _LIGACAO:
                j += 1
            captura = []
            while (j < len(base) and len(captura) < MAX_PALAVRAS_NOME
                   and _palavra_de_nome(palavras[j])):
                captura.append(palavras[j])
                j += 1
            if captura:
                return " ".join(captura).title()
    return ""


def _palavras_limpas(texto: str) -> list[str]:
    """Só letras (com acento), hífen e apóstrofo — fora dígito e emoji."""
    import re
    limpo = "".join(ch for ch in texto
                    if ch.isalpha() or ch in " -'").strip(" -'")
    return re.sub(r"\s+", " ", limpo).split()


def extrai_nome(texto: str) -> str:
    """Nome informado na identificação (tira dígitos, emoji e sobras)."""
    palavras = _palavras_limpas(texto)
    ancorado = _nome_apos_ancora(palavras)
    if ancorado:
        return ancorado
    restante = [p for p in palavras if p.lower() not in
                ("sou", "eu", "me", "chamo", "aqui", "é", "e", "o", "a",
                 "meu", "nome", "numero", "número", "telefone")]
    return " ".join(restante).title() if restante else "Cliente"


def nome_ancorado(texto: str) -> str:
    """Nome que a pessoa marcou explicitamente ("meu nome é X") — e só ele.

    Serve de exceção ao corte de tamanho: numa frase que passa do limite
    ("bom dia, meu nome é Murilo e quero cancelar a linha") o nome está
    ali, marcado por quem escreveu. O que essa função devolve é a única
    parte da mensagem que pode ser usada — a captura ancorada, já passada
    pelo crivo de `nome_plausivel`. O texto em volta continua descartado.

    Devolve "" quando não há âncora ou quando o que vem atrás dela não
    tem cara de nome; aí o corte de tamanho vale normalmente."""
    nome = _nome_apos_ancora(_palavras_limpas(texto))
    return nome if nome and nome_plausivel(nome) else ""


def lista_planos_texto() -> str:
    """Lista numerada dos planos para mostrar ao cliente."""
    linhas = []
    for i, chave in enumerate(ORDEM_PLANOS, start=1):
        p = PLANOS[chave]
        preco = f"{p['preco']:.2f}".replace(".", ",")
        linhas.append(f"{i}. {p['nome']} — R$ {preco}/mês")
    return "\n".join(linhas)


def acha_planos(texto: str) -> list[str]:
    """Todos os planos citados no texto, na ordem em que aparecem."""
    t = _normaliza(texto)
    posicoes = []
    for chave, p in PLANOS.items():
        apelidos = [chave, p["nome"].split()[0].lower(), f"{p['gb']}gb",
                    f"{p['gb']} gb", f"{p['gb']} giga"]
        achou = [t.find(_normaliza(a)) for a in apelidos if _normaliza(a) in t]
        if achou:
            posicoes.append((min(achou), chave))
    return [chave for _, chave in sorted(posicoes)]


# Número por extenso da escolha de plano ("dois", "o segundo"). "um" fica
# de fora do reconhecimento livre-no-meio-da-frase por ser também artigo
# indefinido ("quero UM plano mais barato" não é escolher o plano 1); e
# "segundo"/"terceiro" soltos colidem com tempo ("espera um segundo") ou
# ordem de outro assunto — por isso só contam quando vêm depois de artigo
# definido ("o segundo", "prefiro o dois"), que é como se aponta a opção
# em português, não um número solto no meio do texto.
_PALAVRAS_NUMERO = {"um": 1, "dois": 2, "tres": 3}
_PALAVRAS_ORDINAL = {"primeiro": 1, "primeira": 1,
                     "segundo": 2, "segunda": 2,
                     "terceiro": 3, "terceira": 3}


def _numero_do_plano(texto: str) -> int | None:
    """Índice (1, 2 ou 3) do plano citado como dígito ou número por
    extenso — sozinho, logo após "plano", ou logo após artigo definido
    ("o"/"a")."""
    import re
    t = _normaliza(texto).strip()

    primeiro_token = re.split(r"[\s.,!]", t, maxsplit=1)[0]
    if primeiro_token in ("1", "2", "3"):
        return int(primeiro_token)
    if primeiro_token in _PALAVRAS_NUMERO:
        return _PALAVRAS_NUMERO[primeiro_token]

    m = re.search(r"\bplano\s+(um|dois|tres|1|2|3)\b", t)
    if m:
        alvo = m.group(1)
        return int(alvo) if alvo.isdigit() else _PALAVRAS_NUMERO[alvo]

    m = re.search(r"\b[oa]\s+(um|dois|tres|1|2|3|"
                  r"primeir[oa]|segund[oa]|terceir[oa])\b", t)
    if m:
        alvo = m.group(1)
        if alvo.isdigit():
            return int(alvo)
        return _PALAVRAS_NUMERO.get(alvo) or _PALAVRAS_ORDINAL.get(alvo)

    return None


def acha_plano(texto: str) -> str | None:
    """Identifica UM plano na resposta do usuário (número — dígito ou por
    extenso —, nome ou GB)."""
    indice = _numero_do_plano(texto)
    if indice:
        return ORDEM_PLANOS[indice - 1]
    citados = acha_planos(texto)
    return citados[0] if citados else None
