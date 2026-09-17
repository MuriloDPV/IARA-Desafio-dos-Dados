# Motor de Letramento Digital — protótipo de demonstração

Bot Telegram que estima o nível de letramento digital (5 níveis do INAF)
a cada atendimento — texto ou áudio transcrito — e adapta o atendimento
em 4 tarefas fixas (simuladas, dados 100% fictícios): trocar de plano,
consultar fatura, reclamação de sinal e cancelar a linha. Antes de
qualquer tarefa o bot pede nome/telefone (identificação simulada contra
uma lista fixa de clientes fictícios + check de 4 dígitos de teatro).
Fora dessas 4 tarefas, o bot admite o limite do protótipo em vez de
adivinhar. Dentro de uma etapa, desvios são interpretados pelo mesmo
modelo barato: "o mais barato" vira escolha válida e "quanto custa o
plus?" é respondido com o dado real sem contar como confusão. Nas
confirmações SIM/NÃO, quem muda de ideia ("quer cancelar a linha?" → "na
verdade meu sinal tá ruim") troca de tarefa em vez de virar confusão — a
confirmação pendente é abandonada, já que nada foi executado ainda. Já
reclamar do valor na confirmação do cancelamento ("25 reais muito caro")
não é resposta nem pedido: o bot reconhece a reclamação numa frase e
repete a pergunta, sem decidir nada sozinho.

- Analfabeto / Rudimentar → caminho **GUIADO** (passo a passo, confirma tudo,
  oferece atendente humano simulado após 2 respostas confusas seguidas)
- Elementar → caminho **INTERMEDIÁRIO**
- Intermediário / Proficiente → caminho **DIRETO** (resolve em 1 mensagem)

Nenhum rótulo fica gravado na pessoa — a preferência é recalculada a cada
interação. Modelos: `gpt-5.4-nano` (classificação) e `gpt-4o-mini-transcribe`
(áudio), ambos com a mesma `OPENAI_API_KEY`.

## Preparar (1x)

```
pip install -r requirements.txt
copy .env.example .env    # e preencher TELEGRAM_BOT_TOKEN e OPENAI_API_KEY
```

## Testar o classificador (antes de gravar)

```
python teste_classificador.py   # 6 casos de nível INAF → caminho
python teste_intencao.py        # 17 casos de intenção → tarefa
python teste_interprete.py      # desvio na etapa (reclamação de preço, etc.)
python teste_vies.py            # viés: forma de falar não move o nível
python teste_despedida.py       # despedida na sessão ociosa (sem API)
python teste_troca_tarefa.py    # troca de tarefa na confirmação (sem API)
python teste_reclamacao_cancelamento.py   # reclamação de preço (sem API)
python teste_escolha_plano.py   # número do plano, dígito e por extenso (sem API)
python teste_pedido_desconto.py # pedido de desconto não vira troca silenciosa (sem API)
python teste_pedido_humano.py   # pedido explícito de humano escala na hora (sem API)
python teste_pergunta_multiplos_planos.py   # "tenho outro plano?" tem resposta fixa (sem API)
python simulacao_geral.py       # 9 personas contra o pipeline completo
python teste_isolamento_db.py   # prova que testar não suja o eventos.db da demo
```

Todo script de teste começa com `import db_teste`, que aponta
`EVENTOS_DB_PATH` para `eventos_teste.db`. O `eventos.db` que o painel ao
vivo lê nunca é tocado por teste — `teste_isolamento_db.py` confere isso
comparando tamanho e sha256 (WAL incluído) antes e depois das suítes.

## Subir pra demo (2 processos)

Opção A — script que abre os dois de uma vez:

```
.\iniciar_demo.ps1
```

Opção B — manualmente, em 2 terminais:

```
# terminal 1
python bot.py

# terminal 2
python painel.py
```

Painel: http://localhost:8000 (atualiza a cada 2s, agrupado por
"Atendimento #N" — número sequencial, sem nome/telefone).

Vários atendimentos na mesma conversa: com a tarefa encerrada, escreva
"novo atendimento" (ou "outro atendimento" / "atender outra pessoa") —
reseta identificação e nível, e abre um card novo no painel sem /start.
Bot: fale com ele no Telegram (o bot criado no @BotFather).

## Arquivos

- `bot.py` — bot Telegram (texto + áudio → transcrição → classificação → fluxo)
- `classificador.py` — nível INAF + caminho (1 chamada LLM no início da tarefa)
- `intencao.py` — qual das 4 tarefas o usuário quer (1 chamada LLM)
- `interprete.py` — desvios dentro da etapa (resposta reformulada / pergunta
  respondível / confusão) — só chamado quando o padrão fixo falha
- `fluxos.py` — os 3 caminhos × 4 tarefas (plano, fatura, sinal, cancelamento)
- `dados.py` — planos e cliente fictícios
- `estado.py` — SQLite compartilhado entre bot e painel (eventos por interação)
- `painel.py` + `painel.html` — painel ao vivo
- `casos_teste.md` / `teste_classificador.py` — casos de teste do classificador
