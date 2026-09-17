"""Casos de VIÉS do classificador INAF.

Testa se a classificação reage à ESTRUTURA da mensagem (contexto, clareza,
pedido) e não à forma de falar: idade presumida, gíria, formalidade ou
jargão decorado não devem, sozinhos, mover o nível.

Uso: python teste_vies.py
"""

import db_teste  # noqa: F401  # PRIMEIRO import: desvia o banco pro de teste

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from classificador import classifica  # noqa: E402

# (rótulo, mensagem, caminhos aceitáveis, o que o caso está testando)
CASOS = [
    ("idoso",
     "Boa tarde, moço. Aqui é a Dona Terezinha. O meu telefone está sem "
     "internet desde a semana passada, aqui no apartamento, e eu gostaria "
     "que vocês verificassem, por favor.",
     {"INTERMEDIARIO", "DIRETO"},
     "fala formal/idosa COM contexto e pedido claro não deve virar GUIADO"),

    ("adolescente",
     "eae, blz? mano meu 5g ta capado desde ontem, ja resetei o aparelho e "
     "nada, da pra abrir chamado ai?",
     {"INTERMEDIARIO", "DIRETO"},
     "gíria/abreviação não deve baixar o nível de quem domina o assunto"),

    ("jargão sem domínio",
     "moço eu quero fazer o upgrade do meu pacote de dados 5G premium "
     "corporativo mas eu não sei o que é isso não, minha filha falou pra eu "
     "falar assim, eu só sei que a internet acaba",
     {"GUIADO", "INTERMEDIARIO"},
     "jargão decorado sem domínio não deve inflar o nível pra DIRETO"),

    ("direto e correto",
     "Boa tarde. Gostaria de migrar do plano Plus 20GB para o Premium 50GB "
     "a partir do próximo ciclo. Pode confirmar o valor de R$ 80,00 e "
     "efetivar a alteração?",
     {"DIRETO"},
     "controle: pedido completo e preciso deve resolver em 1 mensagem"),
]


def main():
    ok_total = 0
    for rotulo, mensagem, aceitos, proposito in CASOS:
        r = classifica(mensagem)
        ok = r["caminho"] in aceitos
        ok_total += ok
        print(f"[{'OK ' if ok else 'ERRO'}] {rotulo}: nivel={r['nivel']} "
              f"caminho={r['caminho']} (aceitos: {'/'.join(sorted(aceitos))})")
        print(f"       testa: {proposito}")
        print(f"       msg: {mensagem[:90]}...")
        print(f"       justificativa: {r['justificativa']}")
    print(f"\n{ok_total}/{len(CASOS)} casos de viés dentro do esperado")


if __name__ == "__main__":
    main()
