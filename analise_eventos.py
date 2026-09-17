"""Resumo agregado do eventos.db — só contagens, nenhum dado pessoal.

Lê o banco que o bot/painel já escrevem e imprime contagens por nível INAF,
por caminho e por tarefa. Opcionalmente salva um gráfico de barras (PNG).

O banco NUNCA é aberto direto: o script copia eventos.db (+ -wal/-shm) para
uma pasta temporária e analisa a cópia, então nem um checkpoint de WAL toca
no arquivo original. As colunas `mensagem` e `resposta_bot` não são lidas
em nenhuma consulta.

Uso:
    python analise_eventos.py
    python analise_eventos.py --grafico resumo.png
    python analise_eventos.py --db eventos_teste.db --grafico /tmp/resumo.png
"""

import argparse
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

DB_PADRAO = Path(__file__).parent / "eventos.db"

# ordem oficial da escala INAF (do menor para o maior domínio)
ORDEM_NIVEL = ["Analfabeto", "Rudimentar", "Elementar", "Intermediário", "Proficiente"]
ORDEM_CAMINHO = ["GUIADO", "INTERMEDIARIO", "DIRETO"]

# bot.py grava "—" em nivel/caminho nas etapas que não passam pelo
# classificador (identificação, menus). Não entram nas contagens INAF.
NAO_CLASSIFICADO = "—"

# paleta: uma série por gráfico = uma única cor (azul 450), fundo claro
COR_BARRA = "#2a78d6"
COR_FUNDO = "#fcfcfb"
COR_TEXTO = "#0b0b0b"
COR_TEXTO_2 = "#52514e"


def carrega(caminho: Path) -> list[dict]:
    """Copia o banco para um temp e devolve as linhas (sem colunas de texto)."""
    if not caminho.exists():
        sys.exit(f"Banco não encontrado: {caminho}\n"
                 "Rode a demo pelo menos uma vez ou aponte --db para outro arquivo.")

    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / caminho.name
        shutil.copy2(caminho, copia)
        for sufixo in ("-wal", "-shm"):  # sem eles, dados no WAL sumiriam
            origem = caminho.with_name(caminho.name + sufixo)
            if origem.exists():
                shutil.copy2(origem, copia.with_name(copia.name + sufixo))

        con = sqlite3.connect(copia)
        con.row_factory = sqlite3.Row
        linhas = [dict(r) for r in con.execute(
            "SELECT id, ts, origem, nivel, caminho, tarefa, atendimento "
            "FROM eventos ORDER BY id")]
        con.close()
    return linhas


def classificados(linhas: list[dict]) -> list[dict]:
    """Só as interações que passaram pelo classificador INAF."""
    return [l for l in linhas
            if (l["nivel"] or "").strip() not in ("", NAO_CLASSIFICADO)]


def conta_eventos(linhas: list[dict], campo: str) -> Counter:
    return Counter((l[campo] or "").strip() or "(vazio)" for l in linhas)


def nivel_predominante(linhas: list[dict]) -> dict[int, str]:
    """Nível mais frequente de cada atendimento (empate: o último observado)."""
    por_atendimento: dict[int, list[str]] = {}
    for l in classificados(linhas):
        n = l["atendimento"] or 0
        if n > 0:
            por_atendimento.setdefault(n, []).append(l["nivel"].strip())
    resultado = {}
    for n, niveis in por_atendimento.items():
        c = Counter(niveis)
        topo = max(c.values())
        # entre os empatados, fica o que aparece por último no atendimento
        resultado[n] = next(x for x in reversed(niveis) if c[x] == topo)
    return resultado


def conta_atendimentos_por_tarefa(linhas: list[dict]) -> Counter:
    """Quantos atendimentos passaram por cada tarefa (par atendimento+tarefa)."""
    pares = {(l["atendimento"], (l["tarefa"] or "").strip())
             for l in linhas
             if (l["atendimento"] or 0) > 0 and (l["tarefa"] or "").strip()}
    return Counter(t for _, t in pares)


def ordena(contagem: Counter, ordem_fixa: list[str] | None = None) -> list[tuple[str, int]]:
    if ordem_fixa:
        conhecidos = [(k, contagem[k]) for k in ordem_fixa if contagem.get(k)]
        extras = sorted(((k, v) for k, v in contagem.items() if k not in ordem_fixa),
                        key=lambda kv: -kv[1])
        return conhecidos + extras
    return sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))


def imprime(titulo: str, itens: list[tuple[str, int]], total: int):
    print(f"\n{titulo}")
    print("-" * len(titulo))
    if not itens:
        print("  (sem dados)")
        return
    largura = max(len(k) for k, _ in itens)
    for k, v in itens:
        pct = f"{v / total * 100:5.1f}%" if total else "    -"
        # barra em ASCII de propósito: o console do Windows (cp1252) não
        # imprime blocos unicode e derruba o script com UnicodeEncodeError
        barra = "#" * round(v / max(1, max(v2 for _, v2 in itens)) * 24)
        print(f"  {k.ljust(largura)}  {v:>4}  {pct}  {barra}")


def grafico(blocos: list[tuple[str, list[tuple[str, int]]]], saida: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, eixos = plt.subplots(
        len(blocos), 1, figsize=(9, 2.2 + 0.42 * sum(len(i) for _, i in blocos)),
        gridspec_kw={"height_ratios": [max(1, len(i)) for _, i in blocos]})
    fig.patch.set_facecolor(COR_FUNDO)

    for eixo, (titulo, itens) in zip(eixos, blocos):
        eixo.set_facecolor(COR_FUNDO)
        rotulos = [k for k, _ in itens][::-1]  # barh desenha de baixo pra cima
        valores = [v for _, v in itens][::-1]
        barras = eixo.barh(rotulos, valores, color=COR_BARRA, height=0.62)
        eixo.bar_label(barras, padding=4, color=COR_TEXTO_2, fontsize=9)
        eixo.set_title(titulo, loc="left", color=COR_TEXTO, fontsize=11, pad=8)
        eixo.set_xlim(0, max(valores) * 1.18 if valores else 1)
        eixo.tick_params(colors=COR_TEXTO_2, length=0)
        eixo.set_xticks([])  # os valores já estão na ponta das barras
        for lado in ("top", "right", "bottom"):
            eixo.spines[lado].set_visible(False)
        eixo.spines["left"].set_color("#d6d5d0")

    fig.suptitle("Motor de Letramento Digital — resumo agregado (sem dado pessoal)",
                 x=0.02, ha="left", color=COR_TEXTO, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    saida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(saida, dpi=160, facecolor=COR_FUNDO)
    print(f"\nGráfico salvo em: {saida}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", type=Path, default=DB_PADRAO, help="caminho do banco")
    p.add_argument("--grafico", type=Path, metavar="ARQUIVO.png",
                   help="também salva um gráfico de barras")
    args = p.parse_args()

    linhas = carrega(args.db)
    if not linhas:
        sys.exit("Banco vazio — nenhuma interação registrada ainda.")

    atendimentos = {l["atendimento"] for l in linhas if (l["atendimento"] or 0) > 0}
    predominante = nivel_predominante(linhas)
    com_inaf = classificados(linhas)

    ev_nivel = ordena(conta_eventos(com_inaf, "nivel"), ORDEM_NIVEL)
    ev_caminho = ordena(conta_eventos(com_inaf, "caminho"), ORDEM_CAMINHO)
    at_nivel = ordena(Counter(predominante.values()), ORDEM_NIVEL)
    at_tarefa = ordena(conta_atendimentos_por_tarefa(linhas))
    ev_tarefa = ordena(Counter(
        (l["tarefa"] or "").strip() for l in linhas if (l["tarefa"] or "").strip()))
    ev_origem = ordena(conta_eventos(linhas, "origem"))

    print(f"Banco: {args.db}")
    print(f"Interações registradas: {len(linhas)}   Atendimentos: {len(atendimentos)}")
    print(f"Interações classificadas pelo INAF: {len(com_inaf)}   "
          f"(as outras {len(linhas) - len(com_inaf)} são identificação/menu, "
          f"sem classificação)")

    imprime(f"Atendimentos por nível INAF (nível predominante) — "
            f"{len(predominante)} de {len(atendimentos)} atendimentos",
            at_nivel, len(predominante))
    imprime("Atendimentos por tarefa (um atendimento pode ter mais de uma)",
            at_tarefa, len(atendimentos))
    imprime("Interações por nível INAF", ev_nivel, len(com_inaf))
    imprime("Interações por caminho", ev_caminho, len(com_inaf))
    imprime("Interações por tarefa", ev_tarefa, sum(v for _, v in ev_tarefa))
    imprime("Interações por origem", ev_origem, len(linhas))

    if args.grafico:
        grafico([("Atendimentos por nível INAF", at_nivel),
                 ("Interações por caminho", ev_caminho),
                 ("Atendimentos por tarefa", at_tarefa)], args.grafico)


if __name__ == "__main__":
    main()
