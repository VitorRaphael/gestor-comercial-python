# Mitigação de Falhas

> **O que é este documento.** A planta da camada de blindagem defensiva do
> Solvix POS (Gestor Comercial Python), a etapa seguinte à
> [`REMASTERIZACAO-V1.md`](REMASTERIZACAO-V1.md). O objetivo declarado é
> **Zero Unhandled Crashes**: nenhum erro de digitação, periférico solto ou
> banco travado pode fazer o programa sumir da tela — nem, o que a auditoria
> descobriu ser o risco real aqui, fazer um clique **não fazer nada em
> silêncio** no meio de um atendimento de pico.
>
> É um documento **vivo e sequencial**, igual ao da remasterização: cada fase
> tem checkbox, critério de pronto e como validar. Marque `[x]` só depois de a
> suíte passar.
>
> **Legenda de confiança dos achados:**
> ✅ **provado** — reproduzido nesta máquina, com saída de execução colada aqui.
> 🔍 **verificado** — código aberto e conferido linha a linha.
> ⚠️ **reportado** — levantado pela auditoria, ainda sem verificação independente.

---

## 0. Onde estamos — 2026-09-07

Auditoria e implementação **concluídas**. As 7 fases fechadas, os 6 testes de
caos verdes.

| Fase | Estado |
|---|---|
| 0 — Rede de segurança | ✅ concluída |
| 1 — Caixa-preta: log rotativo | ✅ concluída |
| 2 — Escudo global | ✅ concluída |
| **2b — Blindagem dos overrides virtuais** | ✅ concluída — *não estava no plano; o §1.6 obrigou* |
| 3 — Impressora: fila + thread | ✅ concluída |
| 4 — SQLite: `busy_timeout` | ✅ concluída |
| 5 — `safe_decimal` | ✅ concluída |

Suíte: **883 passando** (baseline 801 + 82 novos), 0 falhas.

```
$ .venv/Scripts/python.exe -m pytest -q          # baseline, antes de tocar em nada
801 passed in 28.01s
$ .venv/Scripts/python.exe -m pytest -q          # com as 7 fases fechadas
883 passed in 28.84s
```

| Item | Estado |
|---|---|
| Branch | `main`, a partir do commit `254bb7b` |
| Pendência no working tree | `REMASTERIZACAO-V1.md` com o §10 **staged e não commitado** (o texto "em português de balcão", de sessão anterior). Não é desta etapa — **não entrou no commit da blindagem** |

---

## 1. Auditoria — o que já existe e o que falta

A instrução original pediu cinco pilares como se o sistema estivesse cru. Ele
não está: a remasterização já entregou parte do que se pede, e em dois pontos
já decidiu o **contrário** do que o roteiro sugere, com o motivo escrito no
código. O quadro abaixo separa trabalho novo de trabalho já feito, para não
reconstruirmos nada por cima.

| # | Pilar | Situação | Onde |
|---|---|---|---|
| 1 | Escudo global anti-crash | ❌ **Não existia** — zero `sys.excepthook`, zero `logging` no projeto inteiro → ✅ Fases 1, 2 e 2b | `core/resilience.py` |
| 2 | Isolamento da impressora | 🟡 Parcial — fronteira, timeouts e `ErroDeImpressao` prontos; faltava a fila de contingência → ✅ Fase 3 | `domain/fila_impressao.py`, `services/impressao_service.py` |
| 3 | Blindagem do SQLite | 🟡 Parcial — `WAL` e `foreign_keys` prontos; faltava `busy_timeout` → ✅ Fase 4 | `repository/base.py:16-59` |
| 3b | Backup atômico | ✅ **Pronto, e melhor que o pedido** — `VACUUM INTO` + rotação | `repository/backup.py` |
| 4 | Sanitização de entradas | 🟡 Parcial — as **9** conversões estavam guardadas, mas por convenção repetida e não por função única → ✅ Fase 5 | `ui/formatacao.py` |
| 5 | Logs rotativos | ❌ **Não existia** → ✅ Fase 1 (item nº 1, ver §1.1) | `core/resilience.py` |

### 1.1 ✅ O modo de falha real **não** é o que o roteiro descreve

Este é o achado mais importante da auditoria, e ele muda o desenho do Pilar 1.

O roteiro parte de "o programa some da tela". Rodei os cenários nesta máquina,
com o PySide6 6.11.2 que o projeto usa:

```
$ QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe probe_qt_default.py
excepthook padrao: <built-in function excepthook>
-> clique
Traceback (most recent call last):
  File "probe_qt_default.py", line 7, in <lambda>
    botao.clicked.connect(lambda: 1 / 0)
                                  ~~^~~
ZeroDivisionError: division by zero
SOBREVIVEU (sem hook custom)
EXEC RETORNOU 0
EXIT CODE: 0
```

**O Qt não derruba o processo.** Uma exceção não tratada dentro de um slot é
impressa no `stderr` e o laço de eventos segue. O mesmo vale para override de
método virtual, com uma diferença que importa muito mais adiante:

```
$ QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe probe_qt_virtual.py
Error calling Python override of QWidget::paintEvent(): Traceback (most recent call last):
  ...
RuntimeError: estouro dentro do paintEvent
EXEC RETORNOU 0
PROCESSO CHEGOU AO FIM
EXIT CODE: 0
```

Agora junte isso com `console=False` em
[`packaging/build.spec:76`](packaging/build.spec) 🔍. No `.exe` empacotado não
há console anexado, então o que é escrito no `stderr` não vai a lugar nenhum.
Conclusão:

> **No food truck, o erro não derruba o programa — ele evapora.** O pai do
> Vitor clica em "Enviar Pedido", a tela não muda, nada é impresso, nada é
> gravado, nenhuma mensagem aparece, e **não fica registro nenhum** de que algo
> falhou. Ele vai clicar de novo, mais forte, e o pedido continua não saindo.

Isso reordena as prioridades desta etapa:

1. **O log rotativo (Pilar 5) deixa de ser acessório e vira o item nº 1.** Sem
   ele, hoje, um defeito em produção é literalmente indiagnosticável — não
   existe uma linha sequer para o Vitor ler depois.
2. **O modal amigável (Pilar 1) é a segunda metade**: o operador precisa saber
   que o clique morreu, ou vai repetir a ação achando que não clicou direito.
3. Existe **um** caminho em que o processo morre de verdade: exceção **fora**
   do laço de eventos — `_aplicar_migrations`, `_rodar_seed`, a montagem das
   views, o `consolidar_wal` do encerramento. Aí `main()` estoura e a janela
   nunca abre (ou some). Esse é o "sumiu da tela" de verdade, e é a única parte
   do Pilar 1 que precisa de `try/except` no `main`, não de hook.

### 1.2 🔍 `sys.excepthook` não cobre tudo — e o roteiro erra a biblioteca

O roteiro pede `report_callback_exception`. **Isso é API do Tkinter, e este
projeto não usa Tkinter** — é PySide6/Qt ([`pyproject.toml`](pyproject.toml)).
Não há equivalente em Qt. O mapeamento correto é:

> ⚠️ **Esta subseção foi corrigida pelo §1.6.** A tabela abaixo é o que a
> auditoria concluiu antes de o teste C6 rodar; a linha do override virtual
> estava **errada** e o §1.6 tem a medição que a desmente. Fica registrada
> porque foi ela que motivou a peça do espelho do `stderr`, que continua
> necessária — só que por outro motivo.

| Caminho da exceção | Passa por `sys.excepthook`? | Prova |
|---|---|---|
| Slot de sinal (`botao.clicked`) | ✅ **Sim** | `HOOK CHAMADO: ZeroDivisionError` no probe com hook |
| ~~Override virtual~~ | ~~❌ Não~~ → ✅ **Sim** (ver §1.6) | o `stderr` leva só o cabeçalho `Error calling Python override`; o traceback vai pelo hook |
| Fora do `app.exec()` (boot, teardown) | ✅ Sim, mas o processo já morreu | — |

O escudo acabou com **quatro** peças: `sys.excepthook`, o decorador
`nao_deixa_escapar` (§1.6), o espelho do `sys.stderr` — que segue valendo, tanto
pelo cabeçalho que o Qt escreve fora do hook quanto porque o `.exe` não tem
`stderr` nenhum — e o `try/except` no `main()`.

### 1.3 🔍 A impressora já está isolada — falta só a rede de contingência

`hardware/impressora_escpos.py` é trabalho maduro e não deve ser reescrito. Já
tem, com o motivo comentado no próprio código:

- Fronteira única — `ErroDeImpressao` é o **único** tipo que atravessa (linhas 66-77).
- `except Exception` largo no driver, proposital, porque pyusb/pyserial/socket
  não têm ancestral comum (linhas 195-203).
- `open()` antecipado, para o cabo solto estourar antes de gastar papel (linha 333).
- `write_timeout` imposto na serial à mão, porque o pyserial só limita leitura e
  o python-escpos não repassa o parâmetro (linhas 345-361). Sem isso, uma
  impressora desligada na COM3 **congelaria a janela para sempre**.

**O que falta:** a `fila_impressao_pendente`. Hoje, quando a impressão falha, o
`ImpressaoService` devolve `ResultadoImpressao(sucesso=False)`, a tela pinta o
aviso âmbar e **o cupom se perde**. A única saída é o operador achar a comanda e
clicar "2ª via" à mão. No pico, ele não vai.

### 1.4 ⚠️ Conflito real: "nunca bloquear a UI" contra a decisão da Fase 4

O roteiro exige que a impressão **nunca** rode na thread da UI. O projeto
decidiu explicitamente o contrário, e o motivo está escrito em
[`ui/widgets/aviso_impressao.py:34-40`](src/gestor_comercial/ui/widgets/aviso_impressao.py):

> DECISÃO DE ARQUITETURA: isto NÃO vai para uma QThread, mesmo que congele a
> tela por até 3 segundos (o timeout do driver). O app inteiro roda sobre um
> único `UnitOfWork`/`Session` do SQLAlchemy por processo, e `Session` não é
> thread-safe: mandar a impressão para outra thread trocaria um congelamento de
> 3 segundos por corrupção silenciosa do banco do food truck.

**A decisão da Fase 4 está certa, e obedecer o roteiro ao pé da letra
introduziria o pior bug do projeto.** Mas os dois podem ser satisfeitos ao mesmo
tempo, porque o congelamento e a `Session` não estão no mesmo pedaço do
trabalho. Uma impressão tem duas metades:

1. **Montar o documento** — lê comanda, itens, produtos, impressora. Toca a
   `Session`. É rápido (tudo em memória) e **precisa** ficar na thread da UI.
2. **Falar com o periférico** — abre USB/serial/rede, escreve, corta. **Não
   toca a `Session`**: recebe uma `list[BlocoTexto]`, que é
   `@dataclass(frozen=True)` de strings e bools
   ([`impressora_escpos.py:47-63`](src/gestor_comercial/hardware/impressora_escpos.py)),
   sem uma única referência a objeto ORM. É esta metade que demora e congela.

O corte já existe no código. A proposta é mandar **só a metade 2** para uma
thread, o que respeita a Fase 4 na íntegra (nenhuma `Session` cruza fronteira de
thread) e entrega o que o roteiro quer (a UI nunca congela). Ver Fase 3.

### 1.5 🔍 Sanitização: o roteiro descreve um risco que já foi tratado

`float(input)` no fluxo monetário **não existe**. O único `float()` do `src/`
inteiro é cosmético, um percentual de margem em
[`cardapio_view.py:86`](src/gestor_comercial/ui/views/cardapio_view.py). Mais
que isso, [`services/dinheiro.py:26-27`](src/gestor_comercial/services/dinheiro.py)
**recusa `float` explicitamente**, com `TypeError`, para 0.1+0.2 nunca virar
diferença no fechamento.

As 8 conversões de campo de texto para `Decimal` estão, todas, guardadas:

| Arquivo | Conversões | Guarda |
|---|---|---|
| `caixa_view.py` | 4 (`:649`, `:679`, `:715`, `:718`) | `except InvalidOperation` nos 3 chamadores (`:550`, `:570`, `:613`) 🔍 |
| `cardapio_view.py` | 3 (`:1062`, `:1122`, `:1124`) | validação prévia em `:1060-1068`, que marca o campo em vermelho 🔍 |
| `funcionarios_view.py` | 1 (`:739`) | `except InvalidOperation` em `:396` 🔍 |

**O que sobra, e é o risco de verdade:** a guarda é *convenção repetida em oito
lugares*, não *função única*. É exatamente o padrão que a remasterização passou
o §3.8 inteiro matando — dez cópias de `_formatar_reais`, uma delas divergente.
O nono campo monetário que alguém adicionar vai esquecer o `try`. A tarefa aqui
não é "criar sanitização", é **fechar a porta**: um `safe_decimal` central e um
teste que impeça a nona cópia de nascer.

Divisão por zero: 🔍 **falso alarme**, conferido depois. `_margem_percentual`
já devolve `0.0` quando `produto.preco is None or produto.preco <= 0`
([`cardapio_view.py:88-91`](src/gestor_comercial/ui/views/cardapio_view.py)) —
a guarda estava uma linha acima da que a auditoria leu.

E a contagem estava errada por baixo: eram **9** conversões, não 8. A nona vive
em [`pagamento_dialog.py:144`](src/gestor_comercial/ui/views/pagamento_dialog.py),
o diálogo mais crítico do sistema, e escapou tanto da varredura por
`replace(",", ".")` quanto da leitura arquivo a arquivo. Quem a encontrou foi a
trava automática da Fase 5, no primeiro segundo em que existiu — que é
exatamente o argumento a favor dela: a varredura manual erra, o teste não.

### 1.6 ✅ Onde o programa morre de verdade — e por que nenhum hook salva

Achado **posterior** ao §1.1, e ele **corrige** o §1.1 num ponto importante.
Quando o teste C6 rodou pela primeira vez, o resultado não bateu com o que a
auditoria tinha previsto. Investigando, apareceu isto:

```
$ QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe probe_virtual4.py; echo "EXIT: $?"
Error calling Python override of QWidget::paintEvent(): EXIT: 1
=== rastro ===
--- repaint 0
paintEvent entrou
HOOK: RuntimeError      <- o excepthook FOI chamado
--- repaint 1
paintEvent entrou
HOOK: RuntimeError
                        <- e aqui o processo morreu, sem chegar ao repaint 2
```

Duas conclusões, e as duas contrariam o que o §1.2 dizia:

1. **O `sys.excepthook` cobre, sim, o override virtual.** A tabela do §1.2
   estava errada nessa linha. O que o PySide6 escreve solto no `stderr` é só o
   cabeçalho `Error calling Python override`; o traceback vai pelo hook.
2. **E não adianta.** Na **segunda** ocorrência o Qt aborta o processo, com
   código de saída 1 — *depois* de o hook ter rodado e retornado. O `abort()` é
   do C++. Rodado de novo com o excepthook padrão, morre igual: não é efeito do
   escudo, é comportamento do PySide6 6.11.2.

Ou seja: **a premissa original do roteiro estava certa, e eu é que estava
errado ao descartá-la.** O programa *some da tela* — só que não por qualquer
exceção, e sim por esta classe específica delas. Os dois diagnósticos convivem:

| Caminho | O que acontece de verdade |
|---|---|
| Slot de sinal (`botao.clicked`) | App sobrevive indefinidamente; sem log, o erro **evapora** (§1.1) |
| **Override virtual** (`paintEvent`, `mousePressEvent`, `sizeHint`...) | 1ª vez registra, **2ª vez o processo morre e a janela some** |
| Fora do `app.exec()` | Processo morre na hora |

E a consequência prática é a Fase 2b, que não estava no plano: como nenhum hook
evita o abort, a **única** defesa é impedir a exceção de sair do override, do
lado Python. É um decorador, e ele é obrigatório.

O tamanho do risco no código de hoje: **16 overrides** em 10 arquivos, entre eles
o `mousePressEvent` do cartão de mesa
([`mesas_view.py`](src/gestor_comercial/ui/views/mesas_view.py)) — o toque mais
repetido do food truck inteiro — e dois `paintEvent`, que disparam por quadro.

---

## 2. Divergências do roteiro — decisões do Vitor  ✅ *respondidas em 2026-09-07*

Três pontos em que executar a instrução literalmente **pioraria** o sistema.
Todos levados ao Vitor antes de qualquer linha de código.

| # | O roteiro pede | O projeto tem hoje | Decisão |
|---|---|---|---|
| D1 | Backup mantendo **7 dias** | `BACKUPS_MANTIDOS = 60` (~2 meses), decisão documentada em [`backup.py:37-41`](src/gestor_comercial/repository/backup.py) | ✅ **Manter 60.** Reduzir para 7 é jogar fora histórico já pago, e o argumento de disco não se sustenta: são `.db` pequenos e já desfragmentados pelo `VACUUM` |
| D2 | Backup via `conn.backup()` | `VACUUM INTO` | ✅ **Manter `VACUUM INTO`.** É superior aqui: gera um `.db` único e já consolidado, sem arquivo `-wal` companheiro para o pai do Vitor esquecer de copiar junto para o pendrive |
| D3 | Impressão **nunca** na thread da UI, timeout **1,5 s** | Impressão na thread da UI por decisão escrita da Fase 4, `timeout_s = 3.0` | ✅ **Cortar ao meio** (§1.4): montar o documento fica na UI, falar com o periférico vai para a thread. Timeout **fica em 3,0 s** — o 1,5 s só existia para encurtar o congelamento; sem congelamento, encurtar só desiste de uma impressora lenta que teria funcionado |

E uma correção de premissa, decidida por ser factual e não opinativa:

| # | O roteiro pede | Realidade | O que será feito |
|---|---|---|---|
| D4 | `report_callback_exception` do Tkinter | O projeto é PySide6 | Escudo de 3 peças do §1.2. Sem Tkinter em lugar nenhum |

---

## 3. O plano

### Fase 0 — Rede de segurança  `[x]`

✅ Baseline registrado no §0: **801 passando**, working tree limpo exceto o §10
staged do `REMASTERIZACAO-V1.md`, que não entra no commit desta etapa.

---

### Fase 1 — Caixa-preta: log rotativo  `[x]`  ⬅ *item nº 1, ver §1.1*

Criar `src/gestor_comercial/core/resilience.py` — módulo novo, só stdlib
(`sys`, `logging`, `logging.handlers`, `traceback`, `pathlib`).

- `configurar_log()` monta um `RotatingFileHandler` — **2 MB, 2 backups**, como
  pedido. Teto de 6 MB de disco, para sempre.
- Destino: `<dir_dados>/logs/gestor.log`, ao lado do banco. **Não** dentro do
  `.exe`: o PyInstaller extrai numa pasta temporária e o log sumiria a cada
  boot. Reaproveita a derivação em runtime de `backup.pasta_backups()`.
- `encoding="utf-8"` explícito, e `delay=True` — não abre o arquivo até a
  primeira linha, economia de handle no boot, coerente com o RNF de otimização.

✅ **Feito** em [`core/resilience.py`](src/gestor_comercial/core/resilience.py),
com `core/` nascendo como camada mais baixa do projeto — sem import de
`repository/`, `services/` nem `ui/`, para poder subir antes de tudo o que pode
falhar. Ligado na **primeira linha** de `main()`.

5 testes em [`tests/unit/test_resiliencia.py`](tests/unit/test_resiliencia.py):
tamanho e rotação, idempotência, `delay=True`, pasta impossível que não derruba
o boot, e `propagate=False` (sem ele o Alembic faria cada linha sair duas vezes).

---

### Fase 2 — Escudo global  `[x]`

No mesmo `core/resilience.py`:

1. **`instalar_escudo()`** → `sys.excepthook` que grava `traceback.format_exc()`
   no log e chama o modal.
2. **Desvio do `stderr`** para o logger — a única forma de capturar exceção em
   override virtual (§1.2), e a única forma de qualquer coisa ser vista no
   `.exe` com `console=False`.
3. **`try/except` no `main()`** cercando migrations, seed, montagem das views e
   teardown — o único caminho que mata o processo de verdade.

**Modal amigável**, com o texto do roteiro e uma emenda: um botão discreto
"Ver detalhes" mostrando o caminho do arquivo de log. Sem isso o Vitor depende
do pai conseguir descrever o erro por telefone.

> Ocorreu uma oscilação pontual nesta ação, mas seus dados continuam salvos.
> O sistema continua operando.

**Guarda-corpo obrigatório:** o modal precisa de anti-repique. Uma exceção em
`paintEvent` dispara a cada repintura — sem limitador, o operador leva centenas
de modais e o PDV fica inutilizável, que é justamente o travamento que o escudo
deveria evitar. Logar sempre; **mostrar o modal no máximo 1× a cada N segundos
por tipo de erro**.

✅ **Feito.** 12 testes em `test_resiliencia.py` e `test_caos.py`. O anti-repique
saiu com janela de 30 s por assinatura (`TipoDoErro@arquivo.py:linha`), e limpa
as entradas vencidas para não virar um dicionário crescente ao longo de semanas
ligado.

Uma emenda que a implementação exigiu: o espelho do `stderr` **espelha em vez de
substituir**. Trocar um pelo outro obrigaria a escolher entre ver o traceback no
terminal em desenvolvimento e ter evidência em disco no `.exe`. E ele tem trava
de reentrância — o `logging` escreve no `stderr` quando ele próprio falha
(`handleError`), o que sem a trava viraria recursão infinita: o escudo matando o
programa que veio proteger.

---

### Fase 2b — Blindagem dos overrides virtuais  `[x]`  ⬅ *não estava no plano, ver §1.6*

O único caminho que realmente mata o processo, e o único que hook nenhum
resolve. Decorador `nao_deixa_escapar` aplicado aos **16 overrides** do projeto,
com o valor de retorno seguro de cada assinatura — `False` num `eventFilter`,
`QSize(0, 0)` num `sizeHint`. Devolver `None` nesses dois trocaria o abort por um
`TypeError` na conversão para C++, o mesmo problema com outro nome.

A trava é o `test_todo_override_virtual_esta_blindado`, que varre `ui/` pelo
marcador que o próprio projeto já usava antes desta etapa (`# noqa: N802
(override Qt)`). **Ela pagou na primeira execução**: pegou dois overrides que a
minha varredura manual tinha perdido — o `done()` dos dois diálogos de PIN.

---

### Fase 3 — Impressora: fila de contingência + saída da thread da UI  `[x]`

1. **Tabela** `fila_impressao_pendente` (migration Alembic), guardando o
   `Documento` já montado (JSON dos `BlocoTexto`), a impressora de destino, o
   horário e o número da tentativa.
2. **Gravar na fila** quando `ResultadoImpressao.sucesso == False`, dentro do
   `ImpressaoService._enviar` — que já é o funil único de toda impressão
   ([`impressao_service.py:364-390`](src/gestor_comercial/services/impressao_service.py)).
3. **Aviso discreto**: reaproveitar o `AvisoDeImpressao` âmbar que já existe,
   trocando o texto para "Impressora não respondeu. Cupom salvo na fila para
   reimpressão."
4. **Tirar da thread da UI** só a metade que fala com o periférico, conforme
   §1.4. Nenhuma `Session` cruza fronteira de thread — o que atravessa é
   `list[BlocoTexto]`, imutável.

✅ **Feito.** O corte do §1.4 funcionou como previsto, e a parte mais importante
é o que **não** precisou mudar: `hardware/impressora_escpos.py` sempre leu a
impressora por `getattr`, com a docstring dizendo que isso "permite testar com um
objeto qualquer que tenha os campos certos". O desacoplamento já estava pronto
antes de existir motivo para usá-lo — bastou criar o retrato
(`ParametrosImpressora`) e passá-lo no lugar da entidade.

O que ficou:

- **`fila_impressao_pendente`** (migration `e5a1c9b73d24`) guarda o **documento
  montado** em JSON, não o id da comanda. Três motivos na docstring da entidade;
  o principal é que reimprimir tem que sair igual ao que teria saído na hora, e
  remontar semanas depois pegaria preço novo e item cancelado depois. Teto de 200
  cupons, descartando os mais antigos: a fila é rede de contingência, não
  histórico, e o alvo é um Celeron.
- **A thread** roda só a conversa com o cabo. O que atravessa é
  `ParametrosImpressora` + `list[BlocoTexto]`, os dois `frozen=True`, sem uma
  referência de ORM. Um teste próprio tranca isso
  (`test_o_que_atravessa_para_a_thread_nao_tem_vinculo_com_o_banco`), porque é a
  garantia mais fácil de perder numa refatoração distraída.
- **A espera** (`aguardar_repintando`) é injetada pela UI — `services/` não
  importa Qt. Ela existe por um motivo específico do Windows: thread principal
  parada em `join()` faz o sistema desenhar "Não Está Respondendo" por cima do
  PDV, e no balcão isso é indistinguível de travamento.
- **O painel na tela de Impressoras**, com Reimprimir e Descartar. Não estava no
  roteiro, mas sem ele o aviso "o cupom ficou salvo na fila para reimpressão"
  seria promessa vazia — não haveria onde reimprimir. Some quando a fila está
  vazia, que é o dia normal.

Duas emendas que a implementação obrigou:

1. **O commit da fila é separado.** Dos cinco caminhos de impressão só
   `imprimir_comanda` commitava; o cupom guardado não pode depender de qual botão
   o operador apertou. Isso mudou a contagem de commits de um teste existente,
   que foi atualizado com o porquê.
2. **Trava de reentrância na espera.** `ExcludeUserInputEvents` segura a entrada
   do operador, mas foi **medido** que evento postado por código atravessa a
   exclusão. Da segunda espera aninhada em diante o bombeamento é desligado, para
   a pilha não crescer sem fim.

---

### Fase 4 — SQLite: `busy_timeout`  `[x]`

Uma linha em [`repository/base.py`](src/gestor_comercial/repository/base.py), no
listener que já aplica os outros PRAGMAs:

```python
cursor.execute("PRAGMA busy_timeout=5000")
```

`foreign_keys=ON` e `journal_mode=WAL` já estão lá 🔍. `synchronous` fica no
`FULL` padrão **de propósito** — baixar para `NORMAL`, como todo guia de WAL
sugere, protege contra o app morrer mas **não** contra a energia cair no meio do
commit, que é exatamente o cenário do food truck e exatamente o que
`tests/integration/test_resiliencia_queda_energia.py` tranca hoje.

Backup (Pilar 3b): **nada a fazer** além de confirmar D1 e D2. Já roda no
fechamento de caixa
([`caixa_service.py:397-400`](src/gestor_comercial/services/caixa_service.py)) e
sob demanda pela tela de Configurações.

✅ **Feito**, uma linha ao lado dos outros dois PRAGMAs, com o motivo escrito na
docstring que já explicava o WAL: sem o timeout o SQLite não espera *pouco*, ele
não espera *nada* — desiste no primeiro encontro e devolve `database is locked`.

---

### Fase 5 — `safe_decimal` e o fim da nona cópia  `[x]`

✅ **Feito** em [`ui/formatacao.py`](src/gestor_comercial/ui/formatacao.py), ao
lado de `formatar_para_campo`, de quem é a função inversa — mesmo argumento do
§3.8: se "como o dinheiro vira texto" tem um dono só, "como o texto vira
dinheiro" também precisa ter, ou a divergência volta pela outra ponta.

Três decisões que a implementação obrigou:

1. **Devolve `Decimal`, nunca `float`.** A assinatura do roteiro diz
   `default=0.0`; um `float` aqui seria recusado por `dinheiro()` três linhas
   adiante, com `TypeError` (§1.5).
2. **`padrao=None` é o modo dos campos obrigatórios.** Ler "não consegui
   entender o que ele contou" como "ele contou zero" inventaria, no fechamento
   de caixa, uma diferença do tamanho do turno — e o pai do Vitor iria procurar
   dinheiro que nunca faltou. Fechamento, pagamento, sangria e quitação usam
   `None`; o custo do produto, que pode legitimamente ficar em branco, usa zero.
3. **Com `,` e `.` juntos, o último manda.** Testar a posição em vez de assumir
   o padrão brasileiro faz `"1.234,56"` (o que a tela ao lado mostra) e
   `"1,234.56"` (valor colado de planilha) serem lidos certo, em vez de erro.

Foram **9** conversões, não 8 — a nona, em `pagamento_dialog.py`, foi encontrada
pela trava e não por mim (§1.5). A trava e 27 casos do que o operador realmente
digita estão em [`tests/unit/test_safe_decimal.py`](tests/unit/test_safe_decimal.py).

---

## 4. Testes de caos

Os três do roteiro, mais três que a auditoria mostrou serem necessários.
**6 de 6 verdes.**

| # | Cenário | Esperado | Estado |
|---|---|---|---|
| C1 | `1 / 0` dentro do clique de um botão | App vivo, linha no log, 1 modal — **e o clique seguinte ainda funciona** | ✅ |
| C2 | Driver pendurado numa porta que não responde | Chamada **volta**, venda conclui, cupom na fila | ✅ |
| C3 | Letras em campo de valor | Campo marcado, sem exceção | ✅ |
| C4 | Mesmo defeito disparando 200× | 1 modal (anti-repique), 200 linhas de log | ✅ |
| C5 | Exceção no boot, antes do `app.exec()` | Modal de erro **em vez de** janela que nunca abre | ✅ |
| C6 | 50 estouros num `paintEvent` | Processo **vivo** — sem o decorador, morre no 2º (§1.6) | ✅ |

O C1 ganhou uma segunda metade que não estava prevista
(`test_c1_o_app_continua_respondendo_depois_do_erro`): sobreviver não basta, o
clique seguinte tem que funcionar. No balcão, um PDV vivo mas surdo é a mesma
coisa que um PDV fechado.

---

## 5. Restrições respeitadas

- **Só stdlib**: `sys`, `logging`, `traceback`, `sqlite3`, `decimal`, `pathlib`.
  Sem Sentry, sem watchdog, sem daemon externo.
- **Teto de ~90 MB de RAM**: o custo desta camada é um `RotatingFileHandler`
  (`delay=True`, um handle de arquivo) e uma tabela SQLite que fica vazia no
  caminho feliz. Nenhuma thread permanente — a da Fase 3 nasce e morre por
  impressão.
- **Nenhuma decisão da remasterização é revertida** sem estar no §2.

---

## 6. Registro de decisões

| Data | Decisão | Porquê |
|---|---|---|
| 2026-09-07 | O Pilar 5 (log) vira o item **nº 1**, antes do modal | ✅ O Qt não derruba o app: o erro evapora no `stderr` de um `.exe` sem console. Hoje um defeito em produção é indiagnosticável — falta a primeira linha de evidência, não a primeira mensagem |
| 2026-09-07 | Escudo de **3 peças**, não `sys.excepthook` sozinho | ✅ Exceção em override virtual (`paintEvent`) não passa pelo hook: o PySide6 escreve direto no `stderr` |
| 2026-09-07 | `report_callback_exception` **descartado** | 🔍 É API do Tkinter; o projeto é PySide6 |
| 2026-09-07 | Impressão sai da thread da UI **só na metade do periférico** | 🔍 A decisão da Fase 4 (`aviso_impressao.py:34-40`) está certa: `Session` em outra thread = corrupção silenciosa. O corte no `list[BlocoTexto]` imutável satisfaz os dois requisitos |
| 2026-09-07 | Modal com **anti-repique** obrigatório | Erro em repintura dispara por frame; sem limitador o escudo vira o travamento que ele deveria evitar |
| 2026-09-07 | `safe_decimal` devolve `Decimal`, não `float` | 🔍 `dinheiro()` recusa `float` com `TypeError` de propósito (0.1+0.2 vira diferença no fechamento) |
| 2026-09-07 | **Correção do próprio §1.2**: o `excepthook` cobre override virtual, sim | ✅ O teste C6 desmentiu a auditoria. O `stderr` leva só o cabeçalho; o traceback vai pelo hook |
| 2026-09-07 | **Fase 2b criada fora do plano**: decorador `nao_deixa_escapar` | ✅ Na 2ª exceção num override virtual o Qt **aborta o processo**, depois de o hook rodar. É o "some da tela" de verdade, e hook nenhum evita — só impedir a exceção de chegar ao C++ |
| 2026-09-07 | O espelho do `stderr` **espelha**, não substitui | Substituir obrigaria a escolher entre ver o traceback no terminal em dev e ter evidência em disco no `.exe` |
| 2026-09-07 | `safe_decimal` ganhou `padrao=None` para campo obrigatório | Ler "não entendi o que ele contou" como "ele contou zero" inventaria uma diferença de caixa do tamanho do turno |
| 2026-09-07 | Travas por teste em vez de convenção (overrides e conversão monetária) | ✅ As duas pagaram na primeira execução: acharam 2 overrides e 1 conversão que a varredura manual perdeu |
| 2026-09-07 | A fila guarda o **documento montado**, não o id da comanda | Reimprimir tem que sair igual ao que teria saído na hora; e fechamento de caixa e teste de impressora não têm de onde ser remontados |
| 2026-09-07 | O cupom guardado tem **commit próprio** | Dos cinco caminhos de impressão só um commitava. O registro de que algo não saiu no papel não pode depender de qual botão foi apertado |
| 2026-09-07 | Painel da fila na tela de Impressoras (fora do roteiro) | Sem onde reimprimir, o aviso "o cupom ficou salvo na fila" seria promessa vazia |
| 2026-09-07 | Trava de reentrância na espera da UI | ✅ Medido: evento postado por código atravessa o `ExcludeUserInputEvents`. Sem a trava, a pilha de esperas aninhadas cresceria sem fim |
