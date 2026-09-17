"""Prova que rodar teste não encosta no eventos.db do painel ao vivo.

Tira uma impressão digital (tamanho + sha256) de eventos.db e dos seus
arquivos WAL, roda as suítes, e confere que nada mudou — enquanto o
banco de teste, esse sim, recebeu a escrita.

Uso: python teste_isolamento_db.py          (só suítes determinísticas)
     python teste_isolamento_db.py --todos  (inclui as que chamam a API)
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

import hashlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import estado  # noqa: E402

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PASTA = Path(__file__).parent
DB_VIVO = estado.DB_PADRAO

# determinísticas: não gastam API, rodam sempre
SUITES = ["teste_despedida.py", "teste_troca_tarefa.py",
          "teste_reclamacao_cancelamento.py", "teste_identificacao.py",
          "teste_escolha_plano.py", "teste_seguranca_mascaramento.py"]
# gastam API (e simulacao_geral escreve no banco de verdade)
SUITES_API = ["teste_classificador.py", "teste_intencao.py",
              "teste_vies.py", "teste_interprete.py", "simulacao_geral.py"]


def _impressao(base: Path) -> dict[str, tuple[int, str] | None]:
    """Tamanho + sha256 do banco e dos seus arquivos WAL/SHM.

    O WAL importa: em journal_mode=WAL a escrita cai nele primeiro, então
    olhar só o .db principal deixaria passar poluição.
    """
    fp = {}
    for p in (base, Path(f"{base}-wal"), Path(f"{base}-shm")):
        if p.exists():
            dados = p.read_bytes()
            fp[p.name] = (len(dados), hashlib.sha256(dados).hexdigest())
        else:
            fp[p.name] = None
    return fp


def _diferencas(antes: dict, depois: dict) -> list[str]:
    return [f"{nome}: {antes[nome]} → {depois[nome]}"
            for nome in antes if antes[nome] != depois[nome]]


def main() -> int:
    todos = "--todos" in sys.argv
    suites = SUITES + (SUITES_API if todos else [])

    if not DB_VIVO.exists():
        print(f"⚠️ {DB_VIVO.name} não existe ainda — o teste ainda vale: "
              "no fim ele não pode ter sido criado.")

    antes = _impressao(DB_VIVO)
    print(f"Banco ao vivo:   {DB_VIVO}")
    print(f"Banco de teste:  {estado.caminho_db()}")
    if estado.caminho_db() == DB_VIVO:
        print("❌ FALHOU: o banco de teste é o mesmo do painel.")
        return 1
    print()

    falhas = []

    # 1) o caminho de escrita, exercitado de verdade
    db_teste.limpa()
    estado.inicializa()
    estado.registra_evento("texto", "persona fictícia de teste", "N1",
                           "GUIADO", "resposta de teste", "TROCAR_PLANO",
                           atendimento=estado.proximo_atendimento())
    eventos = estado.ultimos_eventos(limite=5)
    if len(eventos) != 1:
        falhas.append(f"o banco de teste não recebeu a escrita ({len(eventos)} "
                      "eventos, esperado 1)")
    print(f"OK   escrita direta foi parar em {estado.caminho_db().name} "
          f"({len(eventos)} evento)")

    # 2) cada suíte, em processo separado (import fresco)
    for suite in suites:
        r = subprocess.run([sys.executable, str(PASTA / suite)],
                           cwd=PASTA, capture_output=True, text=True)
        marca = "OK  " if r.returncode == 0 else "AVISO"
        print(f"{marca} {suite} (exit {r.returncode})")
        if r.returncode != 0:
            # falha da suíte em si não invalida o isolamento, mas aparece
            print(f"     → últimas linhas: {r.stdout.strip()[-200:]}")

    # 3) o veredito
    depois = _impressao(DB_VIVO)
    print()
    difs = _diferencas(antes, depois)
    if difs:
        falhas.append("eventos.db do painel FOI ALTERADO:\n     " +
                      "\n     ".join(difs))

    print("=" * 68)
    if falhas:
        for f in falhas:
            print(f"❌ {f}")
        return 1
    print(f"✅ {DB_VIVO.name} intacto (tamanho e sha256 idênticos, WAL "
          "incluído) depois de rodar "
          f"{len(suites)} suíte(s) + escrita direta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
