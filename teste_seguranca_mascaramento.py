"""Regressão de privacidade: número de telefone/CPF digitado FORA da
identificação não pode ir parar em texto puro no eventos.db (e, por
tabela, na aba Atendimentos do painel).

Motivo: caso real — depois de já identificada, uma pessoa respondeu uma
confirmação SIM/NÃO digitando o próprio telefone por engano
("999451260"). A proteção que já existia (bot.py trocar o texto por
MSG_ID_OMITIDA) só vale DURANTE a etapa de identificação — é proteção
por ETAPA da conversa, não por CONTEÚDO. Fora dali, qualquer dígito
longo (telefone, CPF) ia direto pro banco e pro painel sem nenhuma
sanitização.

A correção mascara em estado.registra_evento — o ponto único por onde
toda mensagem passa antes de virar evento persistido — então cobre
QUALQUER etapa da conversa, não só a identificação.

Determinístico: só bate em estado.py (SQLite local), nenhuma chamada de
API.

Uso: python teste_seguranca_mascaramento.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import sys  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import estado  # noqa: E402

# ---- casos --------------------------------------------------------------
# (mensagem do usuário, deve mascarar?, texto que NÃO pode sobrar cru se
# mascarar, ou "" quando o caso é de NÃO mascarar)
CASOS = [
    # o caso real do relato: telefone digitado respondendo SIM/NÃO,
    # já identificado, no meio de TROCAR_PLANO — não é etapa de
    # identificação nenhuma.
    ("999451260", True, "999451260"),
    # CPF formatado — separadores plausíveis (ponto, traço)
    ("123.456.789-00", True, "123456789"),
    # telefone com DDD e parênteses/espaço
    ("(11) 98765-4321", True, "11987654321"),
    # telefone solto, só dígitos, 11 dígitos
    ("11987654321", True, "11987654321"),

    # não pode mascarar o que não é número sensível: escolha de plano,
    # tamanho de pacote, valor em reais — tudo abaixo do piso de 8 dígitos
    ("1", False, ""),
    ("2", False, ""),
    ("sim", False, ""),
    ("não", False, ""),
    ("quero o plano de 20GB", False, ""),
    ("R$ 50 tá caro", False, ""),
    ("quero cancelar minha linha", False, ""),
]


def _registra_e_le(mensagem: str) -> str:
    db_teste.limpa()
    estado.inicializa()
    estado.registra_evento("texto", mensagem, "Rudimentar", "GUIADO",
                           resposta_bot="[resposta do fluxo]",
                           tarefa="TROCAR_PLANO",
                           atendimento=estado.proximo_atendimento())
    (evento,) = estado.ultimos_eventos(limite=1)
    return evento["mensagem"]


def _caso_confirmacao_sim_nao_fora_da_identificacao() -> list[str]:
    """O cenário exato do relato: sessão já identificada (fora do fluxo de
    identificação — aqui simulado só pela tarefa não ser IDENTIFICACAO),
    respondendo a uma pergunta SIM/NÃO com o telefone por engano."""
    erros = []
    gravado = _registra_e_le("999451260")
    if "999451260" in gravado:
        erros.append(f"telefone vazou pro campo mensagem: {gravado!r}")
    if gravado == "999451260":
        erros.append("mensagem não foi alterada — nenhuma máscara aplicada")
    return erros


def main():
    resultados = []

    for mensagem, deve_mascarar, nao_pode_sobrar in CASOS:
        gravado = _registra_e_le(mensagem)
        erros = []
        if deve_mascarar:
            if nao_pode_sobrar and nao_pode_sobrar in gravado:
                erros.append(f"dígito sensível ainda em texto puro: {gravado!r}")
            if gravado == mensagem:
                erros.append("nada foi mascarado")
        else:
            if gravado != mensagem:
                erros.append(f"mascarou o que não devia: {mensagem!r} -> {gravado!r}")
        nome = f"{'mascara' if deve_mascarar else 'preserva'} {mensagem!r}"
        resultados.append((nome, erros))

    resultados.append(("caso do relato: SIM/NÃO respondido com telefone",
                       _caso_confirmacao_sim_nao_fora_da_identificacao()))

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
