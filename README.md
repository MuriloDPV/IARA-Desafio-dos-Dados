# Iara — Motor de Letramento Digital

> Protótipo de demonstração — Desafio dos Dados 2026

Bot de Telegram que estima o nível de letramento digital do usuário (escala
INAF, 5 níveis) a cada atendimento — texto ou áudio transcrito — e adapta a
conversa em tempo real, em vez de tratar todo mundo com o mesmo roteiro.

## Como funciona

Antes de qualquer tarefa, o bot faz uma identificação simulada (nome/telefone
contra uma lista fixa de clientes fictícios + check de 4 dígitos de teatro).
A partir daí, o nível estimado define o caminho de atendimento:

| Nível INAF | Caminho | Comportamento |
|---|---|---|
| Analfabeto / Rudimentar | **Guiado** | Passo a passo, confirma tudo, oferece atendente humano simulado após 2 respostas confusas seguidas |
| Elementar | **Intermediário** | Meio-termo entre guiado e direto |
| Intermediário / Proficiente | **Direto** | Resolve em 1 mensagem |

Nenhum rótulo fica gravado na pessoa — o nível é recalculado a cada
interação, nunca fixado num perfil.

Dentro de uma tarefa, desvios de conversa são interpretados sem virar
"confusão" automaticamente:
- **"o mais barato"** → escolha válida, sem precisar do nome exato do plano.
- **"quanto custa o plus?"** → respondido com o dado real, sem contar como desvio.
- Mudar de ideia numa confirmação (*"quer cancelar a linha?" → "na verdade meu sinal tá ruim"*) → troca de tarefa, já que nada foi executado ainda.
- Reclamar do valor numa confirmação (*"25 reais muito caro"*) → reconhecido como reclamação, não como resposta SIM/NÃO — o bot não decide nada sozinho.

O bot cobre 4 tarefas fixas, com **dados 100% fictícios**: trocar de plano,
consultar fatura, reclamação de sinal e cancelar a linha. Fora dessas 4, o
bot admite o limite do protótipo em vez de adivinhar.

**Modelos usados:** `gpt-5.4-nano` (classificação de nível/intenção) e
`gpt-4o-mini-transcribe` (transcrição de áudio) — ambos com a mesma
`OPENAI_API_KEY`.

## Preparar (1x)

```bash
pip install -r requirements.txt
copy .env.example .env    # preencher TELEGRAM_BOT_TOKEN e OPENAI_API_KEY
```

## Rodar a suíte de testes

Antes de gravar uma demo, vale rodar os testes do classificador e dos fluxos:

```bash
python teste_classificador.py               # 6 casos de nível INAF → caminho
python teste_intencao.py                    # 17 casos de intenção → tarefa
python teste_interprete.py                  # desvio na etapa (reclamação de preço, etc.)
python teste_vies.py                        # viés: forma de falar não move o nível
python teste_despedida.py                   # despedida na sessão ociosa (sem API)
python teste_troca_tarefa.py                # troca de tarefa na confirmação (sem API)
python teste_reclamacao_cancelamento.py     # reclamação de preço (sem API)
python teste_escolha_plano.py               # número do plano, dígito e por extenso (sem API)
python teste_pedido_desconto.py             # pedido de desconto não vira troca silenciosa (sem API)
python teste_pedido_humano.py               # pedido explícito de humano escala na hora (sem API)
python teste_pergunta_multiplos_planos.py   # "tenho outro plano?" tem resposta fixa (sem API)
python simulacao_geral.py                   # 9 personas contra o pipeline completo
python teste_isolamento_db.py               # prova que testar não suja o eventos.db da demo
```

Todo script de teste começa com `import db_teste`, que aponta
`EVENTOS_DB_PATH` para `eventos_teste.db`. O `eventos.db` que o painel ao
vivo lê nunca é tocado por teste — `teste_isolamento_db.py` confere isso
comparando tamanho e sha256 (WAL incluído) antes e depois das suítes.

## Subir para demo

**Opção A** — script que abre bot e painel de uma vez:

```powershell
.\iniciar_demo.ps1
```

**Opção B** — manualmente, em 2 terminais:

```bash
# terminal 1
python bot.py

# terminal 2
python painel.py
```

Painel ao vivo em `http://localhost:8000` (atualiza a cada 2s, agrupado por
"Atendimento #N" — número sequencial, sem nome/telefone).

Para atender várias pessoas na mesma conversa, escreva "novo atendimento"
(ou "outro atendimento" / "atender outra pessoa") depois de uma tarefa
encerrada — reseta identificação e nível, e abre um card novo no painel sem
precisar de `/start`.

## Estrutura do projeto

```
bot.py            bot Telegram (texto + áudio → transcrição → classificação → fluxo)
classificador.py  nível INAF + caminho (1 chamada LLM no início da tarefa)
intencao.py       qual das 4 tarefas o usuário quer (1 chamada LLM)
interprete.py     desvios dentro da etapa — só chamado quando o padrão fixo falha
fluxos.py         os 3 caminhos × 4 tarefas (plano, fatura, sinal, cancelamento)
dados.py          planos e cliente fictícios
estado.py         SQLite compartilhado entre bot e painel (eventos por interação)
painel.py         painel ao vivo (FastAPI)
painel.html       front-end do painel ao vivo
casos_teste.md    casos de teste do classificador, em texto
teste_*.py        suíte de testes (ver seção acima)
```

## Aviso

Protótipo de demonstração — dados de clientes, planos e valores são
100% fictícios. Não há integração com sistemas reais de telecom.
