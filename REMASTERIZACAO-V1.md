# Remasterização da Versão 1.0

> **O que é este documento.** A planta da faxina cirúrgica final do Solvix POS
> (Gestor Comercial Python) antes de ir para produção real no food truck.
> Nenhuma funcionalidade nova entra aqui. O objetivo é unificar a arquitetura,
> matar duplicação, extinguir código morto e blindar o ciclo de vida de memória
> para o sistema aguentar **semanas ligado num Celeron de 4 GB sem degradar**.
>
> É um documento **vivo e sequencial**: cada fase tem checkbox, critério de
> pronto e como validar. Marque `[x]` só depois de a suíte de testes passar.
> Status geral e escopo do produto continuam em [`TODO.md`](TODO.md) e
> [`docs/arquitetura.md`](docs/arquitetura.md).
>
> **Para leitura não técnica:** o **§10** conta esta mesma remasterização em
> português de balcão — o que o programa ganhou, sem jargão. É por onde começar
> se a pergunta é "o que melhorou?" em vez de "como foi feito?".
>
> **Legenda de confiança dos achados:**
> ✅ **provado** — reproduzido nesta máquina, com saída de execução colada aqui.
> 🔍 **verificado** — código aberto e conferido linha a linha.
> ⚠️ **reportado** — levantado pela auditoria, ainda sem verificação independente.

---

## 0. Onde paramos — 2026-09-06

**Remasterização concluída. As 8 fases (0 a 7) estão fechadas.**
Suíte: **800 passando, 0 `xfail`, 0 falhas** — de 620/621 (1 falha) no começo.

| Fase | Estado |
|---|---|
| 0 — Rede de segurança | ✅ concluída |
| 1 — Integridade de dados | ✅ concluída |
| 2 — Núcleo de dados e performance | ✅ concluída |
| 3 — Utilitários compartilhados | ✅ concluída |
| 4 — Ciclo de vida da UI (escopo enxuto) | ✅ concluída |
| 5 — Higiene da UI | ✅ concluída — 9 de 9 itens |
| 6 — Arquitetura da UI | ✅ concluída — só a duplicação real |
| **7 — Validação final** | ✅ **concluída** |

### O que a Fase 7 fechou

A validação comparou o sistema inteiro com o código de **antes da
remasterização** (`b22da75`), pelos dois produtos que o pai do Vitor enxerga: a
tela e o papel.

| Frente | Resultado |
|---|---|
| Suíte | 800 verdes, sem teste apagado, enfraquecido ou `skip` |
| Telas | 11 telas × 2 temas + 2 estados de filtro = **24 renderizações** comparadas pixel a pixel |
| Impressão | os 6 documentos ESC/POS, **idênticos linha a linha** (só o relógio normalizado) |
| Bancadas | `tools/comparar_telas.py` passou a montar a `MainWindow` real e cobrir as 10 telas; `tools/comparar_cupons.py` nasceu para o papel |

Das 24 renderizações, **9 são byte a byte idênticas** e **15 diferem** — cada
diferença rastreada até a fase que a causou e conferida uma a uma:

- **13** são os defeitos que a remasterização **consertou**, agora visíveis
  lado a lado: widget fantasma sobrando na grade de Mesas e no cartão de
  fechamento do Caixa (§3.7), célula empilhada por cima da anterior em Cardápio
  e Impressoras (§3.3), cor escura congelada no tema claro e inicial errada no
  avatar da Comanda e do Dashboard (§3.15).
- **2** são a tela de Configurações, que ganhou a seção "Cópia de Segurança" na
  Fase 2 — e onde a comparação achou o único **defeito novo** da
  remasterização.

### 🔴 O que a Fase 7 encontrou: a tela de Configurações espremida

A seção nova empurrou o conteúdo para além da altura da página e o
`QVBoxLayout` sem rolagem **espreme os filhos** em vez de rolar: os quatro
botões "Alterar"/"Cadastrar" de Senhas e Acesso caíram de 39px para **14px, sem
rótulo nenhum**, com os textos das linhas sobrepostos. Num monitor de 768px — a
classe de máquina do food truck — a tela ficava inutilizável.

Nenhum dos 799 testes pegava isso: teste de widget não mede pixel, e a suíte
roda sem banco de fontes. Corrigido com `QScrollArea` (o mesmo padrão do
Histórico e do Dashboard) e travado por
`tests/ui/test_telas_cabem_na_tela.py`, que aperta a moldura pela metade do que
a **própria tela** pede — medida relativa, para o teste também reprovar na
máquina sem fonte instalada.

### O que continua aberto (não é da remasterização)

- **`.exe` em máquina limpa de verdade** — `docs/checklist-maquina-limpa.md`,
  e depois a validação com o pai do Vitor.

### O que veio depois da remasterização

- ✅ **Tela de Caixa a 768px — corrigida em 2026-09-06** (§9). O cartão
  "Recebimentos" cortava as quatro linhas ao meio, e **não era regressão**:
  `b22da75` cortava igual. Ficou de fora da faxina porque mexer no layout
  durante a comparação tiraria a paridade contra a qual comparar; foi o
  primeiro item assim que ela fechou. Suíte: **801**.
- ✅ **Sete modais em cartão** (§9.4 a §9.7, §9.9) e a **subcategoria como
  entidade** (§9.8/§9.9), entre 2026-09-08 e 2026-09-09.
- ✅ **O turno-fantasma, a barreira de exclusão e o olho das senhas — 2026-09-09**
  (§9.10). O defeito de persistência que o Vitor relatou tinha duas causas, e
  **nenhuma delas na exclusão**: o `run_seed()` repovoando a cada boot e o
  `Usuario` de login que nunca era excluído junto do `Funcionario`. Suíte:
  **1418**.
- ✅ **O Cardápio em cartões — 2026-09-11** (§9.11). A árvore e a lista de
  produtos passaram a ser **pintadas por delegado**, sem widget por linha: o
  crescimento de RSS em 60 trocas de categoria caiu de +37,7 MB para +0,7 MB,
  a troca de 34 para 8 ms e a recarga de 39 para 10 consultas. Margem e
  números do topo foram para o service, e o roteamento de impressão não foi
  tocado (cupons idênticos). Suíte: **1495**.

---

## 1. Correção de premissas do briefing

O briefing desta remasterização descrevia uma stack que **não é a deste
projeto**. Registrado para não guiar decisão errada mais na frente:

| Premissa do briefing | Realidade verificada na base |
|---|---|
| Tkinter / CustomTkinter | **PySide6 (Qt)**. `grep -rn "tkinter" src` → **0 ocorrências** |
| `sqlite3` cru, `with closing(conn.cursor())` | **SQLAlchemy 2.0 ORM**. `import sqlite3` → **0**. Não há um único cursor manual no projeto |
| `widget.destroy()`, `unbind`, `after_cancel` | API Tk. Equivalente Qt: `deleteLater()` / `disconnect()` / `QTimer.stop()` |
| Timers `after()` pendentes | **Não existe nenhum `QTimer`, `singleShot`, `startTimer` nem thread no projeto.** Todo refresh é sob demanda, na navegação |
| `PhotoImage` com `lru_cache` | API Tk. Aqui é `QPixmap` + `ui/widgets/thumbnail_cache.py` — **que já tem LRU com teto de 200 entradas** (§3.10) |
| "zero ORMs" | SQLAlchemy é fundação do projeto desde a Fase 1. Arrancá-lo é reescrever o sistema, não limpá-lo |

**Como a regra foi interpretada.** "Zero ORM / zero dependência pesada" vale
como: **nenhuma dependência nova entra** nesta remasterização. O SQLAlchemy
fica. As regras de higiene continuam valendo, traduzidas para Qt e para o ORM —
e o vazamento que o briefing suspeitava **existe mesmo**, só que noutro lugar.

> **A tabela acima vale para todo pedido que vier depois.** O §9.10 chegou
> pedindo de novo `destroy()`, `unbind()` e `after_cancel()`: continua sendo a
> API do Tk, e continua traduzida do mesmo jeito — `executar_modal()` + o
> `done()` do diálogo (descarte), método ligado em vez de `lambda` no `connect`
> (§3.14, que é o "unbind" que importa aqui) e `QTimer.stop()` no `done()`/
> `hideEvent` (o "after_cancel"). O que o pedido quer dizer é ciclo de vida
> limpo; o que muda é só o nome das funções.

---

## 2. Linha de base medida — o "antes"

### 2.1 Tamanho

| | |
|---|---|
| Arquivos `.py` (src + tests) | 106 |
| Linhas em `src/` | 17.697 |
| Linhas em `tests/` | 6.794 |
| Maior arquivo | `ui/views/cardapio_view.py` — 1.343 linhas |
| Camada `ui/` | ~8.000 linhas (≈45% do código) |

### 2.2 Suíte de testes

```
621 testes → 620 passam, 1 falha
```

- ✅ **`test_resumo_mensal_sem_nenhum_fechamento_no_mes` falha.** Não é bug de
  produção: o comportamento mudou de propósito no commit `fa0e650` — `resumo_mensal`
  passou a devolver as 5 formas de pagamento com valor zero em vez de lista
  vazia, e o teste ficou para trás. **O teste é que está errado.**
- ✅ **A camada `ui/` tem cobertura ZERO.** Os 621 testes cobrem
  services / repository / hardware; nenhum instancia um widget. Quase metade do
  código seria refatorada sem rede de segurança — é o maior risco desta
  operação e a Fase 0 existe por causa disso.

### 2.3 Memória — medido headless (`QT_QPA_PLATFORM=offscreen`)

> #### 🔴 AVISO (Fase 4): os números desta seção são artefato de medição
> Os +40,8 MB e os "300 de 300 modais vivos" abaixo **não descrevem o app**.
> Foram medidos sem `exec()` e sem `sendPostedEvents(DeferredDelete)` — e sem
> isso um `deleteLater()` legítimo fica pendente para sempre, indistinguível de
> vazamento. Pelo caminho que o app percorre, os mesmos 300 modais custam
> **+0,5 MB** e deixam **0 vivos**. Reproduza os dois com
> `python tools/medir_memoria.py [--roteiro-antigo]`. A seção fica como está,
> com este aviso, porque é a origem documentada de três achados derrubados
> (§3.2, §3.3 e este) — apagá-la esconderia a lição.

| Estágio | RSS |
|---|---|
| Interpretador nu | 17,9 MB |
| + `QApplication` | 38,1 MB |
| + migrations Alembic + seed | 116,1 MB |
| **+ shell completo, 10 telas montadas** | **154,5 MB ← baseline** |
| + 300 aberturas do modal mais simples | 195,3 MB (**+40,8 MB**) |

✅ **300 de 300 modais continuavam vivos** após `reject()`, `del`,
`gc.collect()` e `processEvents()`.

### 2.4 Banco

| | |
|---|---|
| `PRAGMA foreign_keys` | ✅ **0 — desligado.** As 20 FKs do schema não são aplicadas |
| `PRAGMA journal_mode` | ✅ `delete` (não WAL) |
| Índices declarados | ✅ **zero** — nenhum `index=True`, `Index()`, `__table_args__` ou `create_index` em toda a base |
| Identity map da Session eterna | ✅ **não cresce** — SQLAlchemy usa referências fracas. *Hipótese inicial refutada por medição* |

---

## 3. Diagnóstico — FASE 1

Método: 11 vetores de auditoria em paralelo sobre os 106 arquivos. Os achados
de maior impacto foram reproduzidos nesta máquina antes de entrar aqui.

### 3.1 🔴 Rollback nunca acontece — estado sujo é gravado por outra operação

**Severidade: CRÍTICA.** ✅ **provado.** O achado mais grave da auditoria, e o
único que corrompe dado.

`repository/unit_of_work.py` promete na própria docstring:

> "ou as três coisas são gravadas, ou nenhuma é: `commit()` no fim do service,
> `rollback()` se qualquer regra estourar."

Mas `rollback()` é chamado em **exatamente um lugar**: `UnitOfWork.__exit__`
(linha 69). E `with UnitOfWork(...)` **não é usado em lugar nenhum** — nem em
`src/`, nem em `tests/`. `main.py:95` faz `uow = UnitOfWork()` solto.

**Consequência:** `__exit__` nunca roda → **`rollback()` nunca executa em
produção.** Quando um service muta objetos e depois estoura numa regra de
negócio, o estado sujo fica na Session e é gravado pelo **próximo `commit()` de
uma operação sem nenhuma relação com ele**.

**Reproduzido com os serviços reais:**

```
nome gravado no início        : Cozinha
operação abortou como esperado: RegraDeNegocioError
nome no banco DEPOIS          : NOME QUE NAO DEVIA PERSISTIR

>>> CONFIRMADO: a alteração abortada foi gravada pelo commit de outra operação.
```

O roteiro: editar uma impressora com nome novo + host inválido → o service
levanta `RegraDeNegocioError` e a edição é rejeitada na tela → em seguida o
gerente cadastra uma **categoria** → o `commit()` dessa categoria grava também
o nome da impressora que tinha sido rejeitado.

Num sistema que movimenta dinheiro, isso é inaceitável antes de produção. E
casa exatamente com o RNF do projeto: *"Confiabilidade: tratado e testado antes
de produção real."*

**Correção:** `rollback()` em todo caminho de erro. Duas frentes:
1. `main.py` passa a usar `with UnitOfWork() as uow:` — o `__exit__` volta a
   existir de verdade.
2. Um decorator/context manager de transação nos services, para que qualquer
   exceção reverta a Session antes de voltar para a UI.

**Risco associado (⚠️ reportado):** `IntegrityError`/`OperationalError` deixam a
Session em `PendingRollbackError` permanente — sem rollback, o app fica inútil
até reiniciar o processo. A mesma correção resolve os dois.

### 3.2 ✅ Os 31 modais nunca são destruídos — **achado corrigido na Fase 3, sites padronizados na Fase 5**

> #### ⚠️ Correção (2026-09-06, Fase 3): a medição não reproduz pelo caminho real
> Este achado foi remedido com PySide6 6.11.2 e um **laço de eventos rodando de
> verdade** (`app.exec()`), nas plataformas `offscreen` e `windows`:
>
> | Cenário | Diálogos presos |
> |---|---|
> | 30 construídos e fechados com `reject()`, **sem `exec()`** | **30** |
> | 30 abertos com `exec()` — **o caminho real do app** | **0** |
>
> O vazamento existe, mas só no caminho que a bancada de medição percorria.
> Abrir de verdade, com `exec()`, já libera o diálogo — e todos os 31 sites do
> app abrem com `exec()`. A severidade cai de 🔴 ALTA para 🟡, e o
> `+40,8 MB de RSS` da tabela abaixo **não é atribuível aos modais**.
>
> `ui/widgets/modais.py` foi entregue mesmo assim (Fase 3): passou a ser
> garantia explícita em vez de dependência de um detalhe de implementação do
> Qt, e é barato o bastante para valer numa máquina que fica semanas ligada.
> O que muda é a **prioridade** da Fase 4, não a existência do utilitário.

**Severidade original: ALTA.** ✅ provado *pela bancada*, ❌ **não reproduzido**
pelo caminho de produção. O texto abaixo é o achado como foi escrito.

```python
modal = CancelamentoDialog(titulo, self)   # parent = a view
if modal.exec() != QDialog.DialogCode.Accepted:
    return                                  # sai sem destruir nada
```

O nome Python sai de escopo, mas **quem detém a posse é o parent em C++**. E
nenhuma view morre: `main_window.py:138-182` monta as 10 telas no boot dentro
de um `QStackedWidget` que vive o processo inteiro.

`grep -rn "deleteLater\|WA_DeleteOnClose" src/gestor_comercial/ui` → **zero**
ocorrências sobre diálogos.

| Cenário medido | Resultado |
|---|---|
| 50 aberturas de `CancelamentoDialog` | 50 vivos, **400 QWidgets** presos |
| 300 aberturas, app completo montado | 300 vivos, **+40,8 MB** de RSS |
| 80 aberturas de `BuscaProdutoWidget` | 80 vivos, ~1.200 QObjects |

Os 31 pontos: `main_window.py:330, 348, 409` · `caixa_view.py:510, 530, 573` ·
`cardapio_view.py:441, 457, 489, 668, 691, 740, 761, 877` ·
`comanda_view.py:597, 619, 710, 750, 784, 811` ·
`configuracoes_view.py:214, 233, 252, 273` · `funcionarios_view.py:310, 328, 392` ·
`historico_caixa_view.py:454, 486` · `impressoras_view.py:439, 457`.

**Frequência é alta por decisão de projeto:** o PIN é exigido a cada acesso à
Central de Loja e ao Caixa (`main_window.py:327-329, 344-347`), então cada ida e
volta na navegação deixa um diálogo para trás. `PagamentoDialog` vaza uma vez
por venda. `_AdicionarItemDialog` vaza uma vez por item lançado — e cada
instância ainda retém a lista inteira de produtos ORM (§3.4).

> #### ⚠️ Armadilha: `WA_DeleteOnClose` seria a correção ERRADA
> Vários modais são **lidos depois** do `exec()`: `modal.resultado()`
> (`cancelamento_dialog.py:52`), `modal.comanda_fechada` (`main_window.py:411`),
> `caixa.clickedButton()` (`cardapio_view.py:502`, `comanda_view.py:725`). Com
> `WA_DeleteOnClose` o objeto C++ já estaria destruído nessa leitura →
> `RuntimeError`. Além disso `accept()`/`reject()` passam por `done()`, que faz
> `hide()`, **não** `close()` — o atributo nem dispararia.
>
> **A correção certa é liberar depois de ler o resultado**, com `try/finally`.

```python
# ui/widgets/modais.py (novo)
def executar_modal(modal: QDialog) -> int:
    """Executa o modal e libera a instância — nenhum diálogo fica pendurado na
    view (que vive o processo inteiro). Ver REMASTERIZACAO-V1.md §3.2."""
    try:
        return modal.exec()
    finally:
        modal.deleteLater()
```

**Cuidado:** `cardapio_view.py:668-684` e `:691-704` usam
`while modal.exec() == Accepted:`, **reaproveitando o mesmo modal** entre
iterações. Ali o descarte fica **fora** do `while`.

### 3.3 ✅ `setCellWidget` não destrói o widget anterior — ❌ **achado derrubado na Fase 3, views padronizadas na Fase 5**

> #### ❌ Correção (2026-09-06, Fase 3): com laço de eventos, não vaza
> Escrever o teste de premissa da Fase 3 derrubou este achado. Medido com
> PySide6 6.11.2 e `app.exec()` rodando:
>
> | Cenário | Widgets vivos | Esperado se vazasse |
> |---|---|---|
> | `setCellWidget` 50x na mesma célula | **1** | 50 |
> | `setRowCount(0)` por 20 ciclos | **0** | 20 |
> | `CardapioView.atualizar()` 21 vezes | **78 → 78** | 78 → 1.638 |
>
> O Qt agenda a destruição do ocupante anterior e recolhe no ciclo seguinte. A
> medição original rodou **sem laço de eventos** — e sem laço um `deleteLater()`
> legítimo fica pendente para sempre e é indistinguível de um vazamento. É a
> mesma causa raiz da correção do §3.2.
>
> `ui/widgets/tabelas.py` foi entregue (Fase 3), mas o que ele dá é
> **determinismo**, não correção de vazamento: o widget antigo sai da árvore no
> ato, antes do próximo repaint, em vez de continuar filho do viewport na
> geometria velha. É a mesma garantia do §3.7 — que ali já custou dois bugs
> visuais reais.

**Severidade original: ALTA.** ✅ provado *sem laço de eventos*, ❌ **derrubado**
com o laço rodando. O texto abaixo é o achado como foi escrito.

Ao contrário do Qt em C++, no PySide6 substituir o widget de uma célula **não
libera o antigo**, e `setRowCount(0)` também não:

```
setCellWidget 100x na MESMA célula:
  QLabels ainda filhos da tabela : 100
  weakrefs Python ainda vivos    : 100
setRowCount(0) 50 ciclos:
  QLabels ainda filhos da tabela : 50
  weakrefs Python ainda vivos    : 50
```

Atinge todas as telas com tabela: `comanda_view.py:443, 534, 571` (dispara a
cada `atualizar()`, linha 303), `cardapio_view.py:373-380, 623-629` (a cada CRUD
e a cada troca de categoria), `impressoras_view.py:289-308, 341-359`,
`funcionarios_view.py:255-269`, `historico_caixa_view.py:426`, `caixa_view.py:495`.

O cardápio acumula ⚠️ ~4 widgets de célula por produto e 1 por categoria **a
cada refresh**. Numa comanda com 20 itens reaberta 50 vezes num turno, são
milhares de widgets órfãos.

**Correção:** um helper de limpeza de tabela que destrói explicitamente os cell
widgets antes de repopular, e usá-lo em todas as views com tabela.

### 3.4 🟠 Modais vazados prendem entidades ORM da Session eterna

**Severidade: MÉDIA.** 🔍 verificado. `ui/widgets/busca_produto.py:69`

```python
self._produtos_ativos = produtos   # objetos ORM vivos, não DTOs
```

`comanda_view.py:810` passa o retorno de `listar_produtos_ativos()` direto, e
`busca_produto.py:159` navega `produto.categoria.nome`, materializando também as
`Categoria`. Como cada `BuscaProdutoWidget` vive dentro de um diálogo que nunca
morre (§3.2), cada abertura do "+ Item" deixa presa uma referência forte a N
`Produto` + suas `Categoria`.

**Correção de raiz é o §3.2.** Defesa em profundidade opcional: um
`@dataclass(frozen=True) ItemBusca` com os 5 campos que a UI realmente usa.

### 3.5 🔴 Zero índices contra as chaves estrangeiras

**Severidade: ALTA.** ✅ **provado.** É a causa raiz da degradação com o tempo
— o problema que o briefing chama de "operar semanas sem degradar".

```
index=True no domain/ ......... 0
Index() / __table_args__ ...... 0
create_index nas migrations ... 0
ForeignKey declaradas ......... 38
```

> #### ⚠️ Correção de contagem (Fase 2): são **20** FKs, não 38
> O número 38 veio de contar linhas de `grep -rn "ForeignKey" domain/`, que
> inclui os `import` e as declarações de `relationship`. A fonte de verdade é o
> schema: `PRAGMA foreign_key_list` em cada tabela do banco real soma **20**.
>
> ```
> caixas 2 · categorias 1 · comandas 5 · combo_itens 2 · itens_comanda 3
> movimentos_caixa 2 · pagamentos 2 · produtos 1 · quitacoes_consumo 2
> ```
>
> O achado continua inteiro — **zero índices** era o número que importava, e
> esse estava certo. Só a contagem de FKs foi corrigida, aqui e nos comentários
> do código que a repetiam.

O SQLite cria índice sozinho para PK e UNIQUE, **nunca para FK**. Então toda
consulta quente (`comanda.itens`, `listar_por_caixa`, `pagamento.comanda`,
`mesa.comandas`) é **varredura de tabela inteira**. Hoje, com o banco pequeno,
não dói. Depois de meses de operação, cada uma dessas varreduras cresce
linearmente — e elas rodam dentro de laços N+1 (§3.6).

> Nota: `TODO.md` afirma que `caixas.numero_sequencial_dia` é "indexado por
> `fechado_em`". **Não é** — não existe índice nenhum no projeto. Corrigir a doc.

> #### 🔴 Descoberto na Fase 2: a Fase 1 ativou uma FK que aponta para a tabela errada
> ✅ **provado.** `alembic check`, rodado para conferir se a migration de
> índices batia com o `domain/`, expôs outra coisa: no banco **migrado** —
> o do food truck — `quitacoes_consumo.autorizado_por_id` referencia
> `funcionarios`, enquanto o modelo declara `usuarios`. O service grava ali o
> `id` do **gerente logado**, que é um `Usuario`.
>
> A migration `d23a4f888a77` conhecia a anomalia e a documentou como aceitável,
> com uma justificativa explícita: *"o app nunca liga `PRAGMA foreign_keys` —
> não há enforcement para corrigir (...) só cosmética de metadado"*. **A Fase 1
> desta remasterização invalidou essa premissa** ao ligar o pragma. Virou
> defeito de produção, com duas caras, as duas reproduzidas num banco migrado:
>
> - **Quebra.** Gerente com `usuarios.id` maior que o maior `funcionarios.id`
>   (o caso comum — a loja tem mais logins de turno do que garçons): dar baixa
>   em consumo interno estoura `IntegrityError: FOREIGN KEY constraint failed`.
> - **Corrompe em silêncio.** Quando o id existe dos dois lados por
>   coincidência, grava apontando para o funcionário errado: o código quis
>   dizer o `Usuario` 2, o banco lê o `Funcionario` 2.
>
> E **nada disso aparecia na suíte**: os testes montam o schema com
> `Base.metadata.create_all`, que segue o `domain/` e já criava a FK certa. Só
> o banco vindo das migrations tinha a FK errada — exatamente o da máquina do
> food truck. É o pior tipo de defeito: verde em desenvolvimento, vermelho em
> produção.
>
> Corrigido na migration `c8e3f6a2b910`, que reconstrói a tabela com a FK certa
> e dá nome às duas (as anônimas do schema inicial eram o que impedia consertar
> sem reconstruir). Depois dela, `alembic check` fica limpo pela primeira vez no
> projeto: as 20 FKs do banco migrado e as do `domain/` batem uma a uma.

### 3.6 🟠 N+1 sistemático nos relatórios e na tela principal

**Severidade: ALTA.** 🔍 verificado (contagens específicas ⚠️ reportadas).

| Local | Problema |
|---|---|
| `mesas_view.py:371-374` | 🔍 `mesa.comandas` carrega **todo o histórico da mesa** para achar a única aberta — e roda para cada mesa ocupada, a cada refresh da **tela principal**. Custo cresce sem teto com as semanas |
| `caixa_service.py:716-744` | 🔍 `resumo_cancelamentos` faz 3 lazy loads por item cancelado (`item.produto`, `item.comanda`, `item.cancelado_por`) |
| `caixa_service.py` `ranking_por_atendente` | 🔍 `pagamento.comanda.atendente` — 1 query por pagamento do período |
| `caixa_service.py:784-810` | 🔍 `resumo_mensal` chama `listar_por_caixa` por turno dentro do laço. ⚠️ Auditoria reporta **3.092 queries / 716 ms** para abrir o Dashboard Mensal |
| `caixa_service.py:548-607` | ⚠️ `resumo` lê movimentos 2x e pagamentos em dinheiro 2x — 8 queries onde 4 bastam |
| `caixa_service.py:913-946` | ⚠️ `fechamento_da_gaveta_do_periodo` recalcula `resumo()` de turnos que a tela acabou de calcular |
| `historico_caixa_view.py:351` | ⚠️ ~6 SELECTs por fechamento a cada troca de mês ou clique em filtro |
| `caixa_view.py:420-434` | ⚠️ Carrega **todos** os fechamentos do banco para exibir 3 |

Cada uma dessas queries é hoje um **scan de tabela** (§3.5). As duas correções
se multiplicam: índices + eager loading (`selectinload`) resolvem juntas.

### 3.7 ✅ Quatro cópias do "limpar layout", com comportamentos divergentes — **RESOLVIDO (Fase 4)**

**Severidade: MÉDIA.** ✅ **provado.** Duplicação que já custou dois bugs visuais.

Duas cópias documentam o bug em detalhe e o corrigem
(`historico_caixa_view.py:556-571`, `dashboard_mensal_view.py:537-555`):

> "`takeAt` só tira o item do LAYOUT — o widget continua filho visível do
> container até o `deleteLater()` agendado rodar no próximo ciclo de eventos.
> (...) isso empilhava a linha antiga por baixo da nova na mesma posição,
> produzindo texto sobreposto/corrompido no repaint."

As outras (`caixa_view.py:735-740`, `mesas_view.py:421-427` e `477-488`) **não
receberam a correção**. Comparação direta das duas variantes, limpando e
repopulando no mesmo ciclo:

```
caixa_view (sem setParent): 5 widget(s) antigo(s) ainda filhos do container
corrigida  (com setParent): 0 widget(s) antigo(s) ainda filhos do container
```

`caixa_view.py` e `mesas_view.py` carregam hoje a versão latente de um bug **que
já foi diagnosticado e corrigido duas vezes** noutros arquivos.

**Correção (Fase 4): feita.** `ui/widgets/layout_utils.py` é a única cópia, e
os 6 sites importam dele. `grep -rn "takeAt" src/` só acha o utilitário e o
`FlowLayout`, que implementa a API de layout do Qt e não é cópia deste laço.
Dois testes novos exercitam `caixa_view` e `mesas_view` de verdade e falham se o
`setParent(None)` sair.
**Cuidado:** `mesas_view.py:421-424` usa `while layout.count() > 1` porque o
último item é um stretch fixo — o helper genérico precisa preservar isso.

### 3.8 ✅ Dez cópias de `_formatar_reais` — e uma delas diverge — **RESOLVIDO (Fase 3)**

**Severidade: MÉDIA (bug visível ao usuário).** ✅ **provado.**
**Resolvido em 2026-09-06:** `ui/formatacao.py`, formato `R$ 1.234,50` nas 10
telas. Ver a Fase 3 no §6 e as decisões no §8.

Nove cópias idênticas de `_formatar_reais(valor: Decimal) -> str`:
`caixa_view:743` · `cardapio_view:1316` · `comanda_view:952` ·
`dashboard_mensal_view:567` · `funcionarios_view:754` ·
`historico_caixa_view:616` · `pagamento_dialog:181` · `busca_produto:163` ·
`secao_cancelamentos:126`. Mais duas de `_formatar_reais_com_sinal`
(`dashboard_mensal_view:530`, `historico_caixa_view:620`).

E a décima, em `mesas_view.py:49`, **usa outra fórmula**:

```
9 telas (caixa, comanda, cardápio, ...): R$ 1234,50
tela de Mesas                          : R$ 1.234,50
DIVERGEM: True
```

A mesma quantia aparece com separador de milhar na tela de Mesas e sem
separador em todas as outras. Isso é visível para o usuário final.

> **Decisão pendente para o Vitor (§8):** ao centralizar, qual formato vence?
> Recomendo o de `mesas_view` (**R$ 1.234,50**, com separador de milhar — o
> correto em português), mas isso muda a aparência de 9 telas. É decisão sua,
> não minha.

### 3.9 ✅ PIN do gerente fica em texto claro na memória — **RESOLVIDO (Fase 4)**

> #### ⚠️ Correção (2026-09-06): o hook errado é real, o "para sempre" não
> Remedido pelo caminho real de `main_window._abrir_caixa`, com `app.exec()`
> rodando e um espião no `closeEvent`:
>
> ```
> Cancelar : PIN no campo logo após exec() = '1234' | closeEvent disparou? False
> Entrar   : PIN no campo logo após exec() = '1234' | closeEvent disparou? False
> após 20 aberturas: 0 diálogos vivos na janela | campos de PIN com texto: 0
> ```
>
> **Confirmado:** `closeEvent` nunca dispara em `accept()`/`reject()`, então
> aquele `_campo_pin.clear()` é código morto e o PIN continua no campo depois
> do `exec()`. A correção proposta (`done()`) está certa.
>
> **Derrubado:** o "para sempre" dependia do §3.2, que a Fase 3 rebaixou. Como o
> diálogo *é* destruído quando a referência sai de escopo, o PIN vive alguns
> milissegundos, não a sessão inteira. Severidade cai de ALTA para MÉDIA.
>
> **Ressalva honesta:** nem `clear()` nem a destruição **zeram** a memória — as
> duas só soltam a referência, e o `str` do PIN ainda passa por `_confirmar()` e
> por `validar_pin_gerente()` como objeto Python comum. O ganho é real e barato
> (3 linhas), mas é higiene, não blindagem criptográfica.

**Severidade original: ALTA.** 🔍 verificado. `ui/widgets/gerente_pin_dialog.py:72-76`

O código **já declara a intenção** de limpar o segredo:

```python
def closeEvent(self, event):
    # Limpa o PIN digitado da memória do widget antes de descartar o modal
    self._campo_pin.clear()
    super().closeEvent(event)
```

Mas `closeEvent` é o hook errado: `accept()` (botão Entrar), `reject()`
(Cancelar) e `Esc` passam por `QDialog::done()`, que faz `hide()`, **não**
`close()`. Só o X da janela dispara `closeEvent`. Somado ao §3.2 — o diálogo
nunca é destruído — **o PIN nunca é apagado**.

```python
def done(self, resultado: int) -> None:  # noqa: N802 - override Qt
    self._campo_pin.clear()
    super().done(resultado)
```

Aplicar idêntico em `loja_pin_dialog.py:74-78`. ~~Necessário **mas não
suficiente** — sem o §3.2 o widget continua vivo.~~ **Suficiente:** com o §3.2
rebaixado, o widget já morre sozinho; o que falta é só o hook certo.

### 3.10 ✅ Cache de miniaturas: teto OK, chave errada — **RESOLVIDO (Fase 5)**

**Severidade: MÉDIA (bug visível).** ✅ **provado.**

Boa notícia primeiro: `ui/widgets/thumbnail_cache.py` **já faz o que o briefing
pediu** — `OrderedDict` LRU com `LIMITE_ENTRADAS = 200`, documentado, com teto
rígido. Não precisa de `lru_cache` nem de mudança de política.

O problema é a chave: `chave = (imagem_path, tamanho)` **não inclui
`nome_produto`**, mas o placeholder é desenhado com a inicial do produto. Logo,
todo produto sem foto compartilha a mesma entrada:

```
chaves no cache: [(None, 64)]
Coca-Cola e Xis Salada devolvem o MESMO objeto? True
Coca-Cola e Batata   devolvem o MESMO objeto? True
```

**Todo produto sem foto exibe a inicial do primeiro produto desenhado.**
Correção de uma linha: incluir a inicial na chave.

⚠️ Reportado também: o cache lê o `ThemeController` mas nunca se inscreve nele —
placeholders ficam com as cores do tema antigo após alternar Claro/Escuro.

### 3.11 ✅ Tela fantasma: `EstoqueView` é inalcançável — **RESOLVIDO (Fase 5)**

**Severidade: MÉDIA.** ✅ **provado.**

`EstoqueView` é instanciada no boot (`main_window.py:150`), adicionada ao
`QStackedWidget` (`:175`) e registrada em `_destinos_nav` (`:217`). Mas a
Central de Loja renderiza apenas 5 cards (`loja_hub_view.py:18-26`):

```
_SECAO_CATALOGO = (Cardápio, Impressoras)
_SECAO_EQUIPE   = (Funcionários, Relatórios, Configurações)
```

**"Estoque" não está entre eles.** Não existe caminho de usuário até a tela. É
um placeholder de um módulo que está no backlog pós-V1 — legítimo como
intenção, mas hoje é peso morto carregado no boot e no `.exe`.

**Decisão do Vitor: remover.** Executado na Fase 5 — saiu de `main_window`
(instanciação, `QStackedWidget`, `_destinos_nav` e `_ROTULOS_LOJA`), o arquivo
foi deletado e a tela saiu da fixture `todas_as_telas`. O git guarda o código
para quando a fase de Estoque começar. `tests/ui/test_main_window.py` impede a
volta da tela fantasma: destino sem card na Central de Loja agora reprova.

### 3.12 ✅ Código morto, QSS órfão e documentação que mente — **RESOLVIDO (Fase 5)**

> #### ✅ Resolvido na Fase 5 (2026-09-06)
> Toda a tabela abaixo foi limpa. Dois pontos merecem registro:
>
> **O comentário de `auth_service` era o item perigoso, e o diagnóstico
> acertou.** Ele afirmava que `loja_config_service` não importa `auth_service`
> no nível de módulo. Importa — linha 29 de lá. Subir aquele import para o topo
> foi reproduzido antes de reescrever o comentário e derruba o boot com
> `ImportError: cannot import name 'AuthService' from partially initialized
> module`. Agora o convite virou `tests/unit/test_ciclo_de_imports.py`.
>
> **As "constantes planas" foram embora inteiras, não só as 15 mortas.** O
> último leitor das 7 restantes era `comprovante_dialog`, e ele foi para o QSS
> global junto com o §3.15 — que é exatamente o que o comentário do bloco
> mandava fazer ("ao tornar um widget reativo, prefira ler de
> `TEMA_ESCURO`/`TEMA_CLARO` via `ThemeController`").
>
> ⚠️ **Uma remoção com ressalva:** `PIN_MIN_DIGITOS = 4` era uma regra de
> negócio que nunca chegou a ser implementada — nenhum ponto do app valida o
> tamanho mínimo do PIN. Sair não muda comportamento, mas apaga a intenção. Se
> exigir 4 dígitos ainda for desejado, entra como validação de verdade (§8).

**Severidade: BAIXA a MÉDIA.** ⚠️ reportado, exceto onde marcado.

| Item | Local |
|---|---|
| 🔍 Pacote `config/` completamente vazio, sem importador — entra no wheel e no `.exe` | `src/gestor_comercial/config/__init__.py` |
| Bloco QSS de `variante="pilula-ciano"` morto: a segunda declaração do mesmo seletor sobrescreve a primeira | `qss_app.py:782-792` vs `1005-1015` |
| 15 das 22 "constantes planas" não são lidas por ninguém | `theme/tokens.py:302-327` |
| 6 seletores QSS órfãos — nenhum widget recebe esses `objectName`/`variante` | `qss_app.py:88, 402, 523, 622, 754, 755` |
| 3 métodos de repository nunca chamados | `base.py:52-55`, `mesa_repository.py:10-11`, `produto_repository.py:18-20` |
| 2 constantes de módulo públicas nunca lidas | `auth_service.py:37`, `imagem_service.py:26` |
| `_aplicar_variante` chamado 2x no mesmo botão, a 2ª contradizendo o comentário | `comanda_view.py:572` |
| **Comentário que afirma o OPOSTO do código**, convidando a uma "limpeza" que quebra o boot | `auth_service.py:50-52` |
| Comentário justifica import tardio com economia de PySide6 que não acontece (já carregado 60 linhas antes) | `main.py:79-81` |
| Comentário afirma motivo errado para guardar `QShortcut` em atributo | `comanda_view.py:217-222` |
| Changelog duplicado, a 2ª cópia corrompida | `docs/arquitetura.md:318, 320` |
| 🔍 **5 `.md` na raiz (~1.004 linhas) descrevem uma tela de login que não existe** — o numpad que eles dizem ter removido está lá, vivo | `COMPARACAO_LOGIN.md`, `GUIA_TECNICO_REFACTORING.md`, `README_REFACTORING.md`, `REFACTORING_LOGIN.md`, `TROUBLESHOOTING_E_MELHORIAS.md` |
| ✅ `scan_tmp.py` na raiz | **já removido nesta sessão** |

**Imports mortos: quase nada.** A varredura achou **um único** import morto real
em todo o projeto (`PIN_GERENTE` em `tests/unit/test_auth_service.py:15`), mais
um wildcard desnecessário em `tests/conftest.py:9` e dois imports-dentro-de-função
por preguiça em `comprovante_dialog.py:98, 126`. A higiene de imports do
projeto **já está boa**.

### 3.13 ✅ O que a auditoria olhou e achou correto

Registrado para não gastar tempo do time revisitando:

- **Separação de camadas está limpa.** `grep` por `uow.`/`session.`/`select(` em
  `ui/` → **0 ocorrências**. Nenhuma view fala com o banco; todas passam por
  services. A única importação de Qt fora de `ui/` é `services/imagem_service.py`
  usando `QImage` — **deliberada e documentada** ("sem Pillow como dependência
  nova"). Corrigir isso violaria a regra de zero dependência nova. **Manter.**
- **Não há QTimer, thread, polling ou refresh automático** em lugar nenhum. Não
  há timer órfão para cancelar. É a escolha certa para o Celeron — não
  introduzir polling.
- **`installEventFilter` não vaza:** em `cardapio_view.py:128-129` e
  `busca_produto.py:77` o filtro e os alvos morrem juntos. Não precisa de
  `removeEventFilter`.
- **`QShortcut` está correto** — parent definido, contexto `WindowShortcut`, e
  páginas fora da atual ficam `hidden`.
- **Lambdas em laços de reconstrução não vazam** — o emissor é o próprio widget
  efêmero e ele é destruído de verdade.
- **Nenhuma conexão de sinal duplicada:** todo `_montar_*`/`_criar_*` com
  `.connect()` é chamado exatamente uma vez.
- **`blockSignals` usado corretamente** ao repopular combos
  (`historico_caixa_view.py:274-284`, `dashboard_mensal_view.py:280-290`).
- **Identity map não cresce** (§2.4).
- **Cache de miniaturas já tem teto rígido** (§3.10).

### 3.14 ✅ Assinantes do tema por lambda sem receptor — **RESOLVIDO (Fase 5)**

**Severidade: MÉDIA (armadilha latente, não vazamento ativo).** 🔍 verificado.

`grep -rn "disconnect" src` → **zero**. Os dois assinantes de `ThemeController.mudou`
são lambdas sem objeto receptor (`login_view.py:313`, `configuracoes_view.py:130`).
Hoje **não cresce**, porque os receptores também vivem o processo inteiro. Vira
vazamento no instante em que alguém recriar uma dessas telas.

**Preservar:** a linha 130 forma realimentação (`mudou` → `setChecked` →
`toggled` → `alternar_para`) que **só não entra em laço infinito por causa da
guarda `if claro == self._claro: return`** (`controller.py:53-54`).

### 3.15 ✅ Cores de tema congeladas em `setStyleSheet` inline — **RESOLVIDO (Fase 5)**

**Severidade: MÉDIA (visual).** 🔍 verificado. `comanda_view.py:117-119` e ~11
cópias do mesmo stylesheet de erro. Resolvido uma vez na construção e nunca
recalculado; como `setStyleSheet` por widget tem precedência sobre o QSS global,
a cor do tema do boot vence para sempre.

**Correção:** levar a cor ao QSS global via `objectName`/propriedade — a troca de
tema passa a funcionar de graça e as 11 cópias somem.

---

## 4. Contrato de zero-regressão

O que **não pode mudar**. Confira item a item ao fim de cada fase.

### 4.1 Máquinas de estado (`domain/enums.py`) — congeladas

```
StatusComanda   : ABERTA · EM_CONFERENCIA · FECHADA · CANCELADA
StatusMesa      : LIVRE · OCUPADA
StatusCaixa     : ABERTO · FECHADO
FormaPagamento  : CREDITO · DEBITO · DINHEIRO · PIX · CONSUMO_INTERNO
TipoMovimento   : SANGRIA · REFORCO · DESPESA · CONSUMO_FUNCIONARIO
PerfilUsuario   : ADMIN · GERENTE · OPERADOR_CAIXA
CargoFuncionario: Gerente · Caixa · Garçom · Cozinha · Atendente
TipoConexao     : USB · SERIAL · REDE · WINDOWS · ARQUIVO
```

Nenhum valor entra, sai ou é renomeado. `CargoFuncionario` é gravado como texto
de propósito (evita migração de dado histórico) — não converter para Enum de banco.

### 4.2 Regras congeladas

- **Arredondamento monetário:** `services/dinheiro.py` — 2 casas, `ROUND_HALF_UP`,
  teto de `99999999.99`, `float` recusado por design. Não mexer.
- **Cascata de 3 níveis de PIN** (Login / Operacional / Master, commit `4c4d33a`,
  §3.13 da arquitetura): a validação é contra a **loja**, não contra o usuário.
- **Impressão ESC/POS:** bytes puros, roteamento por categoria + fallback para a
  padrão. **Nenhuma alteração na lógica de comandos.**
- **Layout split-screen do login, numpad 3x4 e alternância Claro/Escuro:** intactos.
- **Nenhuma dependência nova** no `pyproject.toml`.

### 4.3 A rede executável

Os **621 testes são o contrato executável** das regras de negócio:

| Arquivo | Linhas | Cobre |
|---|---|---|
| `test_impressao_service.py` | 1.282 | roteamento, fallback, cupons |
| `test_caixa_service.py` | 1.247 | abertura/fechamento, sangria, resumos |
| `test_cardapio_service.py` | 1.005 | CRUD, combos, impressoras |
| `test_comanda_service.py` | 771 | máquina de estados, itens |
| `test_pagamento_service.py` | 637 | parcial, troco, consumo interno |
| `test_impressora_escpos.py` | 412 | drivers de conexão |
| `test_auth_service.py` | 358 | cascata de PIN |
| + 8 outros | ~1.100 | formatador, entidades, resiliência |

**Regra:** ao fim de cada fase a suíte tem de estar verde, **sem teste apagado,
enfraquecido ou marcado `skip` para "passar"**. Se um teste precisa mudar, isso
é uma mudança de contrato e vai para o registro do §8.

---

## 5. Plano de saneamento — FASE 2

Ordem deliberada: **primeiro a rede de segurança, depois a integridade dos
dados, depois o núcleo, e a UI por último.** O briefing pedia dados → negócio →
UI; a base impõe dois ajustes: refatorar 8.000 linhas de UI sem um único teste
de UI é apostar, e o bug de rollback (§3.1) é grave demais para esperar.

| # | Fase | Por quê nesta posição | Rede |
|---|---|---|---|
| 0 | Rede de segurança + limpeza de raiz | Sem teste de UI, nada de tocar em view | — |
| 1 | **Integridade de dados** (§3.1, §3.5) | É o único achado que corrompe dado | 621 testes |
| 2 | Núcleo de dados e performance (§3.6) | Índices + N+1 andam juntos | 621 testes |
| 3 | Utilitários compartilhados (§3.7, §3.8) | Precisam existir antes de a UI consumir | testes novos |
| 4 | Ciclo de vida da UI (§3.2, §3.3, §3.9) | Onde mora o ganho de RAM | testes de vazamento da Fase 0 |
| 5 | Higiene da UI (§3.10 a §3.15) | Mecânico, baixo risco | smoke tests |
| 6 | Arquitetura da UI | Maior risco; só onde compensa | smoke tests |
| 7 | Validação final | Fecha a remasterização | tudo |

**Regra de ouro do processo:** cada fase é **um commit próprio**, com a suíte
verde antes de a próxima começar.

---

## 6. Execução — FASE 3

### Fase 0 — Rede de segurança e limpeza de raiz ✅ CONCLUÍDA (2026-09-06)

- [x] Corrigir `test_resumo_mensal_sem_nenhum_fechamento_no_mes` (§2.2) — o teste
      agora afirma o contrato real: as 5 formas presentes, todas zeradas
- [x] `tests/ui/conftest.py` com `QApplication` offscreen — **zero dependência nova**
- [x] `tests/ui/test_smoke_telas.py` — as **13** telas montam e sobrevivem a um
      `atualizar()`, com banco vazio e com dado real
- [x] `tests/ui/test_vazamento_modais.py` — 4 testes `xfail(strict=True)` + 1 que
      trava o vazamento de hoje
- [x] `tests/ui/test_vazamento_tabelas.py` — 3 testes `xfail(strict=True)` + 1 que
      documenta a armadilha do PySide6
- [x] 5 `.md` de refatoração movidos para `docs/historico/` com README de aviso (§3.12)
- [x] Remover `scan_tmp.py`

**Resultado:** `626 passed, 7 xfailed` — de `620 passed, 1 failed`.

> #### A mecânica do `xfail(strict=True)` — leia antes da Fase 4
> Os 7 testes de vazamento descrevem o comportamento que a **Fase 4** vai
> entregar. Foram escritos **antes** da correção de propósito: teste de
> vazamento que já nasce verde não prova nada.
>
> Hoje eles falham, e o `xfail` mantém a suíte verde sem varrer o problema para
> baixo do tapete. O `strict=True` é o catraca: quando a Fase 4 corrigir o ciclo
> de vida, esses testes vão passar — e "passou inesperadamente" com `strict`
> **é falha**. A suíte avisa na hora de remover o marcador. Não existe caminho
> em que a correção entre e o teste continue mentindo.
>
> Cada arquivo tem também 1 teste que passa **hoje** e trava o "antes"
> (`test_o_vazamento_de_hoje_esta_documentado`,
> `test_o_comportamento_do_qt_esta_documentado`). Esses saem junto com os
> marcadores, na Fase 4.

> #### Armadilha encontrada ao escrever os testes
> `test_cardapio_nao_cresce_a_cada_atualizar` passou a primeira revisão como
> "xfail" — mas por **motivo errado**: faltava usuário logado, e o que estourava
> era `NaoAutorizadoError`, não o vazamento. Um xfail falso é pior que nenhum
> teste, porque parece cobertura. **Sempre rodar `pytest --runxfail` e conferir
> que a falha é a asserção esperada**, não uma exceção qualquer.

### Fase 1 — Integridade de dados ✅ CONCLUÍDA (2026-09-06)

- [x] **`main.py` usa `with UnitOfWork() as uow:`** — o `__exit__` era código
      morto; agora é o que garante que o app não encerre com escrita pendente
- [x] **Rollback em todo caminho de erro dos services** — via
      `services/transacao.py` + `@transacional` nas 8 classes de service
- [x] `tests/unit/test_integridade_transacional.py` — 7 testes
- [x] `PRAGMA foreign_keys = ON` via listener em `repository/base.py` (§3.5)
- [x] `journal_mode = WAL` avaliado e **adiado para a Fase 2** — ver decisão abaixo

**Resultado:** `633 passed, 7 xfailed` — as 621 provas antigas seguem verdes,
zero regressão. `main()` validado ponta a ponta headless: migrations, seed de
60 mesas, 10 telas montadas, FK ativa.

> #### A regra do rollback: "só se houver pendência", e por quê
> A correção óbvia — desfazer em **qualquer** exceção — quebraria o app, porque
> este projeto usa exceção como **fluxo normal** em dois lugares:
>
> 1. **A cascata de 3 níveis de PIN** (§3.13 da arquitetura):
>    `senha_master_confere` chama `validar_senha_master` e captura
>    `AcessoNegadoError` para devolver `False`. Digitar a senha errada é evento
>    rotineiro do balcão — com rollback genérico, toda tentativa errada
>    passaria a descartar trabalho pendente.
> 2. **A blindagem da impressão**: `impressao_service.py:364` captura
>    `Exception` de propósito, para a impressora com defeito nunca derrubar a
>    venda junto. Rollback ali faria exatamente o que o RNF proíbe.
>
> Por isso a regra implementada é mais estreita: **desfaz apenas se a operação
> estiver saindo com alterações não gravadas** (`session.new/dirty/deleted`).
> Senha errada sai com a Session limpa e não dispara nada. Edição rejeitada no
> meio sai suja — e é essa que precisa ser descartada. Dois testes travam esse
> equilíbrio (`test_cascata_de_pin_continua_funcionando` e
> `test_erro_de_regra_nao_descarta_o_que_ja_foi_comitado`).

> #### Por que um decorator de classe, e não 123 edições
> Os 8 services somam **123 métodos públicos e 45 pontos de commit**. Decorar à
> mão seria um diff enorme e fácil de errar por omissão — e a omissão seria
> justamente onde o bug voltaria.
>
> A alternativa considerada e **descartada** foi inspecionar o código-fonte de
> cada método (`inspect.getsource`) para decorar só quem comita: o PyInstaller
> empacota `.pyc` sem o `.py`, então isso funcionaria em desenvolvimento e
> falharia no `.exe` do food truck — o pior tipo de defeito.
>
> O que ficou: `@transacional` em 8 linhas, uma por classe. O diff em `src/` da
> fase inteira é de **16 linhas de service + 1 módulo novo + 2 blocos**.

### Fase 2 — Núcleo de dados e performance ✅ CONCLUÍDA (2026-09-06)

- [x] **Índices nas 20 FKs** (não 38 — ver correção no §3.5), via `index=True`
      no `domain/` **e** migration `b4d7e2c91a08`: banco novo (`create_all`, os
      testes) e banco antigo (migrations, o food truck) convergem para o mesmo
      schema
- [x] **`quitacoes_consumo.autorizado_por_id` corrigida** (migration
      `c8e3f6a2b910`) — a FK que a Fase 1 ativou apontando para a tabela errada,
      achada por `alembic check`. Ver o quadro no §3.5
- [x] **`journal_mode = WAL` adotado** — decisão do Vitor, 2026-09-06, ver §8
- [x] **Rotina de backup** (`repository/backup.py`): `VACUUM INTO` no fechamento
      de caixa e sob demanda na tela de Configurações, `wal_checkpoint(TRUNCATE)`
      ao fechar o caixa e ao encerrar o app
- [x] Corrigir `TODO.md`, que afirmava um índice que não existe
- [x] `selectinload` + consultas agregadas nos N+1 do §3.6 — grade de mesas,
      `resumo`, `totais_por_forma`, `resumo_cancelamentos`,
      `ranking_por_atendente`, `resumo_mensal`, `fechamento_da_gaveta_do_periodo`
- [x] Medido antes/depois num banco de **3 meses de operação** (3.522 comandas,
      14.039 itens, 3.510 pagamentos) — números no §7
- [x] `tests/unit/test_custo_das_consultas.py` (10 testes) +
      `tests/integration/test_backup.py` (12) + `tests/ui/test_backup_na_tela.py` (3)
- [x] Suíte verde, **contrato do §4 conferido** — `enums.py`, `dinheiro.py`,
      `auth_service.py`, `impressao_service.py`, `hardware/` e `pyproject.toml`
      não têm uma linha alterada

**Resultado:** `658 passed, 7 xfailed` — de `633 passed, 7 xfailed`.
Dashboard Mensal: **2.502 → 217 consultas** e **960 → 108 ms**.

> #### A prova de que nenhum número mudou
> Otimização de relatório financeiro que altera um centavo é pior que
> lentidão. Antes de fechar a fase, cada valor foi recalculado por um caminho
> **independente** — o jeito antigo, uma consulta por forma de pagamento, item
> a item — sobre os 3 meses do banco de medição, e comparado com o que os
> métodos novos devolvem: saldo esperado, totais por forma, contagem de
> comandas, cancelamentos e ranking por atendente de cada um dos 26 turnos.
> **Todos idênticos.** O `dinheiro()` permite isso porque somar parcelas já
> arredondadas a 2 casas não introduz arredondamento novo — foi o que deixou
> `totais_de_cancelamento` somar o mês inteiro de uma vez sem divergir da
> auditoria turno a turno.

> #### Testes de custo: por que medem o dobro do volume, e não um número fixo
> N+1 é um defeito que **volta sozinho**. Basta alguém, meses adiante, ler
> `pagamento.comanda` dentro de um laço: nada quebra, nenhum teste fica
> vermelho, o número sobe de novo e só aparece como "o sistema ficou lento"
> depois de meses de vendas acumuladas.
>
> Por isso nenhum dos testes de `test_custo_das_consultas.py` afirma um número
> mágico de consultas — cada um roda a **mesma operação com o dobro (ou 10x) do
> volume** e exige que a conta não mude. É a propriedade que interessa: o custo
> da tela é função do que ela mostra, não de quanto o food truck já vendeu. Um
> teto fixo envelheceria mal e ninguém saberia se ainda faz sentido.
>
> Conferidos contra o código antigo, como manda a lição da Fase 0: **8 dos 10
> ficam vermelhos** sem as correções desta fase. Os 2 que passam nos dois lados
> são de conteúdo — travam o que a otimização não podia mudar.

### Fase 3 — Utilitários compartilhados ✅ CONCLUÍDA (2026-09-06)

- [x] **`ui/formatacao.py`** — as 10 cópias de `_formatar_reais` e as 2 com sinal
      viraram uma (§3.8). Formato adotado: **`R$ 1.234,50`**, com separador de
      milhar — decisão do Vitor. A aplicação nas 10 telas entrou nesta mesma
      fase, a pedido dele, em vez de esperar a Fase 5
- [x] **`ui/widgets/layout_utils.py`** — `limpar_layout()` na versão corrigida
      (`setParent(None)` + `deleteLater()` + sub-layouts recursivos), com
      `manter_ao_final=` para o stretch fixo de `mesas_view` (§3.7)
- [x] **`ui/widgets/modais.py`** — `executar_modal()` e `descartar_modal()` (§3.2)
- [x] **`ui/widgets/tabelas.py`** — `limpar_tabela()` e `definir_celula()` (§3.3)
- [x] **48 testes** dos quatro: `test_formatacao.py` (26), `test_tabelas.py` (7),
      `test_layout_utils.py` (8), `test_modais.py` (7)
- [x] Fixture `assentar` em `tests/ui/conftest.py` — o helper que os dois
      arquivos de vazamento copiavam, agora num lugar só **e com o
      `sendPostedEvents(DeferredDelete)` que faltava nas duas cópias**

**Resultado:** `706 passed, 7 xfailed` — de `658 passed, 7 xfailed`.
Nenhuma linha de `services/`, `repository/`, `domain/` ou `hardware/` alterada.

> #### 🔴 O que esta fase descobriu: §3.2 e §3.3 não sobrevivem ao laço de eventos
> Escrever o teste de premissa das tabelas derrubou o §3.3 e obrigou a remedir o
> §3.2. As duas medições originais rodaram **sem laço de eventos**, e é isso que
> muda tudo: sem laço, `deleteLater()` nunca sai do papel, e um objeto
> legitimamente agendado para destruição é indistinguível de um vazado.
>
> | Cenário, com `app.exec()` rodando | Vivos | Se vazasse |
> |---|---|---|
> | `setCellWidget` 50x na mesma célula | **1** | 50 |
> | `setRowCount(0)` por 20 ciclos | **0** | 20 |
> | `CardapioView.atualizar()` 21 vezes | **78 → 78** | 78 → 1.638 |
> | 30 diálogos com `reject()` **sem `exec()`** | **30** | 30 |
> | 30 diálogos com `exec()` — **o caminho do app** | **0** | 30 |
>
> Conferido em `offscreen` e em `windows`, PySide6 6.11.2. O único cenário que
> ainda vaza é o que **nenhum dos 31 sites do app percorre**.
>
> Isso rebaixa a Fase 4 de 🔴 para 🟡 e muda o critério de pronto dela — os 7
> `xfail(strict=True)` da Fase 0 **não podem ficar verdes como estão escritos**,
> porque medem a API crua do Qt (`tabela.setCellWidget(...)`,
> `CancelamentoDialog(...)` + `reject()`) sem passar por utilitário nenhum.
> Nenhuma correção feita nas *views* muda o que eles medem. Ver a Fase 4.

> #### A lição, para a próxima medição de memória
> `QApplication.processEvents()` **não** despacha `DeferredDelete`. O Qt segura
> esses eventos até o laço em que foram agendados terminar — e num teste não
> existe laço nenhum. Toda medição de vazamento em Qt precisa de
> `sendPostedEvents(None, QEvent.Type.DeferredDelete)` (é o que a fixture
> `assentar` faz agora) ou de um `app.exec()` de verdade. Sem isso a medição
> acusa vazamento onde só há destruição adiada.

> #### Decisões tomadas dentro da fase
> **Sinal do negativo unificado.** `formatar_reais(-12)` agora devolve
> `-R$ 12,00`, não `R$ -12,00`. A tela do Caixa mostrava as duas formas ao mesmo
> tempo: `-R$ 12,00` na linha de sangria (sinal montado à mão) e `R$ -12,00` na
> diferença de fechamento. Ganhou a que já era maioria.
>
> **Arredondamento passa por `dinheiro()`.** `f"{valor:.2f}"` usa o padrão do
> Python (meio para o par) e arredondaria `R$ 0,005` para `R$ 0,00`, enquanto o
> cupom impresso — que já chamava `dinheiro()` — imprimiria `0,01`. Um centavo
> de divergência entre a tela e o papel na mão do cliente. Agora os dois usam a
> mesma política, e `test_a_tela_e_o_cupom_mostram_o_mesmo_numero` tranca isso.
>
> **`descartar_modal()` checa `isValid()` antes do `deleteLater()`.** A chamada
> mora num `finally`; num objeto já destruído ela levanta `RuntimeError` e
> substituiria a exceção original — o operador veria um estouro de shiboken no
> lugar da mensagem de verdade, ou o app cairia no balcão por causa da
> *limpeza*. Cai direto no RNF "zero travamentos".

### Fase 4 — Ciclo de vida da UI ✅ CONCLUÍDA (2026-09-06)

> Rebaixada de 🔴 para 🟡 pela Fase 3 e executada no **escopo enxuto** decidido
> pelo Vitor (§8): os dois defeitos reais, os 7 `xfail` e a medição. Os 31 + 6
> sites de padronização foram para a Fase 5.

- [x] **Os 7 `xfail(strict=True)` reescritos** — era o bloqueador: como estavam,
      exercitavam a API crua do Qt (`tabela.setCellWidget(...)`,
      `CancelamentoDialog(...)` + `reject()`) e **nenhuma correção feita nas
      views poderia deixá-los verdes**. Passaram a medir o app: os diálogos
      reais abertos com `exec()`, e as telas reais recarregadas 20 vezes
- [x] **`ui/widgets/layout_utils.py` é a única cópia** (§3.7) — `caixa_view` e
      `mesas_view` (3 sites) saíram da versão **sem** `setParent(None)`;
      `dashboard_mensal_view` e `historico_caixa_view` (3 sites) largaram as
      cópias corretas que mantinham. `grep -rn "takeAt" src/` só acha o
      utilitário e o `FlowLayout` (que implementa a API do Qt, não é cópia)
- [x] **`closeEvent` → `done()` nos 2 diálogos de PIN** (§3.9) — `accept()`,
      `reject()` e Esc passam por `done()`; o `clear()` pendurado no
      `closeEvent` era código morto nos três caminhos
- [x] **`tools/medir_memoria.py`** — a bancada do §2.3 virou script versionado,
      com `--roteiro-antigo` para reproduzir a medição original. Sem dependência
      nova: `GetProcessMemoryInfo` via `ctypes`
- [x] **21 testes novos** — `test_pin_dialogs.py` (10), 3 em `test_layout_utils.py`,
      e os arquivos de vazamento reescritos (`test_vazamento_modais.py` 8,
      `test_vazamento_telas.py` 2, ex-`test_vazamento_tabelas.py`)
- [x] Fixture `todas_as_telas` movida para `tests/ui/conftest.py` — o smoke e o
      teste de vazamento varrem a **mesma** lista, então tela nova entra nas
      duas redes de uma vez
- [x] `tests/ui/test_vazamento_*.py` verdes ← critério de pronto, agora
      alcançável porque medem o app e não o Qt
- [→] `executar_modal()` nos 31 sites (§3.2) e limpeza de tabela nas 6 views
      (§3.3) — **movidos para a Fase 5**: viraram padronização quando os
      achados caíram
- [→] Lambdas do tema (§3.14) — **movido para a Fase 5**, mesma razão

**Resultado:** `727 passed` — de `706 passed, 7 xfailed`. Zero `xfail` restantes.
Nenhuma linha de `services/`, `repository/`, `domain/` ou `hardware/` alterada.

> #### 🔴 O que esta fase descobriu: o §2.3 era artefato de medição
> A linha de base do documento inteiro dizia que 300 modais custavam **+40,8 MB**
> e que **300 de 300** continuavam vivos. Rodando os dois roteiros na mesma
> bancada, no código de hoje:
>
> | Roteiro | 300 modais custam | Modais vivos |
> |---|---|---|
> | Caminho real do app (`exec()` + `assentar`) | **+0,5 MB** | **0 de 300** |
> | Roteiro do §2.3 (sem `exec()`, só `processEvents`) | **+41,7 MB** | **300 de 300** |
>
> **Nenhuma linha de produção separa as duas colunas.** O +40 MB é reproduzível
> hoje, com a Fase 4 pronta, e some quando se mede pelo caminho que o app usa.
> Somado ao §3.2 e ao §3.3, são **três achados de memória** que vieram do mesmo
> erro de bancada. É por isso que a bancada agora é um arquivo no repositório.

> #### Sobre "provar" correção
> Cada correção desta fase foi conferida **desfazendo-a** e vendo a suíte ficar
> vermelha, não só vendo-a verde depois. Sem o `setParent(None)`, 6 testes de
> `test_layout_utils.py` falham; com o `closeEvent` de volta, 6 dos 10 de
> `test_pin_dialogs.py` falham; e a rede larga de telas pega um vazamento
> injetado numa tela real (Cardápio: 80 → 100 widgets). Um teste que passa dos
> dois jeitos é exatamente o que produziu os `xfail` que esta fase jogou fora.

> #### Decisões tomadas dentro da fase
> **Os arquivos de vazamento foram reescritos, não "consertados".**
> `test_vazamento_tabelas.py` virou `test_vazamento_telas.py`: dois dos três
> `xfail` mediam `QTableWidget` cru, sem passar por view nenhuma. O nome antigo
> prometia cobrir tabelas e cobria a API do Qt.
>
> **O contrato do utilitário e o comportamento do app ficam em arquivos
> separados.** `test_modais.py`/`test_tabelas.py` testam `modais.py`/`tabelas.py`;
> `test_vazamento_*.py` testam os diálogos e as telas reais. Misturar os dois foi
> o que deixou os `xfail` medirem a coisa errada sem ninguém notar.
>
> **A rede larga de telas é sobre crescimento, nunca sobre número absoluto.**
> Quantos widgets uma linha usa é detalhe de layout que muda sem ser bug; o que
> nunca pode acontecer é o total subir a cada `atualizar()`.

### Fase 5 — Higiene da UI ✅ CONCLUÍDA (2026-09-06)

> Herdou da Fase 4 os itens que deixaram de ser correção de vazamento e viraram
> padronização. Fechou os 9, cada um com o teste que o reprova quando desfeito.

- [x] 🟢 **Remover a `EstoqueView`** (§3.11) — saiu de `main_window`
      (instanciação, `QStackedWidget`, `_destinos_nav` e `_ROTULOS_LOJA`), o
      arquivo foi deletado e a tela saiu da fixture `todas_as_telas`. O git
      guarda o código para quando a fase de Estoque começar.
      **Achado no caminho:** a `MainWindow` não era montada por **nenhum**
      teste — a peça que compõe todas as outras, e um erro nela só apareceria
      no boot. `tests/ui/test_main_window.py` fechou a lacuna, e é ele que
      transforma o §3.11 em invariante: destino sem card na Central de Loja
      (a tela fantasma) e card sem destino agora reprovam
- [x] 🟡 `executar_modal()` nos 31 sites (§3.2) — 29 diretos; os 2 laços
      `while` do cardápio reaproveitam a mesma instância e usam
      `descartar_modal` num `finally` **fora** do laço, porque o caminho de
      sucesso sai por `return` de dentro dele
- [x] 🟡 `limpar_tabela()`/`definir_celula()` nas views com tabela (§3.3) —
      6 views + `secao_cancelamentos`. **Não era mecânico:** ver o achado da
      seleção logo abaixo. `limpar_tabela` ganhou `preservar_selecao`
- [x] 🟡 Lambdas do tema → métodos ligados (§3.14), **com a guarda anti-laço
      preservada** e testada: se a guarda de `alternar_para` sumir, o teste da
      pílula não falha por asserção — estoura por recursão
- [x] Chave do cache de miniaturas (§3.10) — a inicial entrou na chave, e a
      mesma função `_inicial()` alimenta a chave e o desenho, que é o que
      amarra as duas pontas. Junto, o cache passou a descartar os placeholders
      quando o tema vira — sem assinar o `ThemeController` (seria uma conexão
      permanente a um singleton, o próprio §3.14), só comparando a paleta por
      identidade a cada miniatura pedida
- [x] Código morto, QSS órfão, constantes não lidas (§3.12) — pacote `config/`
      vazio, o bloco QSS `pilula-ciano` que era sobrescrito 220 linhas abaixo,
      6 seletores sem widget, **as 22 "constantes planas" inteiras** (o último
      leitor, `comprovante_dialog`, foi para o QSS global no §3.15), 3 métodos
      de repository, 2 constantes de módulo, a 2ª cópia corrompida do changelog
      e 4 imports
- [x] **Corrigir os comentários que mentem** (§3.12) — `auth_service.py`
      afirmava que `loja_config_service` **não** importa `auth_service` no
      nível de módulo. Importa, na linha 29 de lá: subir aquele import fecha o
      ciclo e o app não abre. Reproduzido antes de reescrever o comentário, e
      agora é `tests/unit/test_ciclo_de_imports.py`. Mais 2: o de `main.py`
      creditava uma economia de PySide6 que não acontece (o Qt entra 60 linhas
      antes) e o de `comanda_view` dava o motivo errado para o `QShortcut` em
      atributo (quem o mantém vivo é o parent, não o atributo)
- [x] Cores inline → QSS global (§3.15) — 20 `setStyleSheet` que resolviam a
      cor **na construção**. Como stylesheet por widget vence o QSS global, a
      paleta do boot ficava congelada ali e a troca de tema não alcançava
      aquelas linhas. Junto vieram os 10 pares `unpolish`/`polish` copiados
      pela UI, agora um só em `ui/widgets/estilo.py`
- [x] Tipagem `typing` nas funções públicas — o projeto já estava em **380 de
      403**; as 23 que faltavam eram as sobrecargas de evento do Qt, os
      `session` do seed e 3 callbacks. Agora é invariante, não estado do dia

> #### 🔴 O que a Fase 5 quase quebrou: a seleção do usuário
> Trocar `setRowCount(len(dados))` por uma limpeza de verdade parecia mecânico.
> Não era. As views nunca zeravam a tabela antes de repopular, e **nesse
> caminho o Qt mantém a linha corrente** enquanto a contagem não encolhe —
> `cardapio_view` e `impressoras_view` leem `currentRow()` logo depois de
> repopular.
>
> Medido antes de trocar:
>
> | Roteiro, linha 1 selecionada de 3 | `currentRow()` depois |
> |---|---|
> | `setRowCount(3)` — o que as views faziam | **1** |
> | `setRowCount(0)` + `setRowCount(3)` — a limpeza | **-1** |
>
> No balcão: o pai do Vitor seleciona um produto, clica em Editar, salva — e o
> produto sai selecionado sozinho, com Editar/Excluir/Combo apagando na cara
> dele. A troca cega ainda fazia a tela emitir `produto_selecionado(None)` no
> meio do próprio refresh.
>
> Por isso `limpar_tabela` ganhou `preservar_selecao`, que devolve a linha
> corrente **com os sinais bloqueados** — do lado de fora, indistinguível do
> `setRowCount` de antes. Os 4 testes de `test_selecao_sobrevive_ao_refresh.py`
> ficam vermelhos se alguém tirar o parâmetro.

> **`gc.collect()` na destruição de telas pesadas: item removido.** Estava aqui
> como "se a medição mostrar ganho". A medição existe agora
> (`tools/medir_memoria.py`) e mostra o contrário: 300 modais custam +0,5 MB
> pelo caminho real. Não há o que o `gc.collect()` recolha, e ele custa uma
> pausa numa máquina fraca. Fica fora até alguma medição pedir.

### Fase 6 — Arquitetura da UI ✅ CONCLUÍDA (2026-09-06)

> Escopo decidido pelo Vitor (§8): **só a duplicação real**. O critério de
> "compensar" deixou de ser tamanho de arquivo e passou a ser duplicação
> medida — e a medição mudou o alvo da fase.

- [x] **Varredura de corpos de função em toda a camada de UI** — comparando o
      `ast.dump` do corpo, então o nome não conta. Acusou **8 cópias**, todas
      entre `dashboard_mensal_view` e `historico_caixa_view`, e **nenhuma** nas
      cinco views gigantes que a fase ia quebrar
- [x] **`ui/widgets/paineis_relatorio.py`** — `PainelGaveta`,
      `PainelAtendentes` e `linha_barra_proporcao` (a função que existia duas
      vezes com dois nomes: `_criar_linha_forma` e `_criar_linha_atendente`).
      O `_linha_rotulo_valor` que gravava `QLabel` no dono via `setattr` sumiu:
      virou detalhe interno do painel
- [x] **`ui/widgets/filtro_periodo_operador.py`** — a barra de filtro passa a
      ser dona do estado que as duas telas duplicavam em três atributos cada
      (`_operador_selecionado`, `_algum_operador_clicado`,
      `_nome_operador_selecionado`) e avisa por dois sinais separados
      (`periodo_mudou`, `operador_mudou`)
- [x] **`formatar_para_campo()` em `ui/formatacao.py`** — as 2 cópias de
      `_formatar_campo` (cardápio e funcionários), agora passando por
      `dinheiro()` como o resto do módulo
- [x] **`ResumoCaixa.diferenca_total`** — as **três** regras divergentes da
      mesma conta viraram uma. Ver o achado abaixo
- [x] **`tools/comparar_telas.py`** — bancada de paridade visual: renderiza as
      telas offscreen em PNG (escuro, claro e com operador filtrado) e compara
      com outro commit. Sem dependência nova, fora de `src/`
- [x] **24 testes novos** — `tests/ui/test_paineis_de_relatorio.py` (21) e
      3 em `test_caixa_service.py`
- [→] Quebrar as 5 views gigantes por tamanho — **não executado, de propósito**:
      a varredura mostrou que elas não duplicam nada entre si. Ver §8
- [x] Camadas: **nada a fazer** — já estava limpo (§3.13)

**Resultado:** `799 passed` — de `775 passed`. Zero corpo de função duplicado
na camada de UI. As duas views somadas caíram de **1.126 para 755 linhas**, com
317 linhas de componente compartilhado no lugar.

> #### A prova que a suíte não dava: as telas continuam idênticas
> Refatoração de UI passa nos testes e ainda assim muda a tela — nenhum teste
> compara pixel. As duas telas foram renderizadas offscreen com o código de
> **antes** (worktree em `018588e`) e o de depois, em 6 combinações (as 2 telas
> × tema escuro, tema claro e com operador filtrado):
>
> ```
> dashboard-claro.png     idêntico    historico-claro.png     idêntico
> dashboard-escuro.png    idêntico    historico-escuro.png    idêntico
> dashboard-operador.png  idêntico    historico-operador.png  idêntico
> ```
>
> **Byte a byte**, não "parecido". A bancada ficou versionada em
> `tools/comparar_telas.py` — é ela que a Fase 7 usa para a paridade tela a
> tela.

> #### 🔴 O que esta fase descobriu: três regras para a mesma conta
> "Diferença total do turno" (quebra + sobra) existia em **três** lugares, com
> **três critérios diferentes** para quando falta uma das duas contagens:
>
> | Onde | Se só uma contagem existe |
> |---|---|
> | `caixa_service.fechamento_da_gaveta` (a gaveta impressa) | devolve `None` |
> | `caixa_view` (a tela do Caixa) | trata a que falta como zero |
> | `historico_caixa_view` (o Histórico Diário) | soma `Decimal + None` → **estoura** |
>
> As três davam o mesmo resultado na prática, porque as duas contagens sempre
> viajam juntas: `fechar` recebe e grava as duas, e a migration `b7c9e2f14a03`
> deixou as antigas com as duas nulas. **Conferido**: pôr a regra do Histórico
> de volta deixa a suíte inteira verde — o defeito é inalcançável hoje.
>
> Por isso a correção não é um teste que pega o estouro (não há como), é
> `ResumoCaixa.diferenca_total`: uma regra só, no lugar onde o dado mora, com
> o critério mais conservador (sem as duas contagens, não há diferença a
> afirmar). E `test_as_duas_contagens_do_fechamento_sempre_viajam_juntas`
> **trava a premissa**: no dia em que o fechamento parcial existir, esse teste
> cai e avisa que agora virou decisão de produto.

> #### Por que as views gigantes ficaram como estão
> A fase existia para "quebrar views gigantes só onde compensar". A varredura
> respondeu onde: **em lugar nenhum delas**. `cardapio_view` (1.342),
> `comanda_view` (949), `funcionarios_view` (754), `impressoras_view` (742) e
> `caixa_view` (735) são grandes porque cada uma carrega a própria tela, os
> próprios painéis e os próprios diálogos — nenhuma linha repetida entre elas.
> Partir esses arquivos seria mover código sem nenhum teste capaz de dizer se
> ficou melhor, no exato ponto do documento em que o risco é maior e o retorno,
> estético. Fica registrado como decisão, não como pendência.

### Fase 7 — Validação final ✅ CONCLUÍDA (2026-09-06)

> A pergunta da fase não é "a suíte está verde?" — ela está verde desde a Fase
> 0. É **"o pai do Vitor vê e imprime a mesma coisa que via antes da faxina?"**.
> Quem responde isso não é teste de widget: é comparar as telas e os cupons com
> o código de **antes de tudo** (`b22da75`, o commit anterior à Fase 0).

- [x] **Suíte inteira verde** — `800 passed`, 0 `xfail`, 0 falhas. Nenhum teste
      apagado, enfraquecido ou marcado `skip` (§4.3)
- [x] **Paridade tela a tela** — as 10 telas do checklist mais a Central de
      Loja, em tema escuro e claro, mais o estado "operador filtrado" das duas
      telas de Relatórios: **24 renderizações**, comparadas pixel a pixel com
      `b22da75`. Resultado e leitura de cada diferença logo abaixo
- [x] **Impressão ESC/POS idêntica** — os 6 documentos (comanda de produção, 2ª
      via, pré-conta, recibo, fechamento da gaveta e teste de impressora),
      impressos de verdade pelo driver de verdade em conexão ARQUIVO:
      `balcao.txt` (130 linhas) e `cozinha.txt` (49 linhas), **idênticos**
- [x] **Métricas do §7 preenchidas**
- [x] **`docs/arquitetura.md`, `TODO.md` e `CONTEXT.md` atualizados**
- [x] **Regressão encontrada e corrigida** — a tela de Configurações espremida
      (achado abaixo), com teste próprio

**Resultado:** `800 passed` — de `799`. O teste novo é
`tests/ui/test_telas_cabem_na_tela.py`.

#### O que mudou nas bancadas

A bancada da Fase 6 renderizava **duas** views soltas, num banco vazio e com o
banco de fontes do Qt vazio (na plataforma `offscreen` ele sobe assim, e todo
texto vira quadradinho — a comparação enxergava layout, não conteúdo). Para
responder pelas 10 telas ela mudou em três pontos:

| Antes (Fase 6) | Agora (Fase 7) |
|---|---|
| 2 views instanciadas soltas | a **`MainWindow` de verdade**, então sidebar, barra de usuário e barra da Central de Loja entram na comparação |
| Banco vazio | o **seed do primeiro boot** (60 mesas, 113 produtos, os 2 operadores de turno) + um dia de operação: turno fechado com venda paga, turno aberto com sangria e reforço, comanda viva na mesa 3 |
| Sem fontes: texto = quadradinho | Segoe UI, Segoe UI Emoji e Archivo Black carregadas na mão — o texto aparece, e **conteúdo** passa a ser comparável |

As datas do cenário são congeladas no dia 1 do mês vigente (`_congelar_datas`),
senão duas execuções diferem pelo relógio e não pelo código. E o `--comparar`
agora diz **onde** difere (quantos pixels e o retângulo que os contém), que é o
que permite ir olhar o lugar certo em vez de caçar a olho.

`tools/comparar_cupons.py` é a bancada irmã, para o papel. Reaproveita o mesmo
cenário (`_montar_servicos` + `_povoar`) de propósito: um seed próprio ali seria
uma segunda versão do mesmo dia de operação, livre para divergir — exatamente a
duplicação que a Fase 6 passou o dia caçando.

#### As 24 renderizações, uma a uma

```
9 idênticas   login (2), loja (2), funcionários (2), histórico claro/escuro,
              dashboard-operador
15 diferentes  todas explicadas abaixo
```

| Telas | Por que difere | Origem |
|---|---|---|
| mesas (2), caixa (2) | o **antes** deixa cartão fantasma na grade e no rodapé "Últimos fechamentos" — widget órfão que continuava pintado | §3.7, Fase 4 |
| cardápio (2), impressoras (2), histórico-operador | o **antes** empilha a célula nova por cima da anterior: "CoCozinha", "SIM SIMONLI", e um botão "2ª via" sobrevivendo numa tabela já esvaziada | §3.3, Fase 5 |
| comanda (2), dashboard (2) | o **antes** pinta chip escuro no tema claro (título "Mesa 3" some no branco) e mostra a inicial errada no avatar | §3.15, Fase 5 |
| configurações (2) | seção "Cópia de Segurança" nova — e o defeito abaixo | Fase 2 / Fase 7 |

Ou seja: **13 das 15 diferenças são defeitos que a remasterização matou**, e
esta é a primeira vez que eles aparecem lado a lado em vez de só na descrição
da fase que os corrigiu.

> #### 🔴 O que esta fase descobriu: Configurações espremida até ficar ilegível
> Com a seção "Cópia de Segurança" (Fase 2), o conteúdo da tela passou a somar
> mais altura do que a área de página oferece. `QVBoxLayout` sem rolagem, nesse
> caso, **não corta: espreme**. Os quatro botões "Alterar"/"Cadastrar" de
> Senhas e Acesso foram de 39px para **14px, sem rótulo nenhum** — e os rótulos
> das linhas ficaram sobrepostos aos valores mascarados.
>
> ```
> botao Alterar   h=14  hint=39     label "Senha de Login"  h=6  hint=16
> ```
>
> Por que nenhum dos 799 testes pegou: nenhum mede pixel, e a suíte roda sem
> banco de fontes — sem fonte, o conteúdo mede menos e **cabe**, então o aperto
> nem acontece. Foi preciso a bancada, com fonte de verdade, para o defeito
> existir.
>
> A correção é a `QScrollArea` que o Histórico e o Dashboard já usam. O teste
> (`tests/ui/test_telas_cabem_na_tela.py`) aperta a moldura pela **metade do
> que a própria tela pede**, e não num número fixo de pixels: assim ele reprova
> pelo aperto de verdade tanto na máquina com fonte quanto na sem. Conferido:
> com o `configuracoes_view.py` de antes da correção, o teste reprova; com o de
> agora, passa.

> #### O que a fase NÃO consertou, e por quê
> A mesma bancada, rodada a **1366×738** (um monitor de 768px maximizado, a
> classe de máquina do food truck), mostra o cartão "Recebimentos" da tela de
> **Caixa** com as linhas cortadas ao meio. Rodada nos dois lados, o corte é
> **igual em `b22da75`**: é defeito anterior à remasterização, não regressão
> dela. Fica registrado no §8 como o próximo item de layout — o remédio é o
> mesmo da Configurações, mas aplicá-lo agora seria mudar uma tela no exato
> momento em que o valor do documento é dizer o que mudou e o que não mudou.
> **Corrigido em 2026-09-06, logo depois desta fase — ver §9.**

---

## 7. Métricas de saída — FASE 4

| Métrica | Antes | Depois |
|---|---|---|
| Testes verdes | 620/621 (1 falha) | **800, 0 xfail, 0 falhas** (Fase 7) |
| Arquivos de teste de UI | 0 | **18** (Fase 7) |
| `MainWindow` coberta por teste | ❌ nenhum | ✅ **5 testes** (Fase 5) |
| Testes marcados `xfail` | 7 (Fase 0) | ✅ **0** — reescritos (Fase 4) |
| Caminhos de produção com `rollback()` | 0 | **todos** (Fase 1) |
| `PRAGMA foreign_keys` no app real | 0 | ✅ **1** (Fase 1) |
| Índices em FK | 0 de 20 | ✅ **20 de 20** (Fase 2) |
| Desvios entre schema migrado e `domain/` | 1 (`alembic check` falhava) | ✅ **0** (Fase 2) |
| `journal_mode` | `delete` | ✅ **WAL** (Fase 2) |
| `synchronous` (resiliência a queda de energia) | `FULL` | ✅ **`FULL`, intocado** |
| Cópias de `_formatar_reais` | 10 (+2 com sinal) | ✅ **1 (+1)** (Fase 3) |
| Cópias de "limpar layout" | 4, em 6 sites | ✅ **1** (Fase 4, §3.7) |
| Sites com a versão SEM `setParent(None)` | 3 (`caixa_view`, `mesas_view` ×2) | ✅ **0** (Fase 4) |
| Diálogos de PIN limpando o campo no hook certo | 0 de 2 | ✅ **2 de 2** (Fase 4, §3.9) |
| Aberturas de modal fora de `executar_modal` | 31 de 31 | ✅ **0** (Fase 5, §3.2) |
| Tabelas repopuladas sem destruir os cell widgets | 6 views | ✅ **0** (Fase 5, §3.3) |
| Assinantes de `ThemeController.mudou` sem receptor | 2 de 2 | ✅ **0** (Fase 5, §3.14) |
| Cores de tema congeladas em `setStyleSheet` | 20 | ✅ **0** (Fase 5, §3.15) |
| Cópias do par `unpolish`/`polish` | 10 | ✅ **1** (Fase 5) |
| Telas montadas no boot sem caminho até elas | 1 (`EstoqueView`) | ✅ **0** (Fase 5, §3.11) |
| Funções públicas sem tipagem completa | 23 de 403 | ✅ **0 de 403** (Fase 5) |
| Corpos de função duplicados na camada de UI | 8 (todos entre as 2 telas de Relatórios) | ✅ **0** (Fase 6) |
| Regras diferentes para "diferença total do turno" | 3 | ✅ **1** (Fase 6) |
| Cópias de `_formatar_campo` | 2 | ✅ **1** (Fase 6) |
| Linhas nas 2 telas de Relatórios | 1.126 | **755** + 317 de componente compartilhado (Fase 6) |
| Telas com paridade visual provada pixel a pixel | 0 | **11**, em 24 estados (Fase 7) |
| Documentos ESC/POS com paridade provada linha a linha | 0 | **6 de 6** (Fase 7) |
| Telas que espremem o conteúdo até o rótulo sumir | 1 (Configurações, Fase 2) | ✅ **0** (Fase 7) |
| "Constantes planas" de tema sem leitor | 14 de 22 | ✅ **bloco inteiro removido** (Fase 5) |
| Linhas em `src/` | 17.697 | **18.616** (+919) — ver nota |
| Linhas em `tests/` | 6.794 | **10.478** (+3.684) |

> **Sobre `src/` ter crescido 919 linhas.** Uma faxina que aumenta o código
> pede explicação. As cópias apagadas (10 de `_formatar_reais`, 4 de "limpar
> layout") são pequenas perto do que entrou: `repository/backup.py` (o
> `VACUUM INTO` que torna o WAL seguro, §8), o decorator `@transacional` do
> §3.1, os 20 índices, os 4 utilitários da Fase 3 — e a documentação que
> explica **por que** cada um existe, que é o que impede a próxima limpeza de
> desfazê-los. Encolher `src/` nunca foi meta desta remasterização; a meta era
> não ter duas versões da mesma regra. Essa parte está no quadro acima.
>
> A Fase 5 acrescentou só **+108 linhas** a `src/` — apagou uma tela inteira,
> um pacote vazio, um bloco QSS morto e 22 constantes, e gastou o saldo em
> `ui/widgets/estilo.py` e nas regras de QSS que substituíram os 20
> `setStyleSheet`.
>
> A Fase 6 **diminuiu** `src/` em 38 linhas mesmo criando dois módulos novos:
> as duas telas de Relatórios encolheram 371 linhas somadas, e os componentes
> que herdaram esse código ocupam 317 — a diferença é a duplicação que deixou
> de existir. `src/` tem hoje **94 arquivos**.

### 7.2 Memória — o "depois" que corrigiu o "antes"

Medido com `tools/medir_memoria.py`, headless (`QT_QPA_PLATFORM=offscreen`),
banco temporário, Python 3.14.6 / PySide6 6.11.2.

| Estágio | §2.3 (Fase 1) | Fase 4 |
|---|---|---|
| Interpretador nu | 17,9 MB | 18,5 MB |
| + `QApplication` | 38,1 MB | 38,4 MB |
| + migrations Alembic + seed | 116,1 MB | 117,0 MB |
| **+ shell completo, telas montadas** | **154,5 MB** | **156,0 MB** |
| + 300 aberturas do modal mais simples | 195,3 MB (**+40,8**) | **156,5 MB (+0,5)** |
| Modais vivos após 300 aberturas | 300 de 300 | **0 de 300** |

**Esta tabela não mostra uma correção — mostra um erro de medição sendo
desfeito.** O mesmo script, no mesmo código de hoje, com `--roteiro-antigo`:

| Roteiro, código da Fase 4 | 300 modais custam | Modais vivos |
|---|---|---|
| Caminho real do app (`exec()` + `assentar`) | +0,5 MB | 0 de 300 |
| Roteiro do §2.3 (sem `exec()`, só `processEvents`) | **+41,7 MB** | **300 de 300** |

Os +40 MB continuam reproduzíveis hoje. Não sumiram porque algo foi consertado:
sumem quando se mede pelo caminho que o app percorre. Ver §8.

O leve aumento da linha de base (154,5 → 156,0 MB, **+1,5 MB**) é o custo dos 20
índices da Fase 2 e das tabelas do WAL — pago de propósito, em troca do −91% de
consultas do §7.1.

> **As linhas "Widgets na tabela do Cardápio", "Modais vivos após 300 aberturas"
> e "Cell widgets vivos" saíram desta tabela como "antes × depois".** Os três
> "antes" foram medidos sem laço de eventos e nunca descreveram o app. Estão
> preservados acima e no §8 como o que são: registro de um erro de bancada.

### 7.1 Consultas por tela — Fase 2

Medido num banco com **3 meses de operação real** (3.522 comandas, 14.039
itens, 3.510 pagamentos, 79 turnos), Session nova a cada medição para o cache
não mascarar nada — é o estado de quem acabou de abrir a tela.

| Tela | Consultas antes | Depois | Tempo antes | Depois |
|---|---|---|---|---|
| **Dashboard Mensal** (mês inteiro) | 2.502 | **217** (−91%) | 960 ms | **108 ms** (−89%) |
| Histórico do mês (lista + gavetas) | 183 | **79** | 127 ms | **28 ms** |
| **Tela de Mesas** (grade principal) | 26 | **16** | 22 ms | **4 ms** (−81%) |
| Cancelamentos de 1 turno | 26 | **7** | 8,0 ms | **3,4 ms** |
| Resumo de 1 turno | 15 | **7** | 9,1 ms | **2,2 ms** |

O pior ofensor isolado era `ranking_por_atendente`: **1.326 consultas** para
um mês, porque buscava a comanda de cada pagamento sob demanda. Passou a **6**.

**Escrita** (o outro lado da balança — índice custa no INSERT, WAL devolve):

| | `delete` + sem índice | `delete` + 20 índices | **WAL + 20 índices** |
|---|---|---|---|
| Por item lançado no balcão | 1,17 ms | 3,35 ms | **1,11 ms** |

Ou seja: os índices **triplicaram** o custo de gravação, e o WAL devolveu tudo.
A combinação final grava mais rápido que o ponto de partida, com todas as
leituras muito mais baratas.

---

## 8. Registro de decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-06 | SQLAlchemy permanece | Arrancá-lo seria reescrita, não limpeza (§1) |
| 2026-09-06 | `WA_DeleteOnClose` **rejeitado** em favor de `deleteLater()` em `try/finally` | Modais são lidos após `exec()`; o atributo quebraria essa leitura (§3.2) |
| 2026-09-06 | Rede de segurança de UI **antes** de refatorar UI | ~8.000 linhas hoje sem nenhum teste (§2.2) |
| 2026-09-06 | Integridade de dados promovida para a Fase 1 | §3.1 é o único achado que corrompe dado |
| 2026-09-06 | Hipótese de identity map crescente **descartada** | Medição: SQLAlchemy usa referências fracas (§2.4) |
| 2026-09-06 | `QImage` em `services/imagem_service.py` **mantido** | Remover exigiria Pillow = dependência nova, proibida (§3.13) |

| 2026-09-06 | Rollback via `@transacional`, disparado **só se houver alteração pendente** | Rollback em qualquer exceção quebraria a cascata de PIN e a blindagem da impressão, que usam exceção como fluxo normal (§6, Fase 1) |
| 2026-09-06 | `inspect.getsource` para decorar só métodos que comitam — **descartado** | PyInstaller empacota `.pyc` sem `.py`: funcionaria em dev e falharia no `.exe` |
| 2026-09-06 | `journal_mode = WAL` adiado para a Fase 2 | 10x mais rápido, mas o ganho absoluto (1 ms por ação) é imperceptível, e WAL cria risco de backup incompleto. Não é correção de integridade |
| 2026-09-06 | **`journal_mode = WAL` adotado** (Fase 2) — decisão do Vitor, contra a recomendação registrada acima | O argumento decisivo não é velocidade, é **concorrência**: em WAL leitura e escrita deixam de se bloquear, e é isso que o **App Mobile do Atendente** do backlog vai exigir — com journal `delete`, um segundo cliente lendo o banco trava a gravação da venda. Escolher agora evita migrar o banco do food truck em produção depois |
| 2026-09-06 | Backup por **`VACUUM INTO`**, nunca por cópia de arquivo | É a mitigação que torna o WAL seguro (item acima). O comando grava um `.db` único, completo e desfragmentado a partir do estado consistente (arquivo + WAL) — **não existe `-wal` do backup para esquecer de copiar junto**. Cópia crua do `.db` com o app aberto perde as últimas vendas, e foi reproduzido em teste (`test_backup_leva_a_venda_que_ainda_esta_no_wal`) |
| 2026-09-06 | `wal_checkpoint(TRUNCATE)` no fechamento de caixa e no encerramento do app | Mantém o `.db` sempre completo no disco com o programa fechado. Verificado ponta a ponta: o `-wal` fica com **0 bytes** depois que o app encerra |
| 2026-09-06 | **`synchronous` NÃO baixado para `NORMAL`** | Toda documentação de WAL sugere isso, e é armadilha aqui: `NORMAL` protege contra o app morrer, **não** contra a energia cair no meio do commit — que é o cenário do food truck e o que `test_resiliencia_queda_energia.py` prova. Fica em `FULL`, e há um teste travando isso |
| 2026-09-06 | Rotina de backup entra apesar da regra "nenhuma funcionalidade nova" | Exceção deliberada, pedida pelo Vitor: é ela que torna segura a decisão do WAL, tomada dentro desta remasterização. Sem ela, a fase entregaria um risco novo de perda de dados em vez de remover um |
| 2026-09-06 | FK de `quitacoes_consumo` corrigida na Fase 2, fora do escopo original | A Fase 1 ligou o `PRAGMA foreign_keys` e com isso **ativou** um desvio de schema que dormia desde `d23a4f888a77`. Fechar a fase sabendo disso seria entregar uma quebra de produção invisível para a suíte (§3.5) |
| 2026-09-06 | Contagem de FKs corrigida de 38 para 20 | `PRAGMA foreign_key_list` sobre o schema real, em vez de contar linhas de `grep`. O achado ("zero índices") continua inteiro; só o denominador estava errado |
| 2026-09-06 | 5 `.md` de refatoração → `docs/historico/` com README de aviso | Documentação que contradiz o código convida a uma "limpeza" que quebra o app; arquivar preserva o porquê das decisões sem poluir a raiz (§3.12) |
| 2026-09-06 | **Formato monetário: `R$ 1.234,50`** (Fase 3) — decisão do Vitor | Vence a fórmula que era minoria (só `mesas_view` a usava) porque é a correta em português, é a que o cupom impresso já usava, e porque num turno bom o food truck passa de mil reais — `R$ 1234,50` era o caso comum, não a exceção. Muda a aparência de 9 telas, de propósito (§3.8) |
| 2026-09-06 | Aplicação nas 10 telas feita **dentro da Fase 3**, não na Fase 5 | Pedido do Vitor. O utilitário sozinho não corrige nada: enquanto as views não importarem dele, a divergência que o usuário vê continua na tela |
| 2026-09-06 | Sinal do negativo unificado em `-R$ 12,00` | A tela do Caixa mostrava as duas convenções ao mesmo tempo — `-R$ 12,00` na sangria e `R$ -12,00` na diferença. Venceu a que já era maioria e a que `formatar_reais_com_sinal` já usava |
| 2026-09-06 | `ui/formatacao.py` chama `dinheiro()` antes de formatar | Sem isso a tela arredondaria meio-para-o-par (padrão do Python) e o cupom meio-para-cima — `R$ 0,00` na tela contra `0,01` no papel na mão do cliente. Um teste tranca a igualdade dos dois |
| 2026-09-06 | Separador de milhar **duplicado** em `ui/formatacao` e `formatador_cupom.moeda`, guardado por teste | Unificar exigiria a UI importar um módulo de cupom, ou mexer no formatador durante a fase cujo critério de pronto é impressão byte a byte idêntica (§7). São 1 linha em cada lado, e `test_a_tela_e_o_cupom_mostram_o_mesmo_numero` impede a divergência |
| 2026-09-06 | **§3.3 derrubado** e **§3.2 rebaixado** (Fase 3) | Remedidos com `app.exec()` rodando, em `offscreen` e em `windows`: as tabelas não vazam (78 → 78 widgets em 21 refreshes) e os modais só vazam pelo caminho `reject()` sem `exec()`, que nenhum dos 31 sites percorre. As medições originais rodaram sem laço de eventos, e sem laço `deleteLater()` nunca sai do papel |
| 2026-09-06 | **§3.9 rebaixado de ALTA para MÉDIA** | O hook errado (`closeEvent` em vez de `done()`) foi confirmado por medição e continua valendo correção. O "PIN para sempre na memória" dependia do §3.2 e caiu junto com ele: o diálogo é destruído ao sair de escopo (§3.9) |
| 2026-09-06 | `modais.py` e `tabelas.py` entregues mesmo com os achados corrigidos | O que entregam deixou de ser correção de vazamento e passou a ser garantia explícita/determinismo — barato, testado, e independe de detalhe de implementação do Qt. Quem decide se vale aplicar nos 37 sites é a Fase 4, com o achado já corrigido na mesa |

| 2026-09-06 | **Fase 4 no escopo enxuto** — decisão do Vitor | §3.7 + §3.9 + reescrita dos 7 `xfail` + medição de RSS. Com o §3.3 derrubado e o §3.2/§3.9 rebaixados, aplicar os utilitários nos 31 + 6 sites virou padronização, não correção de vazamento — e padronização é o objetivo declarado da Fase 5, não o da fase que existe para blindar memória |
| 2026-09-06 | **`EstoqueView` será removida** — decisão do Vitor | Tela instanciada no boot e registrada na navegação, mas sem nenhum caminho de usuário até ela (§3.11): a Central de Loja renderiza 5 cards e "Estoque" não é um deles. É peso morto no boot e no `.exe` de um módulo que está no backlog pós-V1. O git guarda o código para quando a fase de Estoque começar. Executada como primeiro item da Fase 5, em commit próprio, para não embaralhar as fases |
| 2026-09-06 | **Os 7 `xfail` foram reescritos, não "corrigidos"** (Fase 4) | Eles mediam a API crua do Qt — `tabela.setCellWidget(...)`, `CancelamentoDialog(...)` + `reject()` — sem passar por utilitário nem por view. Nenhuma correção feita no app poderia deixá-los verdes: o critério de pronto da fase era literalmente inalcançável. Passaram a exercitar os diálogos reais com `exec()` e as telas reais com `atualizar()` |
| 2026-09-06 | `test_vazamento_tabelas.py` → `test_vazamento_telas.py` | O nome prometia cobrir as tabelas do app e cobria `QTableWidget` cru. O arquivo agora varre as 13 telas da fixture `todas_as_telas`, e a fixture saiu do arquivo de smoke para o `conftest` justamente para as duas redes lerem a mesma lista |
| 2026-09-06 | **O §2.3 (memória) é artefato de medição, como o §3.2 e o §3.3** (Fase 4) | `tools/medir_memoria.py --roteiro-antigo` reproduz os +40,8 MB e os 300 modais vivos **hoje**, com a Fase 4 pronta. Pelo caminho real do app, os mesmos 300 modais custam +0,5 MB e deixam 0 vivos. Nenhuma linha de produção separa as duas colunas — só o método. São três achados de memória vindos do mesmo erro de bancada |
| 2026-09-06 | Bancada de medição versionada em `tools/medir_memoria.py` | Três achados do documento vieram de uma medição que ninguém conseguia repetir. `ctypes` em vez de `psutil` porque nenhuma dependência nova entra — nem em ferramenta. Fica fora de `src/`, então não entra no `.exe` |
| 2026-09-06 | Toda correção da Fase 4 foi conferida **desfazendo-a** | Ver a suíte verde depois da correção não prova nada — foi assim que os `xfail` nasceram medindo a coisa errada. Sem o `setParent(None)`, 6 testes de `test_layout_utils.py` falham; com o `closeEvent` de volta, 6 dos 10 de `test_pin_dialogs.py` falham |
| 2026-09-06 | `gc.collect()` na destruição de telas **descartado** da Fase 5 | Estava listado como "se a medição mostrar ganho". A medição existe agora e mostra o contrário: não há o que recolher, e a pausa custa caro na máquina fraca do food truck |
| 2026-09-06 | **`limpar_tabela` ganhou `preservar_selecao`** (Fase 5) | A troca cega apagaria a seleção que hoje sobrevive ao refresh: as views chamavam `setRowCount(len(dados))` sem zerar antes, e nesse caminho o Qt mantém a linha corrente. Medido antes de trocar (linha 1 de 3 selecionada: `setRowCount(3)` → 1; `setRowCount(0)`+`setRowCount(3)` → -1). Sem o parâmetro, editar um produto o deixava sem seleção e apagava os botões do rodapé. A restauração vai com os sinais bloqueados, para o observável ficar idêntico ao de antes |
| 2026-09-06 | **`MainWindow` ganhou teste** (Fase 5) | Remover a `EstoqueView` mexe em quatro lugares do mesmo arquivo, e descobriu-se que **nenhum teste montava a `MainWindow`** — a peça que compõe todas as outras. Um esquecimento ali só apareceria no boot. Os 5 testes novos também transformam o §3.11 em invariante: destino sem card no hub, e card sem destino, agora reprovam |
| 2026-09-06 | Cache de miniaturas **não assina** o `ThemeController` (Fase 5) | O §3.10 pedia que os placeholders acompanhassem a troca de tema. Assinar o sinal criaria uma conexão permanente a um singleton, sem ninguém para desfazê-la — o próprio §3.14. Em vez disso o cache compara a paleta por identidade a cada miniatura pedida e descarta o que foi pintado com a anterior |
| 2026-09-06 | Pares `unpolish`/`polish` unificados junto com o §3.15 (Fase 5) | Não estavam na lista dos 9 itens. Entraram porque o §3.15 precisava do mesmo par para trocar a propriedade de tom, e deixar nove cópias quase idênticas ao lado do utilitário novo seria criar exatamente o cheiro que esta remasterização existe para matar (§3.7, §3.8) |
| 2026-09-06 | `PIN_MIN_DIGITOS = 4` **removida** com o resto do código morto (Fase 5) | ⚠️ Era uma regra de negócio que **nunca foi implementada**: nenhum ponto do app valida o tamanho mínimo do PIN. Removê-la não muda comportamento nenhum, mas apaga a intenção — se exigir 4 dígitos ainda for desejado, é decisão de produto e entra como validação de verdade, não como constante sem leitor |

| 2026-09-06 | **Fase 6 no escopo "só a duplicação real"** — decisão do Vitor | O critério da fase era "quebrar views gigantes só onde compensar", e a varredura de corpos de função respondeu onde compensa: as 8 cópias da camada de UI estão todas entre as duas telas de Relatórios, e **nenhuma** nas cinco views grandes. Partir aquelas cinco moveria ~4.500 linhas sem nenhum teste capaz de dizer se ficou melhor — risco máximo, retorno estético |
| 2026-09-06 | Estado do filtro passou a morar no componente, não nas telas | `FiltroPeriodoOperador` é dono de `_operador_selecionado`, `_algum_operador_clicado` e `_nome_operador_selecionado` — três atributos que cada tela mantinha em paralelo. O Dashboard nem usava o terceiro; ganhou de graça, sem mudar o que aparece |
| 2026-09-06 | Dois sinais (`periodo_mudou` / `operador_mudou`), não um só | Um sinal único de "filtro mudou" seria mais simples e mudaria comportamento: `RelatoriosView` assina só a troca de **período** para o subtítulo da aba, e passaria a ser chamada também na troca de operador. O contrato de zero-regressão (§4) vale para detalhe assim |
| 2026-09-06 | A barra de filtro virou `QWidget` com `objectName` + regra de fundo transparente | Um `QWidget` sem `objectName` herda o `QWidget { background: bg_marca }` global e pinta um retângulo por trás das pílulas — o mesmo tropeço já documentado em `SecaoCancelamentos`. Junto, `setContentsMargins(0,0,0,0)`: layout aninhado nasce sem margem, layout instalado em widget herda a do estilo |
| 2026-09-06 | **`ResumoCaixa.diferenca_total`**: as 3 regras da mesma conta viraram 1 | Gaveta impressa exigia as duas contagens, tela do Caixa tratava a que faltasse como zero, Histórico Diário somava `Decimal + None` (estoura). Vence o critério conservador: sem as duas contagens não há diferença a afirmar. **Nenhum teste pega a divergência** — ela é inalcançável hoje (as duas contagens sempre viajam juntas), e pôr a regra antiga de volta deixa a suíte inteira verde. Por isso a proteção é o teste de premissa, que cai no dia em que o fechamento parcial existir |
| 2026-09-06 | `formatar_para_campo` passa por `dinheiro()` | As duas cópias de `_formatar_campo` usavam `f"{valor:.2f}"` — meio para o par, a mesma divergência com o cupom que o §3.8 corrigiu no resto do módulo. Para valor gravado (Numeric(10,2)) o resultado é idêntico; a mudança tira a segunda política de arredondamento de dentro do módulo que existe para ter só uma |
| 2026-09-06 | Bancada de paridade visual versionada em `tools/comparar_telas.py` | A fase mexeu na montagem de duas telas inteiras e a suíte não compara pixel. Renderizar offscreen e comparar PNG com o commit anterior provou o que teste nenhum provava — e é a ferramenta que a Fase 7 usa na paridade tela a tela. Mesmo critério do `medir_memoria.py`: sem dependência nova, fora de `src/` |
| 2026-09-06 | Varredura de corpos duplicados virou teste, não relatório | Foi ela que redefiniu o escopo da fase; sem virar catraca, a Fase 6 valeria só no dia em que foi escrita. Compara o `ast.dump` do corpo (nome não conta — era assim que `_criar_linha_forma`/`_criar_linha_atendente` passavam) e ignora funções com menos de 4 comandos, para não acusar delegação de uma linha |
| 2026-09-06 | **Fase 7 compara com `b22da75`, o commit anterior à Fase 0** | Comparar com o commit anterior (Fase 6) provaria só a última fase. O que interessa antes da produção é o efeito das 8 fases somadas sobre o que o pai do Vitor vê — e é essa comparação que transforma 13 correções descritas em prova visível lado a lado |
| 2026-09-06 | A bancada de telas passou a montar a **`MainWindow` real**, com seed e fontes | Três limitações da versão da Fase 6 escondiam defeito: view solta não compara a sidebar nem as barras do shell; banco vazio não enche tabela nenhuma (e é dentro de tabela que moravam as células empilhadas); e a plataforma `offscreen` sobe **sem banco de fontes**, então todo texto virava quadradinho e a comparação enxergava layout, não conteúdo |
| 2026-09-06 | Cupons: **hora normalizada**, datas do banco **congeladas** | São dois problemas diferentes. A data gravada no dado é congelada no seed (`_congelar_datas`), mas a hora de impressão vem de um `datetime.now()` dentro do serviço, que nenhum dado alcança — normalizar `HH:MM:SS` no `diff` é o que permite exigir igualdade em todo o resto do cupom |
| 2026-09-06 | `comparar_cupons.py` reaproveita o cenário de `comparar_telas.py` | Um seed próprio seria uma segunda versão do mesmo dia de operação, livre para divergir daquele — a duplicação que a Fase 6 passou a fase inteira caçando. As duas bancadas comparam o mesmo sistema no mesmo estado |
| 2026-09-06 | **Configurações ganhou `QScrollArea`** (regressão da Fase 2, achada na Fase 7) | A seção "Cópia de Segurança" empurrou o conteúdo além da altura da página, e `QVBoxLayout` sem rolagem espreme em vez de cortar: os botões de Senhas e Acesso foram a 14px sem rótulo. É correção de regressão da própria remasterização, então entra dentro dela |
| 2026-09-06 | O teste do aperto mede em **fração do que a tela pede**, não em pixels fixos | A suíte roda em `offscreen`, sem fonte: com um número absoluto o conteúdo caberia, o aperto não aconteceria e o teste passaria com o bug de pé. Metade do `sizeHint` da própria tela reprova em qualquer máquina |
| 2026-09-06 | **Cartão "Recebimentos" da tela de Caixa a 768px fica de fora** | A bancada a 1366×738 mostra as linhas cortadas ao meio — e mostra **igual em `b22da75`**: é defeito anterior à faxina, não regressão. O remédio é o mesmo da Configurações, mas aplicá-lo aqui seria mudar uma tela justamente no documento cujo valor é separar o que mudou do que não mudou. Fica como primeiro item de layout depois da remasterização — **feito em 2026-09-06, §9** |

### Decisões pendentes do Vitor

**Nenhuma.** As duas que bloqueavam o trabalho foram decididas em 2026-09-06 e
estão registradas no quadro acima:

~~1. `EstoqueView`~~ — **decidido**: remover. ✅ Executado na Fase 5.

~~2. Escopo da Fase 4~~ — **decidido**: enxuta, mais a medição de RSS. Fase
concluída; os 31 + 6 sites e as lambdas do tema migraram para a Fase 5, e ✅
foram executados lá.

~~3. Formato monetário~~ — **decidido em 2026-09-06**: `R$ 1.234,50`. Ver §8.

~~4. `journal_mode = WAL`~~ — **decidido em 2026-09-06**: adotado, com backup
por `VACUUM INTO` e checkpoint no fechamento. Ver §8.

---

## 9. Depois da remasterização — registro contínuo

> A faxina fechou com um defeito de layout **anterior** a ela documentado e de
> pé (§8, última linha): o cartão "Recebimentos" da tela de Caixa cortava as
> linhas ao meio num monitor de 768px. Ficou de fora de propósito — mudar uma
> tela durante a comparação tiraria a paridade contra a qual comparar. Com o
> documento fechado, a paridade já foi prestada, e o defeito passou a ser
> simplesmente o próximo item. Esta seção é o que veio **depois** da fase 7, e
> continua sendo o lugar de cada trabalho que entra na V1 daqui em diante — um
> item por subseção, com data.
>
> | | | |
> |---|---|---|
> | §9.1 | 2026-09-06 | O cartão "Recebimentos" espremido |
> | §9.4 | 2026-09-08 | O modal "Adicionar item" refeito |

### 9.1 O cartão "Recebimentos" espremido ✅ CORRIGIDO

Reproduzido com a bancada a **1366×738** (o monitor de 768px com a janela
maximizada, descontada a barra de tarefas — a máquina do food truck):

```
janela 1366x738  tela 1106x682 (sizeHint 1051x753)
  ESPREMIDO h= 6 hint=16  caixaFormaNome   'Dinheiro'   ... e mais 20 rótulos
```

A página oferece **682px** e a tela pede **753**. É o mesmo mecanismo da
Configurações: `QVBoxLayout` sem rolagem **não corta, espreme** — as quatro
linhas de "Recebimentos" caem de 16px para **6px**, nome e valor cortados ao
meio, e os cinco "Ajustes do turno" para 12px.

**A correção** é a `QScrollArea` da Configurações, aplicada só na **coluna de
resumo** (saldo, recebimentos, ajustes). A coluna da direita fica de fora de
propósito: lá quem cede altura é a tabela de movimentos, que já rola sozinha, e
envolver as duas criaria rolagem dentro de rolagem.

**O que a medição mudou no caminho.** A primeira versão trocou um corte por
outro: com a barra de rolagem visível, o viewport nasce com **326px** para um
cartão cujo mínimo é **340**, e — com a barra horizontal desligada — a lateral
direita do cartão sai cortada. A coluna passou a reservar a largura da própria
barra (`_LARGURA_MIN/MAX_RESUMO + barra`), e os dois limites viraram constantes
porque agora têm dois donos: o cartão de saldo e a rolagem que o envolve.

| | Antes | Depois |
|---|---|---|
| Linhas de "Recebimentos" a 1366×738 | 6px de 16px | **16px, inteiras** |
| Rótulos espremidos na coluna | 21 | **0** |
| Viewport × mínimo do cartão | 326 < 340 (cortava) | **340 = 340** |

### 9.2 Como foi conferido

- **Teste** — `test_linhas_de_recebimentos_nao_encolhem_quando_a_pagina_e_baixa`
  entrou em `tests/ui/test_telas_cabem_na_tela.py`, ao lado do teste da
  Configurações, e com a mesma régua: a moldura aperta pela **metade do que a
  própria tela pede**, não num número fixo de pixels, senão a suíte sem banco
  de fontes não reprovaria. Conferido **desfazendo a correção**: com o
  `caixa_view.py` de antes, 8 de 8 linhas reprovam.
- **Suíte** — `801 passed` (de 800), nenhum teste tocado.
- **Paridade** — as 24 renderizações da Fase 7, rodadas em 1280×800 **e** em
  1366×738: **22 idênticas byte a byte** nos dois tamanhos; diferem só
  `caixa-claro` e `caixa-escuro`, que é a tela corrigida. A coluna da direita
  desloca 14px por causa da barra reservada, e é por isso que a diferença
  ocupa a largura do corpo em vez de só a coluna.
- **Bancada** — `tools/comparar_telas.py` ganhou `--tamanho LxA`. O 768px era
  reproduzido editando a constante na mão; agora é um argumento, e o tamanho em
  que os dois defeitos apareceram fica registrado no próprio comando.

### 9.3 Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-06 | Rolagem **só na coluna de resumo**, não na tela inteira | A coluna da direita é uma tabela que rola sozinha; envolver as duas poria uma rolagem dentro da outra, e o que estoura a altura é a coluna de altura fixa |
| 2026-09-06 | A rolagem **reserva a largura da barra** | Sem a reserva o viewport fica menor que o mínimo do cartão (326 contra 340) e a lateral direita é cortada — trocar corte de cima por corte de lado não é correção. Custa 14px de largura da tabela de movimentos, que reflui |
| 2026-09-06 | Barra de rolagem fica com o **visual padrão do Qt** | É o mesmo da Configurações e do Histórico. Estilizá-la só aqui criaria uma terceira aparência de rolagem; estilizá-la global é mudança de tema para todas as telas, e não é o que este item pede |
| 2026-09-06 | `--tamanho` na bancada em vez de editar `TAMANHO` | Os dois defeitos de aperto (Configurações e Caixa) só existem numa altura específica. Ou o tamanho é argumento do comando, ou a reprodução depende de alguém lembrar de editar a constante |


### 9.4 O modal "Adicionar item" refeito ✅ CONCLUÍDO — 2026-09-08

Pedido do Vitor, com dois mockups: substituir a janela legada de lançar produto
na comanda pela interface moderna, **mantendo a miniatura do produto** ao lado
de cada item. O modal antigo (`_AdicionarItemDialog`, 60 linhas dentro de
`comanda_view.py`) era um `QFormLayout` com a moldura de janela do sistema, um
`QSpinBox` de setinha e uma lista de texto corrido:
`"Arroz — R$ 10,00 — Acompanhamentos"`. É a tela por onde entra **cada produto
de cada comanda** — a mais usada do turno.

O resultado mora em `ui/widgets/adicionar_item_dialog.py` e segue o arranjo do
`pin_pad_dialog`: cartão sem moldura, escurecedor atrás, cabeçalho próprio
(`MESA 3 · LANÇAMENTO RÁPIDO` / `Adicionar item` / ✕). Dentro: busca com lupa
desenhada e anel âmbar no foco, faixa de pílulas de categoria, lista com
miniatura circular, e um rodapé com quantidade, observação e a prévia do valor.

**Nenhuma regra de negócio mudou.** O diálogo não conhece `ComandaService`:
recebe um `lancar_item(produto_id, quantidade, observacao)` e chama. O
`R$ 20,00` do rodapé é preço × quantidade **para o operador conferir** — não
entra em cálculo, não é gravado, e o total da comanda continua inteiro no
service. O fluxo rápido também é o de antes: `Enter` lança e o modal **fica
aberto**, com os campos zerados e o foco de volta na busca.

#### O que a digitação deixou de custar

O modal fica aberto lançando item atrás de item, e é aí que estava o defeito.
`lancar_item` faz commit, **e o commit expira os atributos das instâncias do
SQLAlchemy** — então era depois de *cada item lançado* que a busca voltava a
bater no banco a cada tecla. Medido sobre o cardápio real do food truck (113
produtos), contando com `after_cursor_execute`:

| | Antigo | Novo |
|---|---|---|
| Primeira tecla, lista fria | 9 consultas | — |
| Teclas 2 a 4 | 0 consultas | **0** |
| 3 teclas **depois de lançar um item** | **120 consultas** | **0** |
| Abertura do modal (instantâneo, frio) | — | 128 consultas, **uma vez** |

A troca é deliberada: paga-se na abertura, fora do caminho da tecla, o que
antes se pagava de novo a cada lançamento. As 128 da abertura são o **N+1 do
§3.6** aparecendo aqui; virariam 2 com `selectinload` no
`produto_repository.listar_ativos_de_categoria_ativa`. Ficou **de fora de
propósito**: é mudança num repositório que serve outras telas, e este item era
o modal.

Fora da conta de consultas, e no mesmo caminho: a lista virou uma
`QStyledItemDelegate`, então digitar não constrói mais um `QListWidgetItem`
**com `QIcon`** por produto filtrado, e a pintura acontece só nas ~4 linhas
visíveis. `formatar_reais` (que passa por `Decimal.quantize`) saiu do por-tecla
para o por-abertura junto com o resto do instantâneo.

#### O defeito que só a bancada visual pegou

A suíte fechou verde com os 5 produtos da fixture. A primeira renderização com
o **cardápio real** mostrou outra coisa: com 15 categorias, o `FlowLayout` da
faixa de filtros quebrava em 6 fileiras, o `QVBoxLayout` reservava a altura de
**uma** (é o que `FlowLayout.sizeHint()` devolve) e as outras cinco eram
pintadas **por cima da lista de produtos**.

É o parente do §9.1 e do defeito da Configurações: layout que não corta,
espreme — só que aqui nem espremia, transbordava. A correção é o teto de
`FILEIRAS_DE_CATEGORIA = 2` com rolagem em volta, e a altura real fechada no
`showEvent`, **depois** do primeiro `polish`: antes dele o `sizeHint` de uma
pílula não conhece o `padding` que o QSS global aplica.

#### O que a suíte cobrou no caminho

`test_nenhuma_funcao_da_ui_repete_o_corpo_de_outra` (Fase 6) reprovou o commit:
`_preparar_botao` e `_centralizar_no_pai` tinham sido **copiados** do
`pin_pad_dialog`. Viraram `ui/widgets/cartao_modal.py`, que passa a ser o dono
das peças comuns dos dois modais em cartão — o escurecedor (`montar`/
`descartar`), o `preparar_botao` e o `centralizar_no_pai`. Foi a varredura
funcionando exatamente como o §3 desenhou: a cópia não passou de um commit.

#### Como foi conferido

- **Suíte** — `946 passed` (de 918). 27 testes novos em
  `tests/ui/test_adicionar_item_dialog.py` e 1 no inventário de
  `test_vazamento_modais.py`.
- **Os dois testes que importam foram conferidos desfazendo a correção**, como
  manda o §9.2: sem `_garantir_filtro_aplicado()`, o teste do Enter apressado
  reprova; sem `_ajustar_altura_da_faixa()`, o teto da faixa reprova.
- **Bancada visual** — o cartão renderizado nos dois temas com o cardápio real,
  na plataforma nativa (a `offscreen` não rasteriza texto). 500×630 num monitor
  de 738px de altura.
- **Ciclo de vida** — 30 aberturas com `exec()` não deixam diálogo preso à
  view; 10 aberturas não deixam escurecedor pendurado na janela.

#### Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-08 | O segundo mockup manda no layout; o **âmbar do tema** manda na cor | O mockup trazia turquesa no botão Adicionar e no total. O acento do app é `acento` (âmbar no escuro, azul no claro) e funciona nos dois temas de graça; uma segunda cor de "ação primária" só existiria nesta tela |
| 2026-09-08 | `QStyledItemDelegate` em vez de um widget por linha | `funcionarios_view` monta widget por linha e está certo lá — a lista muda ao clicar num filtro. Aqui ela é refiltrada a cada tecla, e widget por produto é o lag que o RNF proíbe |
| 2026-09-08 | Instantâneo do cardápio na abertura, em vez de ler o ORM ao filtrar | Ver a tabela acima: tira o banco do caminho da tecla em qualquer estado, inclusive depois do commit de um lançamento |
| 2026-09-08 | O teclado é lido **só** no `keyPressEvent` do diálogo | Ligar `returnPressed` dos campos **além** disso lançaria o item duas vezes com um Enter só: o `QLineEdit` ignora o Return e ele sobe para o diálogo. Por isso lista e botões ficam sem foco |
| 2026-09-08 | Faixa de categorias com teto de 2 fileiras e rolagem | 15 categorias no cardápio real. Sem teto, o cartão sai da tela do food truck; com teto, quem passa disso rola — e a busca continua sendo o caminho rápido |
| 2026-09-08 | `Esc` fecha o modal, em vez de limpar a busca primeiro | O briefing pede fechamento com descarte. O comportamento antigo (1º Esc limpa, 2º fecha) continua no `BuscaProdutoWidget`, que o modal de combos do Cardápio ainda usa |
| 2026-09-08 | Tokens `pin_fechar_*` renomeados para `botao_circular_*` | Mesmos quatro hex vestem o ✕ dos dois modais e os passos −/+ da quantidade. O nome passou a ser o papel, e não a tela; duplicar a família seria pior |
| 2026-09-08 | `selectinload` no repositório fica **fora** deste item | As 128 consultas da abertura são o §3.6, não o modal. Mexer num repositório que serve outras telas pede medição própria e paridade própria |
| 2026-09-08 | O `BuscaProdutoWidget` antigo **continua existindo** | O modal "Adicionar componente" do Cardápio (`_ComponenteDialog`) ainda o usa, e não estava no escopo. `filtrar_produtos` é compartilhada entre os dois, com os testes dela intactos |

---

### 9.5 O modal "Novo funcionário" e o vermelho da mesa ocupada ✅ CONCLUÍDO — 2026-09-08

Dois pedidos do Vitor no mesmo dia, com um mockup para o primeiro.

#### Parte 1 — o modal de cadastro da equipe

O `_FuncionarioDialog` eram 40 linhas dentro de `funcionarios_view.py`: três
campos empilhados num `QFormLayout`, com a moldura de janela do sistema e um
`QComboBox` de setinha para o cargo. Não é a tela mais usada do turno (essa é a
de lançar item, §9.4), mas é a que decide **quem existe no sistema** — e
"Cargo: [Garçom ▾]" não diz o que um garçom pode fazer no PDV.

O resultado mora em `ui/widgets/funcionario_dialog.py` e é o **terceiro** modal
em cartão do app, no mesmo arranjo do PIN e do "Adicionar item": cartão sem
moldura, escurecedor atrás, cabeçalho próprio. Dentro: badge de identidade com
ícone desenhado à mão, avatar que monta as iniciais enquanto se digita o nome,
os cinco cargos como **cards com descrição** em grade de duas colunas, telefone
com máscara, situação Ativo/Inativo em pílulas, e um rodapé que diz em voz alta
o que o cargo marcado libera (`CAIXA · ACESSO LIBERADO`).

**Nenhuma regra de negócio mudou, e nenhum método de service é novo.** O
diálogo não conhece `FuncionarioService`: devolve um `DadosFuncionario` e a
view chama `criar`/`editar` como antes. A situação também não virou campo: o
funcionário continua nascendo ativo em `criar()`, e a view usa `ativar()`/
`desativar()` — o mesmo par que o botão do painel de detalhe já usava — quando
a escolha diverge do estado atual. O modal não abriu caminho novo para o banco;
abriu uma segunda porta para o caminho que já existia.

##### O que a tela promete e o que o sistema faz pararam de poder divergir

"ACESSO" nunca foi campo do domínio (§3.14): é derivado do cargo. A derivação
morava solta em `funcionarios_view` como um conjunto de dois nomes
(`_CARGOS_ACESSO_TOTAL`), e o texto do rodapé do modal seria uma **segunda**
lista dizendo a mesma coisa. Os dois passaram a ler `CARGOS`, onde cada cargo
carrega o valor que vai para o banco, a descrição do card e o resumo de acesso.
Enquanto fossem duas listas, "Gerente e Caixa" precisava estar certo em dois
arquivos ao mesmo tempo.

##### "Atendente" virou "Entregador" — e isso é mudança de dado

O mockup pede cinco cargos, e o quinto é **Entregador**, não "Atendente".
"Atendente" não descrevia função nenhuma do food truck (todo mundo ali atende);
quem leva o pedido do delivery, sim. `CargoFuncionario.ATENDENTE` virou
`ENTREGADOR`.

`funcionarios.cargo` é `String`, não `Enum` de banco, então o **schema** não
muda — mas o valor gravado, sim, e é por isso que a mudança veio com a migração
`a7f3c2e5d918`. Sem ela, um funcionário já cadastrado como "Atendente"
continuaria na lista, abriria o modal de edição com **nenhum** cargo marcado e
perderia o cargo na primeira vez que alguém mexesse em qualquer outro campo —
sem aviso. Nenhum `Funcionario` do `seed.py` usa "Atendente" (o bootstrap só
cria Caixas), então na máquina do food truck a migração provavelmente não vai
tocar em linha nenhuma; ela existe para o cadastro feito à mão.

#### Parte 2 — Vermelho Ferrari na mesa ocupada

A mesa em atendimento era ciano, e o comentário no QSS dizia por quê: "ocupada
é estado normal, não um alerta". A leitura de balcão é a oposta — mesa ocupada
é **onde está o dinheiro em aberto do salão**, e é o que se procura de relance
numa grade de sessenta. Virou `#DC2626`, o mesmo nos dois temas (o único token
de status que não muda entre Claro e Escuro), com o corpo do card tingido:
`#2D1214` no escuro, `#FEE2E2` no claro, textos em branco e em carmim
`#991B1B`. A borda, os dois pontinhos de legenda (`● OCUPADA` no resumo do
salão e o da comanda no painel da direita) e a palavra OCUPADA acompanham,
porque todos leem a mesma família de tokens.

##### A cor tinha carona

`mesa_ocupada_borda` não era lido só por seletor de mesa: o **badge de despesa
do Caixa** e o **link de pendências das Impressoras** pegavam aquele ciano
emprestado. Pintar a mesa de vermelho pintaria de vermelho a despesa do caixa
junto, e ninguém veria até abrir aquela tela. Os dois passaram a ler
`ciano_metrica`, que é a cor que queriam — e uma varredura no
`test_mesas_ocupadas_em_vermelho.py` reprova quem recolar o empréstimo. Ela
descobre quem lê um token trocando o valor dele por uma sentinela e procurando
a sentinela no QSS montado, em vez de ler o template com expressão regular.

##### O corte que o fundo tingido revelou

Com o corpo do card na cor da superfície, ninguém via que o card ocupado tem
**quatro** linhas (número, tag, valor, atendente) contra as duas da mesa livre:
ele media 110px de conteúdo e era desenhado com 96, o piso de
`setMinimumSize`. O valor em aberto saía cortado ao meio e o nome de quem
atende não aparecia — no card da mesa que tem dinheiro pendurado, e justo o
dado que a cor nova existe para destacar.

É o parente do §9.1 e da Configurações da Fase 7: layout que não corta,
espreme. O piso subiu para `ALTURA_PX = 112`, medido, e o que a suíte cobra não
é o número: é o invariável de que nenhum card seja desenhado menor que o
próprio `sizeHint`.

#### O que a suíte cobrou no caminho

O teste do corte **passava verde com o defeito no lugar**, e por um motivo que
vale registrar: a plataforma `offscreen` sobe com o banco de fontes **vazio**, e
sem fonte o card ocupado mede 93px em vez de 110 — o aperto simplesmente não
acontece ali. A correção foi registrar, na fixture, a fonte que o próprio app
registra no boot (`resources/fonts/ArchivoBlack-Regular.ttf`, que vive no
repositório) e devolvê-la ao banco no fim. Sem isso, o arquivo teria três
testes que nenhuma regressão poderia deixar vermelhos — exatamente o que o §9.2
manda conferir antes de fechar.

#### Como foi conferido

- **Suíte** — `1009 passed` (de 946). 47 testes novos em
  `tests/ui/test_funcionario_dialog.py`, 15 em
  `tests/ui/test_mesas_ocupadas_em_vermelho.py` e 1 no inventário de
  `test_vazamento_modais.py`.
- **Os testes que importam foram conferidos desfazendo a correção**, como manda
  o §9.2: com `ALTURA_PX = 96` os dois testes de corte reprovam (`mesa 1: 96px
  < 110px`); devolvendo o empréstimo do ciano, a varredura da carona reprova.
- **Bancada visual** — `tools/comparar_telas.py --tamanho 1366x738` nos dois
  temas: das 24 renderizações, 22 **idênticas byte a byte** e só as duas de
  Mesas diferindo. O cartão do modal foi renderizado na plataforma nativa
  (520×536 num monitor de 738px de altura), em branco, preenchido e em edição,
  nos dois temas.
- **Migração** — aplicada do zero num banco temporário até a `head`, com um
  `Funcionario` gravado como "Atendente": `upgrade` reescreve para "Entregador",
  `downgrade` devolve, `upgrade` reescreve de novo.
- **Ciclo de vida** — 30 aberturas com `exec()` não deixam diálogo preso à view;
  10 aberturas não deixam escurecedor pendurado na janela.

#### Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-08 | O mockup manda no layout; o **acento do tema** manda no botão Cadastrar | Mesma decisão do §9.4, e pelo mesmo motivo: o mockup traz turquesa na ação primária, mas o app já tem uma (`acento` — âmbar no escuro, azul no claro) e ela funciona nos dois temas de graça. Uma segunda cor de "ação primária" existiria só nesta tela. O ciano do mockup **ficou** onde ele é identidade e não ação: o badge do cabeçalho, as iniciais do avatar e o card de cargo escolhido |
| 2026-09-08 | As iniciais continuam sendo **primeira + última** palavra | O mockup mostra "AB" para "Ana Beatriz Souza" (duas primeiras); o app usa o monograma de sempre, nome + sobrenome, e "AS" é o que a linha da lista já mostrava. Trocar mudaria o avatar de toda a tela de Funcionários, e o exemplo escrito no briefing ("Ana Beatriz" → "AB") vale nos dois critérios. É uma linha em `iniciais()` se o Vitor preferir o do mockup |
| 2026-09-08 | `ATENDENTE` → `ENTREGADOR` com **migração de dado** junto | O valor do enum é o que está gravado na coluna. Renomear sem migrar faz o cadastro antigo perder o cargo na primeira edição, calado |
| 2026-09-08 | Situação Ativo/Inativo pelos métodos que já existiam | `criar()` não recebe situação e nunca recebeu. Mudar a assinatura do service por causa de uma pílula seria a UI mandando na camada de dados; `ativar()`/`desativar()` já fazem exatamente isso |
| 2026-09-08 | A máscara de telefone **não mexe** no que não parece telefone | `telefone` é texto livre e sempre foi. Abrir o modal para trocar o cargo de alguém não pode remontar um recado gravado ali como se fosse número — seria o dado reescrito por um caminho que ninguém pediu |
| 2026-09-08 | O ✓ do card de cargo está sempre no layout e só troca de cor | Mostrar e esconder mudaria a largura da linha do título a cada clique, e card que muda de tamanho ao ser escolhido é o que faz o dedo errar o próximo |
| 2026-09-08 | Tokens `pin_icone_*` renomeados para `badge_icone_*` | Terceira vez que o mesmo trio bg/borda/glifo veste uma tela que não é a do PIN. Mesmo critério do `botao_circular_*` no §9.4: o nome é o papel, não a tela |
| 2026-09-08 | "Fechando" **não** entrou na mudança de cor | Continua âmbar. Se os dois estados ficarem vermelhos, param de se distinguir na grade — que é o que a cor existe para fazer |
| 2026-09-08 | O `_QuitarConsumoDialog` continua com a moldura do sistema | Não estava no pedido, e é o modal que pede a Senha Operacional: mexer nele sem paridade própria é mexer num caminho de autorização |

##### Ficou de fora, e por quê

- **As 8 colunas fixas da grade de mesas** (`_COLUNAS_GRADE = 8`) não cabem na
  largura útil do monitor de 1366px: a última coluna fica atrás da barra de
  rolagem horizontal. É anterior a este item e independente da cor — mas
  aparece nas renderizações acima, e por isso fica registrado aqui.
- **O `BuscaProdutoWidget`** e o modal "Adicionar componente" do Cardápio
  continuam como estavam (§9.4).

---

### 9.6 A movimentação manual do caixa em modal único ✅ CONCLUÍDO — 2026-09-08

Pedido do Vitor com dois mockups: a mini-tela de sangria/reforço/despesa
(`_MovimentoDialog`, 30 linhas dentro de `caixa_view.py`) virou um cartão com
teclado numérico na própria tela. O resultado mora em
`ui/widgets/movimentacao_caixa_dialog.py` e é o **quarto** modal em cartão do
app, no mesmo arranjo do PIN, do "Adicionar item" e do "Novo funcionário":
cartão sem moldura, escurecedor atrás, cabeçalho próprio.

#### Uma classe, três operações — o requisito arquitetural do pedido

Sangria, reforço e despesa não são três telas. São a mesma tela — valor,
descrição, confirmar — com ícone, texto e sugestões diferentes. O que separa uma
da outra cabe numa linha, e é essa linha que `OPERACOES` guarda:

```python
Operacao(tipo, papel, titulo, subtitulo, rotulo_confirmar,
         placeholder, tags, glifo, token_tinta, token_glifo)
```

`papel` é a chave que o QSS lê (`[operacao="sangria"]`), e ela chega a
**exatamente dois widgets**: o badge do cabeçalho e o botão que grava. O resto
do cartão é idêntico nas três e é declarado uma vez só — inclusive as teclas do
numpad, o ✕, o Cancelar e o divisor, que já eram famílias compartilhadas com os
outros modais.

`CONSUMO_FUNCIONARIO` fica de fora de propósito, e o construtor levanta
`ValueError` se alguém tentar: `registrar_movimento` recusa esse tipo (consumo
interno já é rastreado como pagamento da comanda, e o movimento manual
descontaria a mesma dívida uma segunda vez). Abrir um cartão sem título e sem
cor para terminar num erro de service seria pior que não abrir.

##### O que a tela de Caixa deixou de repetir

`caixa_view` tinha **três dicionários paralelos** com as mesmas três chaves: o
rótulo do tipo (`_ROTULOS_TIPO_MOVIMENTO`), a chave de estilo do badge da tabela
(`_TIPO_BADGE`) e a variante do botão. "Reforço" precisava estar certo nos três
ao mesmo tempo. Os três passaram a ler `OPERACOES`, e o laço que monta os botões
itera o próprio dicionário — movimentação manual nova entra num lugar só e ganha
botão, modal e badge de uma vez. É o mesmo remédio que o §9.5 aplicou em
`CARGOS`.

#### O visor conta centavos, e é aí que está o ganho

O modal antigo pedia o valor num `QLineEdit`: o operador digitava `"50,00"`,
`"R$ 50"` ou `"50.00"` e `safe_decimal` lia de volta, com `padrao=None` para o
caso de não conseguir — daí o `_ERRO_VALOR` ("Valor inválido. Informe um valor
em reais, como 50,00.") na linha vermelha da tela.

Agora o visor é um `int` de centavos que cresce pela direita, como máquina de
cartão: `5`,`0`,`0`,`0` mostra `R$ 0,05` → `R$ 0,50` → `R$ 5,00` → `R$ 50,00`.
Isso **apaga a classe inteira de defeito**: não existe mais "valor ilegível",
porque nunca houve texto para ler de volta. `safe_decimal` continua existindo e
continua certo — ele resolve o problema de *ler* o que foi digitado, e a
abertura e o fechamento do caixa ganharam numpad no §9.7, e outros campos de
valor do app continuam usando `safe_decimal`.

O teto do visor sai de `dinheiro.LIMITE`, e não de um número escolhido na tela.
A razão é específica: `NUMERIC(10,2)` é o teto das colunas monetárias, e um
valor acima dele faz `registrar_movimento` levantar `ValueError` — que **não
está em `_ERROS_SERVICE`** e subiria como estouro no balcão em vez de virar
mensagem na tela. Amarrando os dois, o numpad não consegue montar esse valor.

#### O que NÃO mudou

**Nenhuma regra financeira, e nenhuma gravação nova.** O diálogo não conhece
`CaixaService`: devolve um `DadosMovimento` (valor + descrição) e a view chama
`registrar_movimento(tipo, valor, descricao)` — mesma assinatura, mesmo tipo,
mesma ordem. Quem exige gerente para sangria e despesa continua sendo o service
(§3.1), quem recusa valor menor ou igual a zero continua sendo o service, e o
erro que ele levantar continua aparecendo na linha de erro da tela de trás. O
`Decimal` passa por `dinheiro()` como todo dinheiro do sistema, e o texto do
visor sai de `formatar_reais` — o mesmo `R$ 1.234,50` da tabela de movimentos e
do relatório de fechamento impresso (§3.8).

O modal não abriu caminho novo para o banco; abriu uma porta melhor para o
caminho que já existia. Os testes provam isso com a `CaixaView` de verdade, o
service de verdade e o banco de verdade — um dublê do diálogo provaria só que o
teste sabe chamar o service.

#### Ciclo de vida (§3.2/§3.9/§3.14, e o RNF do Celeron)

O briefing pediu, no vocabulário do Tkinter, `destroy()` + `unbind()` +
`after_cancel`. Os três equivalentes em PySide6 passam por `done()`, o único
portão por onde saem Confirmar, Cancelar, ✕ e Esc:

* **destroy** — `executar_modal()` faz o `deleteLater()` depois de ler o
  resultado; `done()` acrescenta soltar o escurecedor, que é filho da **janela**
  e não do diálogo;
* **unbind** — o `eventFilter` do campo de descrição é removido explicitamente.
  `QShortcut` não existe: o teclado é lido no `keyPressEvent` do próprio
  diálogo, que morre com ele;
* **after_cancel** — não há timer nenhum, e isso é decisão. O visor é
  recalculado na tecla, não há busca a agrupar e nada é agendado.

E o **oposto** da limpeza, que quase virou defeito: `done()` **não** zera o
valor digitado. No modal de PIN zerar é obrigatório (o segredo tem que sumir da
memória e ninguém o lê de volta); aqui `resultado()` é lido *depois* do
`exec()`, e zerar faria toda sangria ser gravada como R$ 0,00 — sem erro, sem
aviso, com o turno fechando errado no fim da noite. Tem teste próprio.

#### Teclado

`0`-`9` e o numpad USB alimentam o visor, `Backspace` apaga o último dígito,
`Enter` confirma (só com valor maior que zero — o botão nasce desligado),
`Esc` fecha sem gravar e `Tab` alterna entre o visor e o campo de descrição.

O `Tab` precisou dos dois lados. Só existem dois destinos de foco, e um deles é
o próprio diálogo, que tem `FocusPolicy.NoFocus` como todo modal em cartão daqui
— a navegação natural do Qt pularia o diálogo e o `Tab` não faria nada. Então o
`keyPressEvent` manda o foco para o campo e o `eventFilter` do campo o manda de
volta. O anel âmbar do visor é o que diz para onde o próximo dígito vai: com o
cursor na descrição, dígito é texto de descrição — e é assim que tem que ser.

#### Como foi conferido

- **Suíte 1085** (de 1025), **60 testes novos** no arquivo próprio mais um no
  inventário de vazamento de modais. Zero falhas, zero xfail.
- **Os testes que importam foram conferidos desfazendo a correção**, como manda
  o §9.2. Oito mutações, oito reprovações: sem o teto, o dígito extra passa;
  zerando o valor em `done()`, seis testes caem; sem o `removeEventFilter`, o
  `unbind` reprova; com o botão sempre aceso, o portão de R$ 0,00 reprova; com a
  tecla a 120px, o cartão não cabe na tela; sem a propriedade `operacao`, três
  reprovam; com o chip emendando em vez de trocar, um; e desligando a volta do
  `Tab`, um.
- **Renderização nativa** (não `offscreen`) das três operações nos dois temas:
  460×611 para sangria e reforço, 460×644 para despesa, que é a que quebra a
  faixa de chips em duas fileiras por ter quatro sugestões.
- **Ciclo de vida** — 30 aberturas com `exec()` a partir da `CaixaView` não
  deixam diálogo preso; 10 aberturas não deixam escurecedor pendurado na janela.

#### Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-08 | **Uma** classe parametrizada, e não três diálogos | Requisito explícito do pedido, e o certo: o que se copiaria entre três classes não é decoração — é o acumulador de centavos e o ciclo de vida, as duas coisas que quebram em silêncio |
| 2026-09-08 | O botão de sangria é **ciano**, não vermelho | O mockup oferecia os dois. Tirar troco para o malote é rotina de turno, não operação destrutiva: pintar de vermelho o botão que o gerente aperta cinco vezes por noite gasta o único sinal de alerta que a tela tem. O vermelho continua reservado para "Fechar caixa" e para os cancelamentos |
| 2026-09-08 | Cada operação com **família de token própria**, mesmo coincidindo com `perigo`/`sucesso` | O coral da sangria é hoje o mesmo hex de `perigo`, e é justamente por isso que o empréstimo seria perigoso — é a armadilha que o §9.5 desarmou quando a mesa ocupada virou vermelha e arrastou junto o badge de despesa do Caixa. Sangria não é ERRO e reforço não é SUCESSO: são duas direções de dinheiro |
| 2026-09-08 | Tokens `pin_tecla_*` renomeados para `tecla_numerica_*` | Segundo numpad do app, mesmas teclas, mesmos quatro hex. Mesmo critério do `botao_circular_*` (§9.4) e do `badge_icone_*` (§9.5): o nome é o papel, não a tela |
| 2026-09-08 | O erro do service continua sendo mostrado **na tela de trás** | Diferente do "Adicionar item", que trata o erro dentro do modal porque fica aberto para o próximo item. Aqui é um movimento e o modal fecha; mover o tratamento para dentro seria mexer no caminho de autorização (sangria e despesa exigem gerente) sem o pedido ter pedido isso |
| 2026-09-08 | Ícones desenhados à mão, inclusive as setas | O recibo da despesa não existe fora do bloco de emoji, e `↗`/`↙` caem no Segoe UI Emoji: saem coloridos, chapados e ignorando o tema — numa máquina limpa que pode nem ter a fonte. Mesma decisão do cadeado (§PIN), da lupa (§9.4) e do usuário (§9.5) |
| 2026-09-08 | O cartão foi **encolhido** depois da primeira medição | 674px de altura num monitor de 768px é margem curta demais. Visor, espaçamentos e margens cederam 30px; as teclas do numpad **não**, porque alvo de dedo é o que não pode encolher num PDV |
| 2026-09-08 | O visor NÃO é limpo no fechamento | O oposto do modal de PIN, e de propósito: `resultado()` é lido depois do `exec()`, e limpar faria toda sangria ser gravada como R$ 0,00 |

##### Ficou de fora, e por quê

- **A abertura e o fechamento do caixa** continuavam em `_ValorDialog` e
  `_FecharCaixaDialog`, com a moldura do sistema e campos de texto. Não estavam
  no pedido, e o fechamento tem três campos com semântica diferente (dinheiro
  contado, maquininha, observação) — mereciam o próprio mockup, não uma cópia
  deste. Eram eles que ainda justificavam o `_ERRO_VALOR` na view. **Feitos no
  §9.7 (2026-09-09), e com eles o `_ERRO_VALOR` saiu da `caixa_view`.**
- **O `_QuitarConsumoDialog`** e o modal "Adicionar componente" do Cardápio
  continuam como estavam (§9.5, §9.4).

---

### 9.7 A abertura e o fechamento do caixa em cartão com numpad ✅ CONCLUÍDO — 2026-09-09

Pedido do Vitor com dois mockups, e é o item que o §9.6 tinha deixado
explicitamente para trás ("ficou de fora, e por quê"): as duas mini-telas que
abrem e encerram o turno (`_ValorDialog` e `_FecharCaixaDialog`, 60 linhas
dentro de `caixa_view.py`, com a moldura de janela do sistema e campos de
texto) viraram cartões split-screen com teclado numérico na própria tela.
São o **quinto** e o **sexto** modais em cartão do app.

| Antes | Depois |
|---|---|
| `_ValorDialog` — 1 `QLineEdit` num `QFormLayout` | `widgets/abertura_caixa_dialog.py` |
| `_FecharCaixaDialog` — 3 `QLineEdit` num `QFormLayout` | `widgets/fechamento_caixa_dialog.py` |

#### O que saiu para peça compartilhada, e por quê

O §9.6 trouxe o segundo numpad do app e, com ele, o acumulador de centavos.
Este item traria o terceiro e o quarto. **Quatro cópias** do laço
`novo = novo * 10 + dígito` não é repetição de decoração: é repetição da conta
que vira dinheiro gravado — e a suíte já reprova corpo de função duplicado na
camada de UI (`test_paineis_de_relatorio.py`). Saíram dois módulos:

* **`widgets/teclado_numerico.py`** — `AcumuladorDeCentavos` (a regra do visor,
  sem Qt, testável sem tela) e `TecladoNumerico` (a grade 3×4, que só avisa qual
  tecla foi apertada). O modal de movimentação do §9.6 **migrou** para as duas:
  hoje existe uma implementação só do numpad de dinheiro no app, e o token
  `movCaixaTecla` virou `teclaNumerica` pelo mesmo critério de nomear o papel.
* **`widgets/cartao_de_turno.py`** — `CartaoDeTurnoDialog`, a moldura que abrir e
  fechar dividem (cabeçalho, coluna do teclado, rodapé, roteamento de teclado,
  `done()`), mais o `IconeDeGaveta`, que é o **mesmo móvel** nos dois estados:
  gaveta com puxadores na abertura, gaveta com cadeado no fechamento.

O `pin_pad_dialog` ficou de fora **de propósito**: o teclado dele não tem `00`,
tem uma tecla ENTRAR no lugar do apagar e alimenta marcadores de dígito, não um
valor em reais. Forçar as duas coisas na mesma classe custaria mais condicional
do que as vinte linhas que ele tem hoje.

##### Por que uma base, e não uma classe parametrizada como no §9.6

Lá, sangria/reforço/despesa eram a mesma tela com outro rótulo, e **uma** classe
parametrizada era o certo. Aqui não: a abertura tem visor, quatro pílulas e um
cartão de contexto; o fechamento tem duas contagens selecionáveis, uma diferença
que se recalcula a cada tecla e um atalho de preenchimento. Espremer as duas num
`if modo is ...` produziria a classe em que metade dos atributos é `None`
conforme o modo — e num modal que grava dinheiro, "este atributo às vezes
existe" é como um valor sai errado sem ninguém ver. O que elas repetiriam de
verdade (cabeçalho, rodapé, teclado, ciclo de vida) é o que a base entrega
pronto.

#### O visor conta centavos — e o `_ERRO_VALOR` acabou

O modal antigo pedia o valor num `QLineEdit`: o operador digitava `"100,00"`,
`"R$ 100"` ou `"100.00"` e `safe_decimal` lia de volta com `padrao=None`, daí a
linha `_ERRO_VALOR` ("Valor inválido. Informe um valor em reais, como 50,00.")
na tela de trás. Com o numpad **não existe texto para ler de volta**, e com este
item o `_ERRO_VALOR` saiu de `caixa_view.py`: era o último caminho que o
justificava, exatamente como o §9.6 previu. `safe_decimal` continua existindo e
continua certo — ele resolve o problema de *ler* o que foi digitado, e outros
campos do app ainda o usam.

No fechamento, o `padrao=None` daquele campo estava certo pelo motivo que a
própria view documentava: ler "não consegui entender o que ele contou" como "ele
contou zero" inventaria uma diferença do tamanho do turno. O que mudou é que
agora essa leitura não acontece.

#### O fechamento: um destino por vez, e a diferença ao vivo

É a tela mais cara do sistema — o único momento em que a gaveta física e o banco
se encontram. Três decisões:

1. **A diferença aparece enquanto se digita.** Antes, o operador confirmava às
   cegas e descobria a quebra no papel impresso, com o turno já encerrado. Agora
   o cartão se refaz a cada tecla: falta em vermelho, exato em verde
   ("R$ 0,00 · Sem diferença"), sobra em ciano. Sobra é ciano e não verde porque
   sobra é uma **pergunta** ("de onde veio esse dinheiro?"), não um parabéns.
2. **O teclado tem um destino só, e ele é dito em voz alta.** O rótulo da
   direita alterna entre `DIGITANDO DINHEIRO` e `DIGITANDO MAQUININHAS`, e a
   linha ativa fica com o anel ciano aceso. Sem isso, o extrato da maquininha é
   digitado por cima da contagem da gaveta e nada avisa.
3. **A prévia é a mesma conta que o service grava, e há teste provando.** A
   prévia não pode chamar `resumo()` (nada foi gravado ainda), então a igualdade
   não é garantida por código compartilhado: `test_a_previa_da_diferenca_e_a_
   mesma_conta_que_o_service_grava` fecha o caixa de verdade com contagens que
   dão quebra e compara o número que o operador viu com o
   `ResumoCaixa.diferenca_total` que sai do banco.

O atalho **PREENCHER VALORES ESPERADOS** existe porque o turno que fecha
certinho é o caso comum, e obrigar a redigitar dois valores que já estão na tela
convida ao erro. Mas ele é, por construção, o botão que permite fechar o turno
**sem contar a gaveta** — por isso é um botão fantasma, discreto, e não um
caminho em destaque. E ele recusa esperado negativo: o saldo da gaveta fica
negativo quando as sangrias passam do que entrou, e preencher a contagem física
com um número negativo seria afirmar que a gaveta deve dinheiro.

#### A observação da abertura, que é a única mudança de dado

O mockup da abertura pede um campo de observação ("Ex.: fundo recebido do
cofre"). Um campo que o operador preenche e o sistema descarta é pior que campo
nenhum — numa tela que declara dinheiro, é o tipo de coisa que só se descobre
quando alguém procura a anotação e ela nunca existiu. Então entraram, nesta
ordem:

* `Caixa.observacao_abertura` (`String(500)`, nullable), migração
  **`d9b4c7e21f30`**;
* `CaixaService.abrir(..., observacao=None)` — parâmetro opcional, passando pelo
  mesmo `_texto_ou_nulo` da observação de fechamento (`"   "` vira `None`);
* a linha `Obs. abertura:` no relatório de fechamento impresso, logo antes da
  `Obs:` que já saía. É na conferência da gaveta que alguém precisa saber de
  onde veio o fundo declarado — gravar e nunca mostrar seria meio caminho.

**Nenhuma regra financeira mudou por causa disso.** É uma anotação livre: não
entra em conta nenhuma, não muda validação nenhuma, e turno gravado antes da
coluna existir simplesmente tem `NULL` ali.

#### O que NÃO mudou

Os dois diálogos não conhecem `CaixaService`. A abertura devolve
`DadosAbertura` (valor + observação) e o fechamento devolve `DadosFechamento`
(dinheiro + maquininha + observação); a view chama `abrir(...)` e
`fechar(caixa_id, dinheiro, maquininha, observacao)` com a mesma assinatura,
mesmo tipo e mesma ordem de antes. Continuam sendo do service: exigir gerente
(§3.1), recusar valor negativo, barrar o turno anterior esquecido
(`TurnoAnteriorPendenteError`, §3.13), barrar comanda em aberto, numerar o turno
do dia e congelar o mix de vendas. O erro que o service levantar continua
aparecendo na linha vermelha da tela de trás.

A impressão do comprovante também **não** mudou: continua saindo na view, pelo
`executar_impressao` isolado pelo disjuntor (§3.12), **depois** do fechamento —
para que impressora quebrada nunca impeça o caixa de fechar.

#### Ciclo de vida (§3.2/§3.9/§3.14, e o RNF do Celeron)

O briefing pediu, no vocabulário do Tkinter, `destroy()` + `unbind()` +
`after_cancel`. Os três equivalentes em PySide6 passam por `done()`, o único
portão por onde saem Confirmar, Cancelar, ✕ e Esc:

* **destroy** — `executar_modal()` faz o `deleteLater()` depois de ler o
  resultado; `done()` acrescenta soltar o escurecedor (filho da **janela**, não
  do diálogo) e a tabela de teclas do numpad;
* **unbind** — os `eventFilter` dos campos de observação são removidos
  explicitamente. `QShortcut` não existe: o teclado é lido no `keyPressEvent` do
  próprio diálogo, que morre com ele;
* **after_cancel** — não há timer nenhum, e isso é decisão: cada tecla
  recalcula um `Decimal` e repinta rótulos, nada é agendado.

E o **oposto** da limpeza: `done()` **não** zera os valores. Aqui `resultado()`
é lido depois do `exec()`, e limpar faria todo fechamento ser gravado como
R$ 0,00 contados — com uma quebra do tamanho do faturamento da noite. Tem teste
próprio, nos dois modais.

#### Teclado

`0`-`9` e o numpad USB alimentam o destino ativo, `Backspace` apaga, `Enter`
confirma, `Esc` fecha sem gravar e `Tab` percorre os destinos na ordem: na
abertura, valor → observação; no fechamento, dinheiro → maquininha →
observação, e volta. Tocar numa linha de conferência aponta o teclado para ela e
**traz o foco de volta do campo de texto** — se o operador estava na observação
e tocou em "Dinheiro", o dígito seguinte tem que ir para a contagem.

#### Como foi conferido

- **Suíte 1179** (de 1086), **93 testes novos**: 19 do teclado compartilhado, 35
  da abertura, 32 do fechamento, 2 no inventário de vazamento de modais, 3 do
  service e 2 do cupom impresso. Zero falhas, zero xfail.
- **Os testes que importam foram conferidos desfazendo a correção**, como manda
  o §9.2. Doze mutações, **onze reprovações**: sem o teto do banco, o dígito
  extra passa; zerando o valor em `done()`, os dois modais caem; sem o
  `removeEventFilter`, o `unbind` reprova; sem soltar o escurecedor, os dois
  reprovam; com a pílula somando em vez de definir, uma; com o dígito indo
  sempre para a primeira contagem, uma; com a diferença invertida, uma; com as
  duas contagens trocadas na volta para a view, uma; com o `definir` aceitando
  negativo, duas; descartando a observação no service, duas; sem o rótulo
  dinâmico do teclado, uma. A décima segunda (tecla do numpad a 120px) **não**
  reprovou, e está certo não reprovar: com 120px o cartão ainda cabe nos 728px
  úteis. Aferido: a 200px o teste reprova nos dois modais — ele mede a restrição
  real, não a altura da tecla.
- **Bancada visual** (`tools/comparar_telas.py`, 24 renderizações): **as 24
  idênticas byte a byte** ao código anterior. A mudança está contida nos dois
  modais — nenhuma das onze telas mudou um pixel.
- **Renderização nativa** (plataforma `windows`, não `offscreen`): 640×441 para
  a abertura e 640×520 para o fechamento, nos dois temas, bem abaixo dos 728px
  úteis de um monitor de 768px.
- **Migração** `d9b4c7e21f30` aplicada e revertida num banco novo, com
  `PRAGMA table_info` conferindo a coluna nos dois sentidos.
- **Ciclo de vida** — 30 aberturas com `exec()` a partir da `CaixaView` não
  deixam diálogo preso; 10 aberturas não deixam escurecedor pendurado na janela.

#### Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-09 | Base compartilhada, e **não** uma classe parametrizada | O oposto do §9.6, e pelo mesmo raciocínio: lá as três telas eram a mesma; aqui as duas colunas da esquerda não têm nada em comum. Parametrizar produziria a classe com metade dos atributos `None` conforme o modo |
| 2026-09-09 | Numpad e acumulador extraídos, com o §9.6 **migrado** junto | Quatro cópias do acumulador de centavos em quatro telas que gravam dinheiro. Migrar a tela antiga foi mais barato que manter duas implementações — e deixou o app com um numpad de dinheiro só |
| 2026-09-09 | Pílulas da abertura **definem**, as do §9.6 **somam** | O rótulo manda: `+50` soma, `R$ 50` troca. Uma pílula que diz "R$ 100" e produz R$ 150 mente para quem apertou |
| 2026-09-09 | Anel de foco **ciano** nos dois modais novos; o §9.6 segue **âmbar** | Ciano é o que os dois mockups pedem, e é o que os modais em cartão já usam para feedback (o marcador do PIN é o mesmo hex). Trocar a cor do modal de movimentação por simetria não foi pedido — seria decidir pelo Vitor numa tela que ele já validou |
| 2026-09-09 | "Confirmar fechamento" em `#DC2626`, o mesmo Vermelho Ferrari da mesa ocupada | Fechar o caixa é a única ação **destrutiva** desta tela: depois dela o turno vira histórico e não reabre. É onde o vermelho de reconhecer-de-longe (§9.5) deve ser gasto. "Abrir caixa" usa o acento do app, que já é o papel de ação primária |
| 2026-09-09 | Famílias de token próprias (`caixa_abertura_*`, `caixa_fechamento_*`) mesmo coincidindo com hex existentes | `caixa_abertura_tinta` é hoje o mesmo hex de `pilula_ativo_bg` e `caixa_fechamento_tinta` o mesmo de `mov_sangria_tinta`. Coincidem porque a paleta é pequena, não porque signifiquem o mesmo: abrir o caixa não é "estar ativo" e fechar não é uma sangria. É a armadilha que o §9.5 desarmou |
| 2026-09-09 | Contagens começam **zeradas**, e não pré-preenchidas com o esperado | Pré-preencher transformaria a conferência num "Enter" e a gaveta nunca seria contada. Quem quiser o atalho tem o botão fantasma, e ele é uma escolha explícita |
| 2026-09-09 | R$ 0,00 é abertura válida e o botão nasce **aceso** | `abrir` só recusa negativo, e existe turno que começa sem fundo de troco. É a diferença para o §9.6, onde o service recusa zero e o botão nasce desligado |
| 2026-09-09 | Coluna e migração para a observação da abertura | Campo de mockup que o sistema descartasse seria uma anotação perdida numa tela que declara dinheiro. Custou uma coluna nullable e uma linha no cupom |
| 2026-09-09 | A linha de conferência é `QFrame` clicável, não `QPushButton` | Medido: `QPushButton` calcula o `sizeHint` a partir do próprio texto e ignora o layout que se ponha dentro — a linha nascia com 15px e os três rótulos saíam com altura zero. O `QFrame` respeita o layout, ao custo de um único override |
| 2026-09-09 | O `pin_pad_dialog` **não** migrou para o teclado compartilhado | Teclado sem `00`, com ENTRAR no lugar do apagar, alimentando marcadores em vez de um valor. Unificar custaria mais condicional do que as vinte linhas que ele tem |

##### Ficou de fora, e por quê

- **O `_QuitarConsumoDialog`** (Funcionários) e o modal "Adicionar componente"
  do Cardápio continuam como estavam, com campo de texto e `safe_decimal`. Não
  estavam no pedido.
- **O fluxo de senha do fechamento cego** (§3.13) continua mostrando a mensagem
  do service na linha de erro, sem pedir a senha em tela. Mexer nele seria mexer
  no caminho de autorização, que o pedido não pediu.
- **O anel âmbar do modal de movimentação** (§9.6) — ver a tabela de decisões.

---

### 9.8 Sub-modelo: a subdivisão dentro da categoria ✅ CONCLUÍDO — 2026-09-09

Pedido do Vitor. O cardápio real tem **15 categorias e 113 produtos**, e dentro
de "Lanches" convivem coisas que não se parecem: artesanal, podrão, cachorro
quente. A categoria não pode ser quebrada em três — ela é o que decide a
impressora — então o produto ganhou uma segunda etiqueta, **puramente
organizacional**, dentro dela.

#### A regra de ouro, e como ela está trancada

> **O roteamento de impressão continua 100% amarrado à CATEGORIA.** O
> sub-modelo é catálogo, não produção. Nenhuma impressora precisa ser
> reconfigurada, e nenhum vínculo existente muda.

Isso não é uma promessa no texto: é o comportamento que a suíte trava, em três
alturas diferentes.

| Onde | O que prova |
|---|---|
| `test_impressao_service.test_o_submodelo_nao_muda_a_impressora_de_destino` | Três lanches da mesma categoria com sub-modelos diferentes (e um sem nenhum) saem **num cupom só**, na impressora da categoria |
| `test_impressao_service.test_o_roteamento_nao_le_o_submodelo_em_lugar_nenhum` | Varredura de código: a palavra `subcategoria` não pode aparecer no `impressao_service`. Mesma varredura que o §9.5 usou para o ciano emprestado |
| `test_migracao_submodelo.test_o_vinculo_de_impressao_nao_e_tocado` | Depois do upgrade, `categorias.impressora_id` está onde estava |

E, fora da suíte, a bancada: `tools/comparar_cupons.py` gerou os cupons antes e
depois, e os dois arquivos são **idênticos linha a linha** (130 e 49 linhas).

#### O modelo de dados, e por que não é uma tabela

`produtos.subcategoria`, `TEXT NULL`, `String(80)` (o mesmo teto de
`Categoria.nome` — nomeia a mesma coisa, um grupo do cardápio). Migração
`e2c7b4f9a613`, que também cria o índice composto
`idx_produtos_categoria_sub (categoria_id, subcategoria)`.

Uma FK para uma tabela `subcategorias` exigiria CRUD, tela, status, e
tratamento de órfão — para não guardar dado nenhum além do próprio nome.
Sub-modelo não tem impressora, não tem status e não tem regra: ele agrupa. O
preço de ser texto livre é a **divergência de grafia**, e é ela que a próxima
seção resolve.

O índice é composto porque toda leitura de sub-modelo acontece **dentro de uma
categoria**. Medido no banco de verdade, com o cardápio real:

```
EXPLAIN QUERY PLAN
  SELECT DISTINCT subcategoria FROM produtos
   WHERE categoria_id = 1 AND subcategoria IS NOT NULL
  -> SEARCH produtos USING COVERING INDEX idx_produtos_categoria_sub
```

`COVERING INDEX`: a consulta que monta as sugestões do cadastro e as pílulas de
filtro é respondida **sem abrir uma linha de produto**.

#### "podrao" e "Podrão" são o mesmo grupo

O que agrupa dois produtos é a string ser a mesma. As pílulas de sugestão
reduzem a chance de divergência, mas só cobrem quem clica em vez de digitar — e
quem digita "podrao" numa categoria que já tem "Podrão" criaria um **segundo
grupo com o mesmo nome**, que nenhuma tela consegue juntar de volta.

`CardapioService._subcategoria_canonica` fecha isso: a comparação ignora acento,
caixa e espaço repetido, e o valor gravado é **o que a categoria já usava**.
Grafia nova só vale quando não há equivalente ali — aí é sub-modelo novo mesmo,
e manda a digitação. A conferência é por categoria: o mesmo rótulo em duas
categorias são duas etiquetas independentes.

A normalização saiu para `services/texto.py` porque a **busca** precisa da mesma
regra, e as duas camadas não podem responder diferente — o dia em que uma
passasse a ignorar hífen e a outra não, o sub-modelo agrupado numa tela
apareceria separado na outra, sem erro nenhum para explicar. O `_normalizar` do
`busca_produto` passou a ser um apelido do de lá.

#### O que apareceu em cada tela

| Tela | O que ganhou |
|---|---|
| **Cardápio**, cadastro de produto | Campo "Sub-modelo" (opcional, input arredondado sobre `superficie_2`, anel do acento no foco) + faixa de pílulas com os sub-modelos **daquela categoria**. Clicar preenche, clicar de novo limpa, e a pílula acende junto com o campo — inclusive para quem digita à mão |
| **Cardápio**, lista de produtos | Selo discreto ao lado do nome + faixa de filtro (TODOS / cada sub-modelo / SEM SUB-MODELO). A busca passou a casar contra nome **e** sub-modelo |
| **Adicionar item** (lançamento) | O sub-modelo entra na linha de metadados: `LANCHES · PODRÃO`. A busca acha por ele — digitar "artesanal" traz os lanches desse sub-modelo, mesmo sem a palavra estar no nome de nenhum |

**Nada disso aparece enquanto não houver sub-modelo cadastrado**, e isso é
deliberado: a faixa de filtro some quando a categoria não tem nenhum, e o selo
só é criado para quem tem. O cardápio de hoje não tem — e a bancada
`tools/comparar_telas.py` confirma: as **24 telas continuam idênticas byte a
byte** ao código anterior. A funcionalidade é invisível até o Vitor usá-la.

##### O defeito que só a renderização com dado real mostrou

A suíte estava verde, e o selo estava errado. Com o sub-modelo "Cachorro
Quente", ele crescia até o `QLabel` do nome — que corta **sem reticências** — e
"Cachorro Quente Linguiça" aparecia como "Cachorro Quente Lin", sem nada na tela
dizendo que faltava texto. O nome do produto é o dado; o sub-modelo é a dica, e
é a dica que encurta.

A correção teve duas armadilhas, e as duas custaram uma renderização cada:

1. **`QFontMetrics.elidedText` ignora o `letterSpacing`.** Ele devolveu
   `"CACHORRO Q…"` para um teto de 76px, e o texto devolvido ocupava 88px — o
   selo saía com a **primeira** letra cortada, pior que o corte original. O
   encurtamento passou a ser um laço sobre `horizontalAdvance`, que respeita o
   espaçamento;
2. **fonte de QSS vence `setFont`.** Medir com um `QFont()` montado em Python
   media a `Segoe UI`; quem **pinta** é o QSS, com a `Archivo Black` da marca,
   ~20% mais larga na mesma altura de 9px. A solução foi `ensurePolished()` e
   medir a fonte do próprio rótulo: quem pinta e quem mede viraram o mesmo
   objeto, e não há gêmeo para divergir.

O teste que tranca isso precisou de **duas** asserções, e a segunda é a que
importa: cortar demais também cabe no teto. Ele exige que o selo use toda a
largura disponível (devolver uma letra tem que estourar o teto) e roda com a
fonte da marca registrada — sem ela, a plataforma `offscreen` mede outra coisa e
o teste passaria verde sem ter olhado, exatamente como no §9.5.

#### `DadosProduto`: a tupla de seis virou sete, e isso não podia

`_ProdutoDialog.resultado()` devolvia uma tupla desempacotada por **ordem** em
dois lugares. Com o sub-modelo ela iria a sete posições, e `descricao` e
`subcategoria` são ambas `str | None`: trocar as duas passaria pelo
interpretador e gravaria a descrição no lugar do sub-modelo, calado. Virou
`DadosProduto`, no mesmo formato de `DadosFuncionario`, `DadosMovimento` e
`DadosAbertura` — o diálogo devolve dados, a view chama o service.

#### Decisões

| Data | Decisão | Por quê |
|---|---|---|
| 2026-09-09 | Coluna `TEXT NULL` em `produtos`, e não tabela `subcategorias` | Sub-modelo não tem impressora, status nem regra. Uma FK custaria CRUD, tela e órfãos para guardar só um nome |
| 2026-09-09 | Código diz `subcategoria`, tela diz "Sub-modelo" | O nome da coluna veio do pedido do Vitor, escrito em SQL; "Sub-modelo" é a palavra que ele usa para explicar a coisa. Renomear um dos dois seria escolher por ele |
| 2026-09-09 | O service adota a grafia que a categoria já usa | Sugestão de tela só cobre quem clica. É no service que "podrao" e "Podrão" param de virar dois grupos |
| 2026-09-09 | `listar_subcategorias` inclui produto **desativado** | Quem desativou o item de verão ainda organiza o cardápio por ele; a sugestão sumir faria o gerente redigitar — a divergência que ela existe para evitar |
| 2026-09-09 | A faixa de filtro **some** quando a categoria não tem sub-modelo | Faixa vazia permanente é altura gasta numa tela já medida contra os 768px do monitor do food truck (`test_telas_cabem_na_tela.py`) |
| 2026-09-09 | Trocar de categoria **solta** o filtro de sub-modelo | Filtrar Lanches por "Podrão" e clicar em Bebidas deixaria a tabela vazia, com a faixa escondida e nada explicando por que a categoria "não tem produto" |
| 2026-09-09 | Família de token própria (`submodelo_badge_*`), sem cor de marca | A lição do §9.5. COMBO é propriedade de **venda** e o âmbar dele grita de propósito; sub-modelo é organização, e tem que ser o selo mais quieto da linha — ele fica ao lado do nome e não pode competir com ele |
| 2026-09-09 | Separador `·` também entre categoria e sub-modelo | `LANCHES · PODRÃO · COMBO` se lê como um caminho, do grupo maior para o menor. Duas pontuações diferentes numa linha de 9px seriam ruído, não hierarquia |
| 2026-09-09 | **Sem** pílula de sub-modelo no modal "Adicionar item" | O filtro em pílulas de lá é por categoria, que é o eixo da impressora e o que o operador tem na cabeça. Uma segunda fileira custaria altura num cartão medido contra os 728px úteis |
| 2026-09-09 | O `seed.py` **não** classifica nada | O seed pula produto que já existe pelo nome, então classificar lá só valeria para instalação nova — a máquina do Vitor e uma máquina limpa ficariam com cardápios diferentes. A classificação é dele, na tela |
| 2026-09-09 | `ensurePolished()` em vez de fonte gêmea em Python | Ver a armadilha nº 2 acima: gêmeo é coisa que diverge, e aqui a divergência produz reticência no lugar errado |

##### Ficou de fora, e por quê

- **Sub-modelo no cupom da cozinha.** A bobina de 32 colunas é para quem produz
  o item, não para quem organiza o cardápio; mais uma linha de etiqueta
  empurraria o pedido para fora do olhar de quem cozinha. Trancado por
  `test_o_submodelo_nao_aparece_no_cupom_da_cozinha`.
- **Relatórios por sub-modelo.** "Quanto vendeu de Podrão no mês" é uma pergunta
  legítima e não estava no pedido. O dado já está gravado e indexado para quando
  for.
- **O N+1 do `_instantaneo`** (§9.4) continua onde estava: o sub-modelo entrou
  no instantâneo justamente para não reabrir aquele caminho, e a suíte mede que
  a busca por sub-modelo faz **0 consultas** em qualquer estado.

**Suíte: 1241 (de 1179), 62 testes novos**, conferidos com 18 mutações — as 18
reprovam. Bancadas: 24 telas idênticas byte a byte, 2 cupons idênticos linha a
linha. Boot de ponta a ponta num banco novo (migrations + seed, duas vezes): 60
mesas, 15 categorias, 113 produtos, 4 combos, WAL ligado.

---

### 9.9 A subcategoria vira o nível que contém os itens ✅ CONCLUÍDO — 2026-09-09

Pedido do Vitor, com mockup, no mesmo dia do §9.8 e corrigindo-o:

> "a subcategoria não deve ser dentro de um item e sim o inverso, os itens devem
> ser dentro de tal subcategoria, assim ao abrir uma categoria vemos suas
> subdivisões" — e, logo depois: "temos que ter a tela com o design bonito para
> criar as subclasses".

O §9.8 tratou a subcategoria como uma **etiqueta pendurada no produto**: um selo
ao lado do nome, na linha do item. Estava de cabeça para baixo. A subcategoria
**contém** produtos, e é isso que a tela precisava dizer.

#### O que a segunda frase mudou no modelo, e por quê

"Tela para criar as subcategorias" não é um detalhe de UI: é uma mudança de
modelo. Com a coluna de texto do §9.8, uma subcategoria **só existia enquanto
algum produto carregasse a string** — não havia como criar uma vazia esperando
os itens, que é justamente como alguém organiza um cardápio (primeiro os
grupos, depois a classificação). E renomear "Podrão" exigiria varrer e
reescrever todo produto que a carregasse; uma reescrita em massa que falha no
meio deixa metade do cardápio num grupo e metade no outro.

Então ela virou entidade: tabela `subcategorias` (id, nome, categoria_id) e
`produtos.subcategoria_id` no lugar do texto. Migração `f8d1a6c40b27`, que
**converte o dado que existir** antes de derrubar a coluna antiga.

| | §9.8 (texto) | §9.9 (entidade) |
|---|---|---|
| Criar vazia | impossível | é o caso normal |
| Renomear | reescrever N produtos | um `UPDATE` numa linha |
| Excluir | apagar a string de N produtos | `SET NULL`, produtos intactos |
| "Podrão" em duas categorias | duas strings iguais, indistinguíveis | duas linhas, cada uma com a sua categoria |
| Nome quase-igual | canonizado na gravação (calado) | recusado com mensagem |

A canonização do §8 (gravar "Podrão" quando alguém digita "podrao") deixou de
existir e virou **recusa**: com uma tela de cadastro, criar às escondidas uma
coisa com nome diferente do que foi digitado é pior que dizer "já existe". A
comparação continua ignorando acento, caixa e espaço repetido — é a mesma
`chave_de_agrupamento` de `services/texto.py`, agora usada para barrar em vez de
para reescrever.

**Sem `ativo`**, ao contrário de `Categoria`, e de propósito: categoria
desativada some do balcão junto com os produtos dela (é regra de venda);
subcategoria é só organização, e desativar não significaria nada que excluir já
não signifique — e excluir é seguro, porque os produtos voltam a ficar sem
subcategoria (`ondelete="SET NULL"`) sem perder venda nem histórico.

#### A regra de ouro segue trancada

> **O roteamento de impressão continua 100% amarrado à CATEGORIA.**

Nada aqui a afrouxou, e as três provas do §9.8 continuam de pé (com a
`subcategoria_id` no lugar do texto):

| Onde | O que prova |
|---|---|
| `test_a_subcategoria_nao_muda_a_impressora_de_destino` | 3 lanches da mesma categoria, em subcategorias diferentes, saem **num cupom só** |
| `test_o_roteamento_nao_le_a_subcategoria_em_lugar_nenhum` | Varredura: a palavra não pode aparecer no `impressao_service` |
| `test_o_vinculo_de_impressao_nao_e_tocado` (migração) | Depois do upgrade, `categorias.impressora_id` está onde estava |

E a bancada: `tools/comparar_cupons.py` deu os dois cupons **idênticos linha a
linha** contra o commit anterior. O modal de cadastro ainda **diz** a regra em
voz alta — o cartão de contexto mostra `LANCHES · COZINHA`, porque "isso muda
onde meu pedido sai?" é a pergunta que uma tela de subdivisão levanta.

#### A tela

**A árvore** (esquerda) expande a categoria e mostra `Todas`, cada subdivisão e
— quando há item solto — `Sem subcategoria`, com a contagem de cada uma. Uma
categoria aberta por vez: com quinze categorias, deixar todas expandidas
transforma a coluna num rolo, e o gerente organiza uma de cada vez.

**A tabela** (direita) agrupa por subdivisão, com uma linha de cabeçalho por
grupo (`GUARNIÇÕES · 3 ITENS`). Escolher uma subdivisão específica mostra só ela
**sem** cabeçalho — haveria um só, dizendo o que o título da tela já diz.

Duas colunas saíram e uma entrou:

* **o selo da subcategoria na linha do produto** — ele repetia, uma vez por
  item, o que o cabeçalho do grupo diz uma vez, e disputava largura justamente
  com o nome. Todo o cuidado de encurtamento do §9.8 (o laço de
  `horizontalAdvance`, o `ensurePolished`) foi embora com ele. O problema não
  era o selo estar mal feito: era o selo não ser o lugar da informação;
* **a coluna "Tipo"** — existia para a badge COMBO, que aparece em 4 dos 113
  produtos do cardápio real. Ela virou um selo ao lado do nome, e os 90px
  voltaram para a coluna "Produto";
* **o KPI "Preço médio"** deu lugar a **"Subcategorias"**. Média de preço sobre
  um cardápio que vai de R$ 0,50 (chiclete) a R$ 48,00 (dois espetos de picanha)
  não decide nada; quantas subdivisões existem, sim — é o que diz se a
  organização avançou.

**O modal "Nova subcategoria"** (`widgets/subcategoria_dialog.py` — **substituído
no §9.12** por `widgets/organizacao_cardapio_dialog.py`, que atende os dois
níveis) é o **sétimo modal em cartão** do app, e o primeiro que cadastra algo
que antes não existia.
Cartão de contexto com a categoria e a impressora, campo com anel de foco e
contador, as subdivisões que já existem como pílulas **apagadas e não
clicáveis** (elas informam; clicar numa delas só poderia levar a "já existe"), e
a conferência do nome rodando na tecla — o botão desliga antes de o gerente
salvar para receber o erro de volta.

#### Nada cortado — o pedido, e o que estava por trás dele

"não deixa nada ficar cortado, pela falta de espaço" era sobre a coluna de
categorias, e o defeito era anterior à subcategoria: **`setItemWidget` numa
`QListWidget` não dimensiona o item**. A linha de duas alturas (nome +
subtítulo) vinha sendo desenhada dentro da altura de uma, e as duas saíam
cortadas ao meio — em TODAS as quinze categorias, desde que a linha ganhou
subtítulo. A árvore nova dá `sizeHint` explícito a cada item.

Três outros cortes apareceram na renderização com o cardápio real, e os três
estão trancados em teste:

1. **`stretchLastSection` nasce ligado no Qt.** A coluna da contagem tomava
   metade da largura (medido: 146 de 293px) e o nome da subcategoria era
   cortado. Desligá-lo é o que faz o `setSectionResizeMode` valer alguma coisa;
2. **`setFirstColumnSpanned` num item ainda solto não vale** — o span mora no
   modelo da árvore, e um item que ainda não foi adicionado não tem modelo onde
   gravá-lo. Chamado antes do `addTopLevelItem`, era silenciosamente ignorado;
3. **dois botões numa linha de 300px** cortavam o próprio rótulo ("ova categ",
   "Subcategor"). Empilhados, cabem.

##### O `setStyleSheet` que descia para os filhos

Os badges ATIVO/VAZIO e a barra de margem **sumiram** no meio do trabalho: viram
texto solto, sem pílula. A causa é uma regra do Qt que vale a pena registrar:
`setStyleSheet("background: transparent")` num widget **vale para os
descendentes dele**, e vence o QSS global. Enquanto os badges se pintavam
sozinhos (com o próprio `setStyleSheet`), a regra do pai perdia; assim que
passaram a se vestir por `objectName` no QSS global, a regra do pai começou a
ganhar. A correção foi trocar o `setStyleSheet` do embrulho por um
`objectName` (`celulaTransparente`) e declarar a regra no QSS — onde ela para no
seletor em vez de descer pela árvore.

#### O ganho de consulta que o §9.4 tinha deixado registrado

O modal "Adicionar item" monta um instantâneo do cardápio na abertura para a
digitação não tocar o SQLAlchemy. O §9.8 mediu **128 consultas** nessa abertura
(o N+1 do §3.6, uma por categoria de cada produto) e registrou que
`selectinload` as levaria a 2. A subcategoria como relação teria **dobrado** a
conta. Em vez disso, `listar_produtos_para_lancamento()` carrega as duas
relações de uma vez:

```
§9.8   abertura do modal (113 produtos)   128 consultas
§9.9   abertura do modal (113 produtos)     3 consultas
```

Três, e não duas, porque são duas relações: a dos produtos e uma por relação —
independentemente do tamanho do cardápio.

#### Decisões

| Data | Decisão | Por quê |
|---|---|---|
| 2026-09-09 | Subcategoria virou **entidade**, não continuou texto | Uma tela de cadastro exige poder criar uma vazia. Texto no produto só existe enquanto algum produto o carrega |
| 2026-09-09 | Nome quase-igual é **recusado**, não canonizado | O §9.8 gravava "Podrão" quando o gerente digitava "podrao". Com tela de cadastro, criar às escondidas uma coisa com outro nome é pior que dizer "já existe" |
| 2026-09-09 | Sem `ativo` na subcategoria | Categoria desativada some do balcão (regra de venda); subcategoria é organização, e excluir já cobre o caso — os produtos só perdem a etiqueta |
| 2026-09-09 | Excluir a subcategoria **não** apaga os produtos | Excluir uma etiqueta nunca pode apagar o que ela etiquetava. É a diferença para `excluir_categoria`, que é bloqueada com produto dentro |
| 2026-09-09 | Excluir a **categoria** leva as subdivisões junto (`cascade`) | Subcategoria órfã não é alcançável por tela nenhuma: toda navegação entra pela categoria |
| 2026-09-09 | O produto **escolhe** a subcategoria num seletor, não digita | Digitar criaria subdivisão pela porta dos fundos, sem passar pela tela que existe para isso — e é assim que nascem duas com o mesmo nome |
| 2026-09-09 | Trocar a categoria no formulário **zera** a subcategoria escolhida | Nome e preço valem em qualquer categoria; uma subdivisão pertence a UMA. Manter a escolha ofereceria gravar um vínculo que o service recusa |
| 2026-09-09 | O selo da subcategoria saiu da linha do produto | Ele repetia por item o que o cabeçalho do grupo diz uma vez, e disputava largura com o nome |
| 2026-09-09 | A coluna "Tipo" saiu; COMBO virou selo ao lado do nome | Uma coluna de 90px para uma marca que aparece em 4 de 113 produtos |
| 2026-09-09 | "Preço médio" saiu do KPI para "Subcategorias" entrar | Média sobre um cardápio de R$ 0,50 a R$ 48,00 não decide nada |
| 2026-09-09 | Uma categoria expandida por vez | Quinze categorias abertas viram uma coluna de sessenta linhas onde rolar é o trabalho principal |
| 2026-09-09 | `atualizar()` **preserva** a seleção da árvore | Voltar para a primeira categoria a cada item salvo seria a tela largando o trabalho. Mesmo contrato que a tabela já cumpria com `preservar_selecao=True` |
| 2026-09-09 | Faixa de seleção da árvore **sem** cantos arredondados | A linha da subdivisão tem duas colunas, cada uma com o seu retângulo: o arredondamento produzia duas pílulas separadas por uma fresta no meio da faixa |
| 2026-09-09 | Família de token própria (`subcategoria_*`), verde-seco | A lição do §9.5, de novo. Não é o âmbar da marca nem o ciano de dado: "isto é organização" tem cor própria |

##### Ficou de fora, e por quê

- **Mover uma subcategoria de categoria.** Chegou a existir no rascunho e saiu:
  levaria os produtos junto e mudaria a impressora deles — o que é correto (a
  categoria é o eixo), mas é uma regra que o pedido não pediu e que ninguém
  precisou ainda.
- **Subcategoria no cupom da cozinha** e **relatório por subcategoria**, os
  mesmos dois do §9.8, pelos mesmos motivos.
- **A barra lateral do mockup** (Visão Geral, Delivery, Estoque, Fechamento).
  São telas que não existem; o pedido era sobre o Cardápio.
- **O `seed.py` continua não classificando nada.** Ele pula produto que já
  existe pelo nome, então classificar lá deixaria a máquina do food truck e uma
  máquina limpa com cardápios diferentes.

**Suíte: 1284 (de 1225), 59 testes novos**, conferidos com 23 mutações — as 23
reprovam. Bancadas: **22 das 24 telas idênticas byte a byte**, diferindo só as
duas do Cardápio (que é a tela reestruturada), e os **2 cupons idênticos linha a
linha**. Boot de ponta a ponta em banco novo: 60 mesas, 15 categorias, 113
produtos, 4 combos, WAL ligado, e a consulta de subdivisões saindo por
`COVERING INDEX`.

---

### 9.10 O turno-fantasma, a barreira de exclusão e o olho das senhas ✅ CONCLUÍDO — 2026-09-09

Três pedidos do Vitor no mesmo bloco, sendo o primeiro um **defeito relatado**:

> "Ao excluir um operador/turno na aba Funcionários, a exclusão não persiste
> após reiniciar o software (ele ressurge na tela de Login e na lista de
> funcionários). Além disso, a tela de Login sempre seleciona o primeiro item
> da lista por padrão."

---

#### 9.10.1 O turno que voltava — duas causas, nenhuma delas na exclusão

`FuncionarioService.excluir` sempre apagou a linha e sempre deu `commit`. O
defeito estava em dois lugares que nada tinham a ver com a exclusão.

**Causa 1 — o seed repovoava a cada boot.** `main.py` chama `run_seed()` em
**toda** abertura do programa, logo depois das migrações. Cada `seed_*` é
idempotente por nome — `seed_mesas` acrescenta a mesa que falta,
`seed_cardapio` pula o produto cujo nome já existe, `seed_funcionarios_turno`
pula o turno já cadastrado. E **idempotente é o mesmo que restaurador**: o
registro apagado deixa de existir, o seed do boot seguinte não o encontra,
conclui que "falta" e o cria de novo.

Não era só dos turnos. O produto e a categoria excluídos no Cardápio voltavam
pelo mesmo caminho, e a mesa voltaria no dia em que alguma tela apagasse mesa.
Por isso a correção é do `run_seed()` **inteiro**, e não de um `if` dentro de
`seed_funcionarios_turno`.

A marca é uma linha em `preferencias` (tabela nova, chave → valor):
`bootstrap_concluido`. Gravada **no mesmo commit** do povoamento — se a energia
cair no meio, ou o cardápio inteiro está gravado e marcado, ou nada está, e o
boot seguinte refaz do zero, que é o certo para um banco que nunca chegou a
nascer.

> **Por que a marca, e não "só povoa se as tabelas estiverem vazias".** Contar
> linhas é a correção tentadora e traz o defeito de volta inteiro no dia em que
> alguém apagar o último registro de alguma tabela. Trancado em
> `test_a_marca_e_o_que_decide_e_nao_a_contagem_de_linhas`.

**A migração `a4c9f1d70b52` marca o banco que já existe.** Um banco que já
existe já foi povoado — é a definição de já existir. Sem isso, a primeira
abertura depois da atualização rodaria o seed uma última vez e ressuscitaria,
uma última vez, exatamente o que o Vitor apagou.

O sinal de "já povoado" custou a acertar: **`usuarios` não serve**. As migrações
`d3f8a1c4e6b9`, `f4b2c8e1a7d5` e `d23a4f888a77` inserem `Usuario` por conta
própria, e a `f4b2c8e1a7d5` cria os dois operadores de turno em **todo** banco,
inclusive num recém-criado — que portanto chega à migração com dois usuários e
zero mesas. Usá-los como sinal marcaria o bootstrap antes de ele acontecer, e a
instalação nasceria sem as 60 mesas e sem o cardápio. O sinal é `mesas` e
`produtos`, que migração nenhuma toca. Trancado em
`test_os_usuarios_criados_por_migracao_nao_contam_como_povoamento`.

**Causa 2 — o login nunca era excluído.** `Funcionario` e `Usuario` são tabelas
separadas (§3.11) e a tela de Funcionários sempre mexeu só na primeira. Para o
Vitor, "Caixa Turno - Manhã" é **uma** coisa: excluí-lo em Funcionários e
continuar vendo o mesmo nome no dropdown do login é a exclusão que "não pegou".

`excluir` passou a aposentar o login de mesmo nome — o par casado por **nome**, a
mesma convenção que `listar_operadores_caixa` já usava por não haver FK entre as
duas.

O login é **desativado, nunca apagado**: `usuarios.id` é chave estrangeira de
`caixas.aberto_por_id`, `comandas.usuario_id` e `movimentos_caixa.usuario_id`, e
apagar a linha arrancaria o nome de todo turno e toda venda que aquele operador
registrou. Desativar preserva o histórico e some do login, que lista só ativos —
que é exatamente o efeito que se espera de "excluí esse turno".

A trava do último gerente ativo (sem ela ninguém autoriza cancelamento nem abre
caixa, e não há tela de recuperação) é consultada **antes** de qualquer escrita:
descobri-la no meio deixaria o funcionário excluído e o login de pé, que é meia
exclusão. Para isso a regra saiu de dentro de `desativar_usuario` para
`AuthService.motivo_para_nao_desativar`, que **devolve a mensagem em vez de
levantar** — dois chamadores com necessidades opostas.

#### 9.10.2 O dropdown abre no último operador

Antes abria sempre no primeiro item, que é só quem tem o nome mais próximo do
começo do alfabeto (`listar_ativos` ordena por nome). No food truck o mesmo
turno abre o programa dezenas de vezes seguidas, e reescolher o operador a cada
abertura é um passo que só existe para ser esquecido — e esquecer aqui grava a
venda no `aberto_por_id` errado.

`ultimo_operador_id` é a segunda chave de `preferencias`, gravada **depois** de a
autenticação passar (a tela mostra o último que *entrou*, não o último que errou
o PIN). A gravação degrada com `except` largo: se ela falhar, o login já
aconteceu e não pode ser desfeito por causa de uma preferência de tela.

O que se guarda é **só o id**. Quem confere se aquele operador ainda está no
dropdown é a tela, contra a lista que ela mesma carregou — devolver o `Usuario`
daqui faria a tela receber alguém que ela não tem para oferecer.

De quebra, dois consertos na mesma tela:

* o `userData` do combo passou a ser o **id**, e não a instância de `Usuario`:
  o objeto do SQLAlchemy expira a cada `commit` e guardá-lo no widget prende no
  dropdown uma linha do banco que pode já não existir;
* `showEvent` recarrega a lista. É o único momento em que ela pode ter mudado
  sem a tela saber — quem exclui ou desativa um operador faz isso na tela de
  Funcionários, com o login escondido atrás. Sem isso, o dropdown continuaria
  oferecendo, depois do logout, alguém que não existe mais.

#### 9.10.3 Excluir funcionário passa a exigir a Senha Master

Era um `QMessageBox.question` de Sim/Não. `exigir_gerente()` já valia, mas ele é
satisfeito pela **sessão**: quem abriu o turno de manhã e deixou o programa
aberto no balcão autoriza qualquer exclusão que alguém clicar à tarde. Um Sim/Não
em cima disso separa a exclusão de um clique distraído por outro clique — e a
linha some do banco de vez.

`PinPadDialog.para_exclusao` é o terceiro construtor nomeado do modal de PIN, e
usa **Nível 3** (`validar_pin_dono`) — a mesma credencial da Central de Loja, sem
herança de baixo para cima. A Senha Operacional abre o Caixa e não pode apagar
cadastro; está trancado em `test_nenhuma_credencial_abaixo_da_master_confirma`.

O único widget novo do cartão é a faixa com a pergunta por extenso ("Você deseja
confirmar a ação de apagar Caixa Turno - Manhã?"), com família de cor própria
(`pin_exclusao_*`) em vez de `perigo` ou `pill_comanda_perigo_*` emprestados —
mesma lição do §9.5. Título é o que a tela **é**; a mensagem é o que ela está
prestes a **fazer**, e é ela que muda a cada clique.

#### 9.10.4 O olho de "Senhas e Acesso" — e o preço que ele cobra

Pedido: um olho ao lado de cada `Alterar` que, mediante o **CPF do Dono**, mostra
o valor real por alguns segundos.

**Isto contradiz uma regra escrita do §3.13**, e a contradição é o item mais
importante desta seção. `LojaConfig` guardava só hash+salt, e a docstring dizia
que "ver o valor não é uma operação que existe". Hash é via de mão única: para o
olho existir, uma **segunda cópia recuperável** precisa existir.

O que a cópia protege e o que não protege está escrito sem rodeios em
`services/segredo_reversivel.py`:

* **protege** contra leitura casual do banco — abrir o `.db` num navegador de
  SQLite e enxergar a senha do caixa numa coluna. O que sai gravado é ruído em
  Base64, com cifra de fluxo `HMAC-SHA256` e selo `encrypt-then-MAC` (biblioteca
  padrão, nenhuma dependência nova para o `.exe`);
* **não protege** contra quem tem o arquivo do banco **e** o programa. A chave
  mora em `preferencias.chave_de_exibicao`, no mesmo banco, porque tem que estar
  ao alcance do app sozinho — não há servidor, e o backup é uma cópia do `.db`
  (`repository/backup.py`), então uma chave guardada fora dele tornaria todo
  backup restaurado ilegível. É **ofuscação em repouso**, não criptografia
  forte, e a barreira de verdade é o CPF exigido na tela.

Na prática do food truck isso está dimensionado: as senhas são de 4 a 8 dígitos
numéricos, e um ataque offline percorre esse espaço inteiro em segundos contra o
hash — com ou sem a cópia. Quem quiser subir a barra troca o modelo de senha, não
a cifra.

**Nada disso participa de autenticação.** `senha_*_hash` continua sendo a única
coisa contra a qual um PIN digitado é conferido, e `revelar()` devolve texto para
a tela sem abrir porta nenhuma — trancado em `test_revelar_nao_e_autenticacao` e
em `test_a_senha_continua_sendo_conferida_pelo_hash`.

**O backfill confere o hash em vez de chutar** (migração `b6e2d80a3f14`, mesma
técnica de `c1d5b8e37a42`): refaz o hash do padrão de fábrica com o salt gravado
e compara. Bateu, o valor é conhecido e vira cópia; não bateu, a senha foi
trocada, ninguém sabe qual é, e a coluna fica `NULL`. Chutar seria pior que não
preencher — o olho mostraria "26407200" com ar de verdade para um dono que
trocou a senha meses atrás. A tela então diz "altere-a uma vez para poder
visualizá-la", e a próxima troca grava a cópia sozinha. O CPF não tem padrão de
fábrica e fica sem cópia até o primeiro cadastro.

`CpfDonoDialog` é o **oitavo modal em cartão** do app e o segundo que autentica.
Visor com a máscara `•••.•••.•••-••` preenchida da esquerda, `TecladoNumerico`
compartilhado, e o botão só liga com os onze dígitos — "Visualizar" que só pode
dar erro é pior que botão desligado. CPF errado mantém o cartão aberto com aviso,
igual ao modal de PIN. O que ele **não** faz é comparar: entrega os dígitos ao
`revelar` e obedece.

O segredo revelado sai da tela por **quatro** caminhos, todos no mesmo
`ocultar_revelado()`: o timer de 8 segundos, o segundo clique no olho, a troca
daquele segredo e o `hideEvent`. O último não é detalhe — sem ele, uma senha
revelada e deixada em Configurações ficaria acesa atrás de qualquer outra página,
e voltar dentro dos oito segundos a traria de volta à vista sem ninguém digitar
CPF nenhum.

Duas notas de desenho:

* **o ícone é desenhado, não é o emoji `👁`.** É a única coisa aqui que não segue
  o pedido ao pé da letra: `👁` mora no bloco de emoji, cai no Segoe UI Emoji,
  sai colorido e chapado, ignora a paleta — e a máquina limpa do food truck pode
  nem ter a fonte. Mesma decisão já registrada no cadeado do PIN, na lupa do §9.4
  e no ramo do §9.9. O traço mora em `desenhar_olho()` e serve às duas peças
  (`BotaoOlho` e `IconeOlho`), porque duas cópias divergiriam na primeira vez que
  alguém ajustasse a curva;
* **a seção virou `QGridLayout`.** Com quatro `QHBoxLayout` empilhados, layouts
  irmãos não conversam sobre largura, e o botão do CPF ("Cadastrar", mais largo
  que "Alterar") deslocava o olho daquela linha dos outros três. Na grade a
  coluna é a mesma para as quatro e o alinhamento sai sem largura fixa chutada em
  pixel.

#### O que ficou de fora, de propósito

- **Exclusão de produto/categoria no Cardápio não ganhou PIN.** A correção do
  seed já fez a exclusão de lá persistir; a barreira de credencial foi pedida
  para Funcionários, e estender por conta própria mudaria o fluxo de uma tela que
  ninguém pediu para mudar.
- **`revelar` não tem registro de auditoria.** Não existe tabela de log no
  projeto, e criar uma por causa disto seria escopo novo. Fica anotado: se um dia
  importar saber *quando* alguém olhou a Senha Master, é aqui que o gancho entra.
- **O `_AlterarSegredoDialog` continua sendo o formulário antigo** (moldura do
  sistema, `QFormLayout`). Ele é o nono candidato a virar cartão, e o pedido
  desta rodada era o olho, não a troca.

**Suíte: 1418 (de 1290), 128 testes novos**, conferidos com 24 mutações — as 24
reprovam. Bancadas: **22 das 24 telas idênticas byte a byte**, diferindo só as
duas de Configurações (que é a tela que ganhou os olhos), e os **2 cupons
idênticos linha a linha**. Renderização nativa dos cartões novos: 360x487 (PIN de
exclusão) e 400x492 (CPF do Dono), sob os 728px úteis de um monitor de 768px.
Boot de ponta a ponta nos dois cenários que existem no mundo: banco novo (60
mesas, 15 categorias, 113 produtos, WAL ligado, olho funcionando com as senhas de
fábrica) e banco que já rodava (marcado pela migração, sem repovoar, com a
exclusão sobrevivendo a duas reaberturas).

---

### 9.11 O Cardápio em cartões: árvore e blocos pintados ✅ CONCLUÍDO — 2026-09-11

Pedido do Vitor, com dois prints: trocar a listagem tabular do Cardápio (a tela
do §9.9) pela navegação do mockup — árvore/acordeão à esquerda, cartões
agrupados por subcategoria à direita, KPIs elevados no topo — de forma "100%
cirúrgica", com quatro travas escritas: **zero widget fantasma**, **preservação
de estado**, **teto de hardware** e **isolamento de negócio**, e a suíte inteira
verde.

#### A decisão: pintar, e não montar

As duas colunas deixaram de ser feitas de widgets. A árvore montava um
`QWidget` com quatro rótulos por categoria; a tabela, cinco células com widget
próprio por produto. Agora cada linha é um item de modelo carregando um
**instantâneo imutável** (`LinhaDeCategoria`, `LinhaDeSubdivisao`,
`ItemDaLista`), e um `QStyledItemDelegate` pinta só as linhas visíveis
(`widgets/cardapio_cartoes.py`). É a decisão do modal "Adicionar item" (§9.4),
pelo mesmo motivo: widget por linha só se paga quando a linha precisa de um
controle de verdade dentro dela.

O instantâneo não é enfeite. **Todo `commit` expira as instâncias do
SQLAlchemy** (a lição do §9.4), e o Cardápio faz commit a cada produto salvo:
um delegado que lesse `produto.nome` ao pintar iria ao banco a cada repintura —
rolar a lista viraria consulta. A pintura lê o instantâneo, montado na recarga,
e `test_pintar_as_listas_nao_toca_no_banco` conta **zero** comandos SQL numa
repintura feita logo depois de um commit (com o teste de premissa ao lado
provando que ler o `Produto` ali iria ao banco).

Medido com a bancada `medir_cardapio` (cardápio real do seed + as subcategorias
e custos do mockup; o mesmo dado nos dois códigos; `offscreen`, Python 3.14.6 /
PySide6 6.11.2):

| | antes (`4e4be90`) | depois |
|---|---|---|
| RSS: tela montada | +15,4 MB | +14,0 MB |
| RSS: +60 trocas de categoria e 20 recargas | **+37,7 MB** | **+0,7 MB** |
| RSS em 12 voltas pelas 15 categorias | 137,8 → 141,5 MB (subindo) | 117,1 → 117,1 MB (plano) |
| Widgets na tela | 206 → 195 | 72 → 72 |
| Widgets dentro da lista de produtos | 58 | **0** |
| Troca de categoria | 34 ms (máx 85) | **8 ms** (máx 15) |
| `atualizar()` | 41 ms | **12–15 ms** |
| Consultas por troca de categoria | 8 | **3** |
| Consultas por `atualizar()` | 39 | **10** |

Os +37 MB do "antes" **não eram vazamento** — a contagem de widgets ficava
estável. Eram o custo de criar e polir ~58 widgets contra um QSS de 94 KB a cada
troca, e o heap que isso deixa para trás. Sem widget por linha, o custo some.

#### As quatro travas do pedido, uma a uma

**1. Widgets fantasmas.** Não há widget por linha para sobrar, sobrepor ou
esquecer de desconectar — a garantia é de construção, e
`test_nenhuma_linha_das_duas_listas_e_widget` a tranca (viewport das duas listas
sem filho nenhum). O roteiro pedia reaproveitar o `limpar_layout` da Fase 4 no
painel dinâmico: **não há mais painel dinâmico** para limpar. Os widgets que
existem (topo, KPIs, painéis, buscas, rodapé) são montados uma vez e vivem com a
tela; o conteúdo das listas é modelo, e `clear()` destrói os itens de verdade —
objetos C++ sem widget pendurado, com o instantâneo solto junto. Nenhuma conexão
por `lambda` (§3.14), nenhum atalho novo (os três `QShortcut` já existiam),
nenhuma tela escondida criada no boot.

**2. Preservação de estado.** Salvar um produto não solta a seleção, não fecha o
acordeão e não rola nenhuma das duas listas para o topo — cobrado pelo caminho
real do "Editar" em `test_salvar_um_produto_nao_fecha_o_acordeao_nem_rola_para_o_topo`.
A seleção passou a voltar pelo **id do produto**, e não pelo número da linha:
com cabeçalhos de bloco no meio, um produto novo cadastrado antes do escolhido
deslocaria o índice e o próximo "Editar" abriria o vizinho. Criar uma categoria
já a abre selecionada, e o produto recém-cadastrado já sai destacado.

**3. Hardware.** Os números acima. As miniaturas saem do `thumbnail_cache` que
já existia (LRU de 200 entradas), pedidas a 36px e recortadas uma vez só — a
pintura não reescala imagem nenhuma. Sem sombra (`QGraphicsEffect` é pago a cada
repintura; a elevação é uma escada de fundos: página `#0F0F0E` < painel
`#121211` < bloco `#161615` < topo do bloco `#1A1A18`), sem fonte nova (a da
marca), ícones desenhados em `QPainterPath` e guardados por nome.

> **O teto de "~90 MB" do pedido não é alcançável por esta tela sozinha, e
> seria desonesto dizer que foi.** O processo já mede ~100 MB antes de o
> Cardápio existir (Python + PySide6 + SQLAlchemy + Alembic) e ~156 MB com o
> shell inteiro (§7.2). O que a tela controla é o próprio custo (+14 MB
> montada) e o não crescimento (+0,7 MB contra +37,7 MB) — e isso é o que foi
> entregue.

**4. Isolamento de negócio.** A conta de margem e os números do topo saíram da
view para o service: `margem_percentual(preco, custo)` e
`CardapioService.resumo_do_cardapio()` → `ResumoCardapio`, em **três consultas
fixas** (eram 17). A árvore lê as subcategorias numa consulta só
(`listar_todas_as_subcategorias`, eram 15 por recarga — o N+1 do §3.6), e
`test_recarregar_a_tela_nao_cresce_com_o_numero_de_categorias` prova o mesmo
número de consultas com 3 e com 15 categorias. **O roteamento de impressão não
foi tocado**: nenhuma linha do `impressao_service` mudou, e
`tools/comparar_cupons.py` deu os **2 cupons idênticos linha a linha** contra o
commit anterior.

#### O que mudou na tela

- **KPIs**: cartões elevados com insígnia âmbar desenhada, rótulo, número e
  legenda. **"Preço médio" voltou**, com a margem média de legenda — é o quarto
  card do mockup, e o §9.9 o tinha tirado. A legenda de Categorias só diz
  "grupos ativos" quando é verdade; com uma desativada, diz "14 ativos · 1
  desativado".
- **Árvore**: a categoria aberta vira um cartão (seta âmbar, nome, "2
  SUBCATEGORIAS", contador redondo com os produtos), uma guia vertical liga as
  filhas, e a escolhida é uma pílula no `acento` (âmbar no escuro, azul no
  claro). O selo **VAZIO** virou o contador com **0**. Categoria desativada diz
  "DESATIVADA · …" no subtítulo. Numa categoria sem subdivisão, a primeira
  entrada chama-se "Todos os produtos".
- **Direita**: um bloco por subcategoria (insígnia, nome, "3 PRODUTOS",
  "Editar subcategoria") e as linhas de produto (miniatura, nome, preço, custo,
  barra de margem esmeralda, percentual). O topo passou a ser a **categoria**
  (`Acompanhamentos`, `COZINHA · 5 ITENS · 2 SUBCATEGORIAS`) — e por isso, numa
  subdivisão escolhida, o **cabeçalho do bloco agora aparece**: é ele que diz
  qual subdivisão está na tela. Categoria sem subdivisão: um bloco só, sem
  cabeçalho.
- **Saíram**: as **pílulas de filtro** (repetiam a árvore, e filtravam sem mover
  a seleção dela) e a **coluna Status** (o "ATIVO" em toda linha era ruído; a
  exceção virou o selo **DESATIVADO** ao lado do nome, junto do COMBO).
- **Gestos**: duplo clique no produto abre a edição; o link "Editar
  subcategoria" edita a subdivisão **daquele bloco** (em "Todas" há vários);
  a seta do teclado pula cabeçalhos; o tooltip da linha diz preço, custo e
  margem por extenso.
- **Rodapé**: Editar, Desativar e **Excluir em Vermelho Ferrari `#DC2626`** —
  o mesmo da mesa ocupada e do "Fechar caixa". Desligados, os três saem do tom
  aceso (antes o "Editar" parecia clicável e o "Excluir" ficava vermelho sem
  produto escolhido).
- Margem **negativa** (custo acima do preço) sai no vermelho de alerta, com a
  barra vazia.

#### O que a tela antiga mostrava errado, e morreu pelo caminho

A renderização de base (`4e4be90`, antes de qualquer mudança) já mostrava três
defeitos, e os três deixaram de ter onde acontecer:

1. os rótulos dos KPIs pintavam um **retângulo escuro atrás do texto** — a regra
   global `QWidget { background }` vale para `QLabel`, e os rótulos antigos não
   declaravam fundo transparente;
2. o recuo da árvore acendia uma **faixa azul do sistema** ao lado de "Todas" —
   o estilo pinta a área de `::branch` com o azul de seleção; agora o recuo é
   zero e a guia é do delegado;
3. a seta da categoria aberta (`⌄`) saía como um **quadradinho** — o glifo não
   existe na fonte da marca; agora é desenhado.

#### Achados no caminho — cada um com teste

1. **Renomear a subcategoria escolhida levava o gerente para a primeira
   categoria** (anterior ao §9.11). A recarga procurava a subdivisão pelo nome
   antigo, não achava e caía no primeiro item da árvore — renomear fechava o
   acordeão em que ele trabalhava. A chave da seleção agora é trocada junto.
2. **O `QColor` não entende `rgba()` do CSS** — metade da paleta "Concreto".
   `QColor("rgba(255, 255, 255, 0.08)")` devolve uma cor inválida que pinta
   como **preto opaco**, sem erro. O placeholder das miniaturas pintava a borda
   de preto no tema escuro desde que a paleta trocou os hex por transparências.
   `ui/theme/cores.py::cor_do_token` entende as duas grafias, e um teste varre
   as duas paletas inteiras. É a única diferença fora do Cardápio na bancada
   (660 px na Comanda e 376 px no Dashboard, só no escuro) — ampliada e
   conferida: o contorno preto virou o contorno claro sutil que o token sempre
   descreveu.
3. **A busca da árvore casava pelas entradas fixas** (anterior): "Todas" e "Sem
   subcategoria" existem em quase toda categoria, e buscar "sub" trazia o
   cardápio inteiro.
4. **Duplo clique numa categoria a fechava de novo**: o clique simples já abre,
   e o `expandsOnDoubleClick` do Qt alternava o ramo em seguida.
5. **Linha estreita**: tirar o custo não bastava para o nome continuar legível
   — entrou o segundo degrau (a barra sai também, o percentual fica). Achado
   pelo próprio teste novo, com a fonte do `offscreen`, que mede mais largo.
6. **O `test_caos.py` pegou dois overrides sem `@nao_deixa_escapar`** no
   rótulo com reticências — a trava do §4 do `Mitigação de Falhas.md`
   funcionando como deveria.
7. **O `QTest.mouseDClick` do Qt 6 manda só o evento de duplo clique**, sem o
   clique que o sistema operacional sempre manda antes — e a lista do Qt só
   anuncia duplo clique no item que recebeu o clique anterior. O teste reprovava
   um código certo; o auxiliar `_duplo_clique` reproduz a sequência real.

#### O `PainelPontilhado` desenha só a região suja

Os dois painéis ganharam a textura de pontos do mockup (a mesma da sidebar e do
login), e as listas têm fundo transparente para ela aparecer entre os blocos —
então passar o mouse por uma linha repinta também o pedaço de painel atrás
dela. O painel percorria os ~600 pontos a cada repintura; agora percorre só os
da região que o Qt mandou repintar. Pixel a pixel igual: login e sidebar saíram
**idênticos byte a byte** na bancada, e `test_painel_pontilhado.py` compara a
repintura de cada pedaço com a do painel inteiro (inclusive com raio fracionário,
que é onde a folga do raio na conta inversa deixa de ser inerte).

#### Como foi conferido

- **Suíte: 1495 (de 1426), 0 falhas**, nenhum teste apagado sem substituto. Os testes que liam a
  tabela por dentro (`tabela`, `cellWidget`, `itemWidget`, pílulas) foram
  portados para ler o mesmo dado pelo instantâneo — a asserção de comportamento
  de cada um é a mesma, e as três que mudaram de propósito (cabeçalho na
  subdivisão escolhida, pílulas, VAZIO → 0) estão ditas no docstring do arquivo.
- **Mutações: 24, e 23 reprovam.** A sobrevivente é declarada: o
  `doItemsLayout()` antes de devolver a rolagem da lista. Medido — nesta lista o
  alcance da barra sobrevive ao `clear()` (1359 antes e depois); numa lista solta
  do mesmo Qt ele caiu e cortou a rolagem (452 de 1052px). A linha ficou como
  defensiva, porque é o mesmo cálculo que o Qt faria antes de pintar, e o
  comentário dela diz isso em vez de fingir que um teste a prova. Três mutações
  sobreviveram na primeira rodada por defeito do TESTE, e os três foram
  corrigidos: números de margem que coincidiam nas duas contas (80% e 80%),
  regiões de pontilhado que não caíam onde a folga importa, e um duplo clique
  em categoria abaixo da aberta (onde as linhas mudam de lugar entre os dois
  cliques e o defeito não aparece).
- **Bancadas**: **20 das 24 telas idênticas byte a byte** nos dois tamanhos
  (1280x800 e 1366x738), diferindo as duas do Cardápio (a tela refeita) e as
  duas do achado 2 acima; **2 cupons idênticos linha a linha**.
- Renderização com o cardápio real + subcategorias, nos dois temas e nos dois
  tamanhos, conferida contra o mockup.

#### Decisões

| Data | Decisão | Por quê |
|---|---|---|
| 2026-09-11 | As duas listas são **pintadas por delegado**, sem widget por linha | Precedente do §9.4; −37 MB de crescimento, troca de categoria de 34 para 8 ms, e widget fantasma deixa de ser possível |
| 2026-09-11 | A pintura lê um **instantâneo**, nunca o `Produto` | O commit expira as instâncias; pintar o ORM seria consulta a cada repintura |
| 2026-09-11 | A seleção volta pelo **id**, não pela linha | Com cabeçalhos no meio, um produto novo antes do escolhido deslocaria o índice |
| 2026-09-11 | Margem e resumo do topo foram para o **service** | Regra de negócio fora da view, e a barra e a média saem da mesma conta |
| 2026-09-11 | "Preço médio" **voltou** ao topo, com a margem de legenda | É o card do mockup do Vitor; a margem, que decide, continua na tela |
| 2026-09-11 | O cabeçalho do bloco **aparece** também na subdivisão escolhida | O topo virou a categoria; sem o cabeçalho, nada diria qual subdivisão está na tela. Reverte o "sem cabeçalho" do §9.9 |
| 2026-09-11 | As pílulas de filtro **saíram** | Repetiam a árvore, e filtravam sem mover a seleção dela |
| 2026-09-11 | **Ativar/Desativar ficou** no rodapé, embora o mockup mostre só Editar e Excluir | É o gesto de todo dia do food truck ("acabou o pão"); tirá-lo deixaria desativar produto sem caminho na tela |
| 2026-09-11 | Excluir em `#DC2626`, com família de token própria (`cardapio_excluir_*`) | O pedido nomeou a cor; família própria pela lição do §9.5 |
| 2026-09-11 | A insígnia continua **âmbar** no tema claro (pastel com glifo escuro) | É a cor do catálogo, não o `acento` (que no claro é azul); arranjo do claro do §9.6 |
| 2026-09-11 | Números na fonte da marca, e não na monoespaçada do mockup | O alinhamento vem do alinhamento à direita; uma segunda família tipográfica seria decisão de identidade, não de tela |
| 2026-09-11 | `cor_do_token` para todo token pintado com `QPainter` | O `QColor` não entende `rgba()`, e metade da paleta está nessa grafia |
| 2026-09-11 | Uma categoria aberta por vez; o clique **não** fecha a aberta | Mantém a regra do §9.9 — a seleção mora na categoria aberta, e fechá-la deixaria a direita mostrando uma categoria escondida |

#### Ficou de fora, e por quê

- **A barra lateral do mockup** (Visão Geral, Delivery, Estoque, Fechamento) e o
  "GERENTE · VITOR RAPHAEL" do topo: são do shell, não do Cardápio — mesma
  decisão do §9.9.
- **A lupa do modal "Adicionar item" não foi unificada** com o sistema de glifos
  novo: mudaria pixels de um modal já validado, e o pedido era o Cardápio.
- **Mover subcategoria de categoria**, subcategoria no cupom e relatório por
  subcategoria continuam fora, pelos motivos do §9.9.

---

### 9.12 Categoria e subcategoria num cartão só ✅ CONCLUÍDO — 2026-09-12

Pedido do Vitor, com dois mockups (Nova categoria e Nova subcategoria) e uma
exigência escrita acima do desenho: **DRY**. "Observe que os dois modais
compartilham 95% da mesma estrutura visual. Implemente um único componente base
reutilizável e parametrizável que receba os parâmetros de contexto (Categoria
Raiz vs. Subcategoria de uma Categoria Pai) em vez de duplicar classes
inteiras." Junto vieram o ciclo de vida limpo (descarte dos widgets, `unbind`
dos atalhos, desconexão dos ouvintes de texto), o teto de hardware do Celeron e
a ordem de não encostar em regra de negócio nem no `WAL`.

#### O que havia antes

Duas telas para a mesma pergunta — "que nome tem este grupo?":

* `_CategoriaDialog`, 20 linhas dentro de `cardapio_view.py`: moldura do
  sistema, `QFormLayout`, `QDialogButtonBox` de fábrica. Era a última janela do
  Cardápio que ainda parecia formulário de 2005, e a única do fluxo sem
  contador, sem aviso de nome repetido e sem `Esc` documentado;
* `SubcategoriaDialog` (§9.9), já em cartão, mas anterior ao mockup — e com uma
  cópia inteira de cabeçalho, campo com anel de foco, contador, rodapé e
  limpeza. Eram exatamente as cinco peças que a categoria teria de copiar para
  ficar parecida com ela.

#### A decisão: uma classe parametrizada, não duas irmãs

`widgets/organizacao_cardapio_dialog.py` é **um** `QDialog`
(`OrganizacaoCardapioDialog`) com dois papéis. O que separa um do outro mora em
`PAPEIS`, uma linha por papel: o glifo do cabeçalho, o rótulo do campo, o
*placeholder*, o destino padrão, a função que decide se o nome já existe e as
seis frases de cada modo (criar/renomear). É a forma do §9.6 (`OPERACOES`, a
movimentação de caixa), pelo mesmo motivo: a tela é a mesma tela com outras
palavras dentro.

**Não** é base + subclasses, a forma do §9.7: lá as duas colunas da esquerda não
tinham nada em comum e parametrizar produziria uma classe com metade dos
atributos `None`. Aqui é o oposto — o que muda cabe numa `dataclass` de sete
campos, e um `if nivel is CATEGORIA` no meio da montagem é justamente como duas
telas voltam a existir sem ninguém ter decidido isso.

Quem chama usa os construtores nomeados (`para_categoria`, `para_subcategoria`),
a convenção do `PinPadDialog` do §9.10: a view diz **o que** quer cadastrar, não
como o cartão se veste.

#### O achado: as duas regras de nome repetido são diferentes

O que mais fácil sairia errado num modal compartilhado é a única coisa que os
dois níveis fazem de formas diferentes no service:

| | regra do service | o que o cartão compara |
|---|---|---|
| Categoria | `Categoria.nome == nome` — **exato** | o nome aparado, exato |
| Subcategoria | `chave_de_agrupamento` — ignora acento, caixa e espaço repetido | a mesma `chave_de_agrupamento` |

Espelhar a regra de cada nível (o campo `normalizar` do papel) é o que impede a
tela de **mentir**. Um "✕ Nome já existente" ao digitar `lanches` com `Lanches`
cadastrada seria um botão desligado por uma regra que o service não tem, e o
gerente ficaria sem saber por que não consegue salvar. Os dois testes ficam lado
a lado no arquivo, um afirmando o que o outro nega, com o porquê escrito em
cada um: se um dia a categoria passar a comparar como a subcategoria, é o
segundo que reprova — e o conserto é **uma linha em `PAPEIS`**, não uma tela
nova.

Fica registrado que a assimetria é do service e não desta tela: duas categorias
`Lanches` e `lanches` continuam possíveis no banco, como sempre foram. Mudar
isso é regra de negócio, o pedido dizia para não mexer, e nada aqui mexeu.

#### O ciclo de vida, item a item do pedido

* **descarte dos widgets** — `executar_modal()`/`descartar_modal()` (§3.2)
  continuam sendo quem destrói, **depois** de `resultado()` ser lido;
  `WA_DeleteOnClose` segue fora, porque `done()` faz `hide()` e não `close()`.
  Os filhos morrem com o cartão; o único widget que não é filho dele é o
  escurecedor, filho da JANELA, e é por isso que `done()` existe aqui;
* **`unbind` de atalhos** — não há nenhum a soltar, e isso é uma decisão: quem
  lê o teclado é o `keyPressEvent` do diálogo. Um `QShortcut` de aplicação
  sobreviveria ao cartão, e é exatamente o vazamento que o pedido descreve;
* **desconexão dos ouvintes de texto** — `_soltar_recursos()` tira o filtro de
  eventos do campo e desconecta as três ligações nominalmente, com a trava
  `_limpo` para a segunda passagem. Elas morreriam com os filhos de qualquer
  forma; explicitá-las é o que impede que uma quarta ligação, a um objeto de
  **fora** do cartão, entre um dia sem ninguém notar que aquela, sim,
  sobreviveria ao fechamento.

A trava `_limpo` rendeu uma correção de teste que vale registrar. A primeira
versão dizia que o segundo `disconnect` levanta `RuntimeError` — **não levanta**
nesta versão do PySide6: devolve `False` e imprime
`RuntimeWarning: libpyside: Failed to disconnect`. O teste escrito contra a
exceção passava verde com a trava apagada (a mutação mostrou), e ainda era
enganado duas vezes: `done()` carrega o `@nao_deixa_escapar`, que engoliria a
exceção de qualquer jeito. Ele passou a medir o **aviso**, chamando
`_soltar_recursos()` na mão.

#### O que o mockup pediu e a fonte da marca não deixou

A largura. O pedido escrito dizia "entre 460px e 500px"; o cartão das duas
imagens tem **576px**, e é dele que sai o rodapé de uma linha do desenho
(atalhos à esquerda, os dois botões à direita). Medido a 480px com a fonte do
app — Archivo Black, ~20% mais larga que a do mockup — o rodapé pede 570px e o
Qt espreme o que não cabe: `+ Criar subcategoria` saía como `Criar subcategol` e
`ENTER PARA CRIAR · ESC PARA FECHAR` virava `ENTER PARA CRIAR · ES`. Um rodapé
que corta a própria instrução de teclado.

O cartão ficou nos 576px do mockup, a linha de atalhos caiu para 9px com metade
do espaçamento, e a folga no pior caso é de 6px — pequena demais para depender
de quem vier depois lembrar dela. Está trancada em
`test_o_rodape_cabe_no_cartao`, que mede `width() < sizeHint().width()` de cada
peça nos dois níveis e nos dois modos, com a fonte da marca registrada na
fixture. Sem essa fixture o teste passaria verde sem ter olhado: a plataforma
`offscreen` sobe sem banco de fontes e ali o aperto não acontece — a mesma
armadilha do card de mesa do §9.5.

#### O resto do desenho

Nenhum token novo. O tema escuro da paleta "Concreto" **já é** o do mockup
(`superficie` `#161615`, `borda` `rgba(255,255,255,0.08)`, `texto_fraco`
`#A1A1AA`, `texto_fraquissimo` `#71717A`, `acento` `#E5A93C`, `sucesso`
`#4ADE80`), e o resto veio das famílias que o Cardápio já tinha
(`cardapio_icone_*` para a insígnia âmbar, `cardapio_painel_bg` para as
superfícies recuadas, `subcategoria_grupo_*` para o selo da impressora). Por
isso o cartão nasce correto no tema claro também, sem uma segunda paleta para
divergir.

* os **glifos** entraram no sistema de `cardapio_cartoes.py`
  (`GLIFO_PASTA_MAIS`, `GLIFO_RAMO`), na mesma grade de 24 dos outros — o
  `_IconeDeRamo`, que o §9.9 desenhava à mão dentro do modal, deixou de existir;
* o **corpo do cartão é um `PainelPontilhado`**, a textura do login, da barra
  lateral e dos dois painéis do Cardápio: é o que as imagens mostram atrás do
  formulário, e custa um `paintEvent` com ~30 pontos na região suja;
* o **cartão de contexto** responde "onde isto vai nascer" antes de qualquer
  digitação: `SERÁ CRIADA EM · Raiz do cardápio` ou `SERÁ CRIADA DENTRO DE ·
  <categoria>`;
* a **linha de validação** tem dois papéis fixos: à esquerda a ajuda (ou o erro
  do service, que é frase inteira e precisa da largura), à direita o veredito
  curto — `✓ Nome válido` / `✕ Nome já existente`. `✓` e `✕` e não `✅`/`❌`,
  pela armadilha do emoji já paga no cadeado do PIN e no olho das senhas;
* o **teto do campo** caiu de 80 (a coluna do banco) para os 60 do mockup, com
  uma ressalva: `setMaxLength` **apara o texto que já está no campo**, então
  abrir a edição de um nome mais longo que o teto e devolvê-lo cortado seria
  perder dado calado. O teto do campo é `max(60, len(nome_atual))`.

#### O que mudou na view, além da troca de modal

Criar e editar **categoria** passaram para o `while modal.exec()` que a
subcategoria já usava desde o §9.9: quando o service recusa, o cartão reabre com
o que foi digitado e a mensagem dentro dele. Antes o erro saía na linha vermelha
da tela de trás, com o cartão já fechado e o texto perdido — e essa linha é
justamente onde o gerente **não** está olhando. São os dois sites novos que
levam `test_o_modal_reaproveitado_no_while_e_descartado_fora_do_laco` de 4 para
6; o total de 36 sites de modal não mudou.

#### Como foi conferido

* **suíte 1530** (de 1495), 0 falhas. 55 testes novos no cartão + 1 na tela;
  os 22 da suíte antiga da subcategoria foram absorvidos e reescritos para rodar
  **nos dois níveis**;
* **19 mutações, as 19 reprovam** — entre elas: trocar a regra de duplicidade de
  um nível pela do outro (nas duas direções), apagar o selo da impressora,
  deixar `setMaxLength` cortar o nome existente, tirar a trava de limpeza dupla,
  deixar o `Enter` passar por cima do botão desligado, não desconectar o
  `textChanged`, não soltar o escurecedor, encolher o cartão para 480px e fazer
  `editar_categoria` não chamar o service;
* **bancada visual**: as **24 telas idênticas byte a byte** ao commit anterior,
  nos dois temas — o cartão é modal e não entra em nenhuma delas, e o QSS novo
  não encosta em widget de tela;
* **bancada de cupons**: os 2 cupons idênticos linha a linha. Roteamento de
  impressão intocado, como o pedido exigia;
* renderização nativa do cartão nos dois níveis, nos dois modos e nos dois
  temas: **576x374**, muito abaixo dos 728px úteis de um monitor de 768px.

#### Decisões

| Data | Decisão | Por quê |
|---|---|---|
| 2026-09-12 | **Uma classe parametrizada** por `NivelDoCardapio`, com `PAPEIS` | O pedido (DRY) e o precedente do §9.6; o que difere cabe em sete campos |
| 2026-09-12 | Construtores nomeados `para_categoria`/`para_subcategoria` | Convenção do `PinPadDialog` (§9.10): a view diz o que cadastra, não como o cartão se veste |
| 2026-09-12 | Cada nível compara duplicidade com **a regra do próprio service** | Uma regra só faria a tela mentir num dos dois lados |
| 2026-09-12 | O `SubcategoriaDialog` foi **apagado**, não mantido ao lado | Mantê-lo seria a duplicação que o pedido mandou eliminar |
| 2026-09-12 | O selo da **impressora** continua no cartão de contexto, fora do mockup | É a regra de ouro do §9.8 dita em voz alta; some na raiz, onde não há bobina a citar |
| 2026-09-12 | Cartão com **576px**, e não os 460–500 do texto do pedido | É a largura das próprias imagens; abaixo disso o rodapé de uma linha corta os próprios rótulos com a fonte da marca |
| 2026-09-12 | Mínimo de **2 letras** para ligar o botão | O mockup pede; o service só recusa vazio, e está escrito nos dois lugares que é trava de tela |
| 2026-09-12 | Teto do campo `max(60, len(nome_atual))` | `setMaxLength` apara o texto existente, e perder dado calado é pior que um contador passando de 60 |
| 2026-09-12 | Criar/editar categoria passaram ao `while modal.exec()` | O erro do service passa a aparecer dentro do cartão, sem redigitar |

#### Ficou de fora, e por quê

- **A assimetria das duas regras de duplicidade** não foi corrigida no service:
  `Lanches` e `lanches` continuam podendo coexistir como categorias. É regra de
  negócio, e o pedido dizia para não mexer. Fica anotado como candidato — a
  correção seria um `_exigir_nome_de_categoria_livre` comparando pela
  `chave_de_agrupamento`, com o mesmo `PAPEIS` acompanhando numa linha.
- **As pílulas "já existem nesta categoria"** do §9.9 saíram: não estão no
  mockup, e a linha de validação faz o trabalho que elas faziam — avisar do
  quase-igual antes de salvar — sem gastar duas fileiras do cartão.
- **A exclusão** de categoria e de subcategoria continua no `QMessageBox` do
  sistema. O pedido era sobre as janelas de **criação**; refazer a confirmação
  destrutiva no mesmo desenho é item próprio.
- **`_ProdutoDialog`, `_ComponenteDialog` e `_ComboComponentesDialog`** seguem
  sendo formulários de fábrica dentro do `cardapio_view.py`. São os três últimos
  do Cardápio, e o `_ProdutoDialog` é bem maior que estes dois cartões.

---

### 9.13 O rodapé do Cardápio passa a agir sobre o que está selecionado ✅ CONCLUÍDO — 2026-09-12

Pedido do Vitor, com a tela aberta em "Combo pastel (0)" e os três botões do
rodapé apagados: `Editar`, `Desativar` e `Excluir` estavam presos ao produto, e
uma subcategoria vazia — que é **exatamente o estado de quem acabou de criá-la**
— não tinha como ser editada, desativada nem excluída por ali. O pedido pediu
que os três virassem *context-aware*: agir sobre a categoria, a subcategoria ou
o produto selecionado, com o rótulo à esquerda dizendo sobre qual deles.

Duas decisões vieram do próprio Vitor, em resposta a perguntas feitas antes de
começar, e as duas **revertem decisões escritas do §9.9**. Ficam registradas
aqui com o nome de quem decidiu, porque quem ler o §9.9 daqui a seis meses vai
achar que esta seção o contradiz — e vai estar certo.

#### O que havia antes

* três botões de produto. Sem produto escolhido, os três desligados, e o rótulo
  dizia "SELECIONE UM PRODUTO PARA EDITAR";
* editar/ativar/excluir **categoria** só existiam no menu de contexto (botão
  direito na árvore): invisíveis para quem não clica com o botão direito;
* editar/excluir **subcategoria**, idem — mais o link "Editar subcategoria" no
  cabeçalho do bloco, que era o único caminho visível, e só para renomear;
* `F2` editava a CATEGORIA mesmo com uma subdivisão destacada: o teclado fazia
  uma coisa e o menu de contexto do mesmo item fazia outra.

#### A máquina de estados

`_ProdutosPainel.alvo_atual()` devolve um `AlvoDaAcao` (tipo, nome, ativo), e
`_atualizar_barra_acoes()` redesenha o rodapé inteiro a partir dele — rótulo,
os três `setEnabled`, a palavra do botão do meio e a cor dele. **Um lugar só**,
chamado de todo caminho que possa mudar o alvo (recarga, clique na lista,
clique na árvore, busca): espalhar `setEnabled` pelos chamadores é como o
rodapé fica dizendo "Desativar" sobre algo que já está desativado.

A precedência é a do gesto mais específico — produto > subcategoria > categoria
> nada — e ela **não produz ambiguidade** porque mover a árvore solta o produto
(trocar de subdivisão recarrega a lista sem seleção). "Produto escolhido" só
existe depois de um clique deliberado numa linha.

| alvo | rótulo | o que os botões pegam |
|---|---|---|
| produto | `PRODUTO: X TUDO` | o produto (comportamento de antes) |
| subcategoria | `SUBCATEGORIA: COMBO PASTEL` | a subdivisão, vazia ou não |
| categoria | `CATEGORIA: LANCHES` | a categoria |
| nada | `SELECIONE UMA CATEGORIA, SUBCATEGORIA OU PRODUTO` | nada, os três apagados |

O rótulo troca de tom por **propriedade dinâmica** (`estado="alvo"`), não por
`setStyleSheet`: cor congelada em folha local não acompanha o alternador
Claro/Escuro (§3.15). O pedido dizia `#FFFFFF`; o que entrou foi o token
`texto`, que **é** `#FFFFFF` no tema Escuro e um tom legível no Claro — um
branco cravado sumiria com a linha inteira no tema Claro. Mesma coisa com o
verde `#4ADE80` do botão "Ativar": entrou como `pilula_ativo_texto`, os mesmos
dois tokens da pílula Ativo do modal de funcionário.

#### Uma porta de entrada só por ação

`_CategoriasPainel` ganhou três despachantes — `editar_selecionado()`,
`alternar_status_selecionado()`, `excluir_selecionado()` — que olham a seleção
da árvore e chamam a rotina do nível certo. O botão do rodapé, o item do menu
de contexto e o atalho de teclado passam **todos** por eles. Sem isso, "Excluir"
no rodapé e "Excluir subcategoria" no menu seriam dois caminhos que começam
iguais e divergem no dia em que um dos dois ganhar uma barreira a mais — que é
precisamente o que aconteceu neste item.

O rodapé mora no painel da DIREITA e o alvo mora na árvore da ESQUERDA, então a
direita emite três sinais sem argumento (`editar_estrutura_pedida` e irmãos) e
a `CardapioView` os liga aos despachantes. Sem argumento de propósito: mandar o
nome junto criaria uma segunda fonte de verdade sobre "onde estou".

Pela mesma razão, **clicar no cabeçalho de um bloco (ou no aviso de bloco
vazio) move a seleção da ÁRVORE**, em vez de a direita guardar um contexto
próprio. É o que faz o pedido da "seção vazia" funcionar: o bloco de uma
subdivisão sem produto nenhum não tem linha para clicar, e antes era
inalcançável pela direita. O link "Editar subcategoria" continua tendo
precedência dentro do cabeçalho — ele é conferido antes, senão viraria um
clique de seleção — e dispara **a mesma rotina** do botão `Editar` do rodapé
(trancado em teste).

#### Decisão 1 do Vitor: desativar subcategoria é regra de VENDA

O §9.9 escreveu que subcategoria não teria `ativo` porque "desativar não
significaria nada que excluir já não signifique". O Vitor escolheu o contrário:
a subdivisão desativada **tira os produtos dela do balcão**, igual à categoria,
um nível abaixo. É o gesto de "hoje não tem podrão" sem desativar item por item
— e sem ter que lembrar quais eram para reativar depois.

Coluna `subcategorias.ativo` (migração `a3e6b91c4d05`) e a regra num lugar só:
`ProdutoRepository._vendavel()`, a lista de condições que `listar_para_
lancamento` e `listar_ativos_de_categoria_ativa` compartilham. Duas cópias
divergiriam, e a divergência apareceria como o produto estando na busca de uma
tela e não na da outra — que é como o atendente conclui que o cardápio sumiu.

Dois detalhes que a consulta tem que acertar, os dois com teste:

* **`outerjoin`, não `join`** — produto sem subdivisão é a maioria de um
  cardápio em organização, e um `INNER JOIN` o apagaria do balcão inteiro;
* **reativar o grupo não religa quem foi desativado sozinho** — religar a
  subdivisão não pode desfazer, calado, a decisão tomada item a item.

**O que não mudou:** a impressora continua saindo de
`produto.categoria.impressora` e só (§9.8). Desativar uma subdivisão não
reconfigura bobina — ela apenas deixa de ter item para mandar. Os 2 cupons da
bancada saíram idênticos linha a linha.

#### Decisão 2 do Vitor: excluir com itens dentro exige a Senha Master

O §9.9 deixava a exclusão passar sempre, soltando os produtos em "Sem
subcategoria" (`ondelete="SET NULL"`). Não perdia nada — e também não perguntava
nada: um clique desmanchava, calado, a classificação de dezenas de itens, e
refazê-la é trabalho manual. Agora são dois caminhos, por dois riscos
diferentes:

* **vazia** — confirmação simples, e sai. É o caso do pedido;
* **com produtos** — o service **recusa**, com o número ("existem 3 produtos
  vinculados a ela"). A tela diz a mesma frase antes de tentar, porque quem
  insistir e for barrado tem que ler a mesma coisa, senão parecem dois
  problemas diferentes;
* **com produtos + Senha Master** — a cascata. Nível 3, `PinPadDialog.
  para_exclusao`, a mesma credencial que abre a Central de Loja. A barreira é
  da TELA, e não do service, pela razão do §9.10: `exigir_gerente()` é
  satisfeito pela SESSÃO, e quem abriu o turno de manhã autorizaria a cascata
  que alguém clicasse à tarde.

**Nem todo produto pode sair do banco, e é o histórico que decide.** Quem já
apareceu numa comanda (ou está preso a um combo) tem linha apontando para ele:
apagá-lo arrancaria junto o item da venda, o total do turno e o cupom que já
saiu na bobina. Esses são **arquivados**; o resto é apagado de verdade. Tudo num
commit só — metade dos produtos apagados e a subcategoria de pé é um estado que
ninguém pediu e que a tela não sabe mostrar.

Daí a coluna `produtos.arquivado`, e ela **não** é o mesmo que `ativo=False`:

| | some do balcão | some do Cardápio | dá para reativar |
|---|---|---|---|
| `ativo = False` | sim | **não** (selo DESATIVADO) | sim, é o gesto de todo dia |
| `arquivado = True` | sim | sim | não, foi excluído |

Reaproveitar `ativo` para o arquivamento faria um produto meramente desativado
sumir do Cardápio — e aí não haveria como reativá-lo. As duas colunas existem
porque são duas perguntas diferentes, e `ComandaService.lancar_item` confere as
duas: o arquivado é barrado com mensagem própria ("foi excluído do cardápio"),
antes da de desativado, senão o operador ficaria procurando como reativar um
item que não aparece mais na tela.

#### Achado no caminho: a confirmação de excluir CATEGORIA mentia

Promover a ação ao rodapé tornou visível que o `QMessageBox` dizia "Todos os
produtos vinculados a ela também serão excluídos permanentemente" — e
`excluir_categoria` faz o **oposto**: recusa categoria com produto dentro,
justamente para não arrancar item com histórico. O texto passou a dizer o que o
service faz.

#### Conferência

* suíte **1596** (de 1530), 0 falhas — 66 testes novos, a maioria em três
  arquivos (`test_subcategoria_no_balcao.py`,
  `test_migracao_subcategoria_ativa.py`, `test_barra_de_acoes_do_cardapio.py`);
* **24 mutações, 23 reprovam**. As sobreviventes da primeira passada não viraram
  teste novo — viraram correção, e as quatro estão registradas porque cada uma
  apontou um problema real:
  * `ativar_produto` aceitava um produto **arquivado**: virou recusa com
    mensagem (o buraco de verdade, e o único que teria chegado ao balcão);
  * o filtro `arquivado` de `SubcategoriaRepository.contar_produtos` **nunca
    exclui linha nenhuma** (arquivado sempre tem `subcategoria_id` nulo, porque
    a cascata apaga a subcategoria no mesmo commit): saiu;
  * a linha `self._selecao = ... _SUB_TODAS` depois de excluir **repetia** o
    `reserva` do `_montar` (§9.11): saiu;
  * as duas restantes ganharam o teste que faltava — a pintura apagada da
    pílula na árvore (recorte da linha **fora da seleção**, com a fonte da
    marca registrada) e o clique numa linha de produto não movendo a árvore;
* bancada visual a 1366x738: **22 das 24 telas idênticas byte a byte**, as duas
  do Cardápio diferindo **só na faixa do rodapé** (y=659..695) — que é o item;
* bancada de cupons: os **2 idênticos** linha a linha;
* memória, sobre o cardápio real (15 categorias, 113 produtos), com o mesmo
  leitor de RSS do `tools/medir_memoria.py`: **+0,9 MB** e **zero widget novo**
  (72 → 72) depois de 60 voltas de desativar/ativar/selecionar e 40 de
  criar+escolher+excluir subcategoria. A linha de base do processo é ~115 MB,
  como o §9.11 já registrou;
* os diálogos abrem de verdade nos testes da view (`executar_modal` roda,
  `exec()` roda, o service grava): um dublê provaria só que o teste sabe chamar
  o service.

#### Ficou de fora, de propósito

- **`subcategorias.ativo` não tem tela própria de relatório nem filtro.** O
  estado aparece onde se age sobre ele: o carimbo `DESATIVADA · 3 PRODUTOS` no
  cabeçalho do bloco e a pílula apagada na árvore. Na árvore é só o tom, e não a
  palavra: a pílula tem ~190px na coluna de 300, e "DESATIVADA" comeria o nome.
- **Não há registro de quem arquivou o quê.** Não existe tabela de log no
  projeto (a mesma nota do §9.10 sobre quem olhou um segredo).
- **O arquivado não tem como voltar pela tela.** É a consequência aceita de
  "some de todas as telas do cardápio": a linha continua no banco para os
  relatórios, e desarquivar exigiria uma tela de lixeira que ninguém pediu.
- **A exclusão de categoria continua no `QMessageBox` do sistema**, como o §9.12
  já tinha anotado. Só o texto foi corrigido.
- **A assimetria das duas regras de nome repetido** (§9.12) continua de pé.

---

### 9.14 Excluir a categoria inteira, com itens e subcategorias dentro ✅ CONCLUÍDO — 2026-09-12

Pedido do Vitor, logo depois do §9.13: *"devemos implementar uma regra, deixando
excluir toda uma categoria por mais que tenha itens e subclasses, mas deverá
gerar uma tela de senha de pin exigindo a senha master"*. É o §9.13 um nível
acima — e o nível acima esbarra numa coisa que o de baixo não tinha.

#### A restrição que desenha o item inteiro

`produtos.subcategoria_id` é **anulável** (`ondelete="SET NULL"`), então a
subdivisão do §9.13 sempre sai do banco: o produto guardado apenas perde a
etiqueta. `produtos.categoria_id` é **NOT NULL**, e essa diferença não é
enfeite — foi escolhida no §9.8 porque produto sem categoria não tem impressora
e não sairia em cupom nenhum.

Consequência direta: um produto que precisa sobreviver à exclusão (já foi
vendido, e apagá-lo arrancaria o item da comanda, o total do turno e o cupom que
já saiu na bobina) **tem que continuar apontando para alguma categoria**. Por
isso a cascata da categoria tem dois finais:

| o que há dentro | o que acontece com a categoria |
|---|---|
| nada com histórico | **apagada de verdade**, e as subdivisões vão junto pelo `cascade` da relação |
| algo com histórico | **fica marcada** (`categorias.arquivado`), some de todas as telas, e é a linha dela que sustenta a venda antiga |

Daí a coluna `categorias.arquivado` (migração `c7b4e0f12a86`) — o mesmo par
`ativo`/`arquivado` do produto, e pela mesma razão de existirem os dois:
`ativo=False` some do balcão e **continua** no Cardápio para poder voltar;
`arquivado=True` some de todas as telas e não volta.

#### O nome, que é o detalhe que morderia depois

`categorias.nome` é `UNIQUE`. A categoria guardada continuaria ocupando
"Lanches" — que é exatamente o nome que o gerente vai querer recadastrar ao
reorganizar o cardápio. Sem tratar isso, excluir "Lanches" e criar "Lanches" de
novo esbarraria numa linha que ninguém vê, com um erro que ninguém entende.

Quem libera o nome é o **service**, renomeando a linha guardada para
`Lanches [excluída #3]`. O marcador leva o `id`, então é único por construção
mesmo que o mesmo nome seja excluído duas vezes, e o corte a 80 tira o fim do
NOME e nunca o marcador — é ele que dá a unicidade.

A alternativa era tirar a `UNIQUE` do banco, e ela foi **recusada**: isso exige
recriar a tabela `categorias` inteira com `produtos` e `subcategorias`
apontando para ela e o `PRAGMA foreign_keys=ON` ligado (o mesmo perigo do
cabeçalho da `f8d1a6c40b27`). Risco grande, no banco que é a única cópia dos
dados do pai do Vitor, para resolver o que uma linha de service resolve.

#### "Vazia" ficou mais estrito que na subcategoria

A exclusão simples agora exige **nem produto nem subdivisão**. As subdivisões
sempre foram junto pelo `cascade` da relação (§9.9) — e irem junto **em
silêncio**, num clique em "Excluir" na CATEGORIA, desmanchava a organização de
um grupo inteiro sem perguntar, e refazê-la é trabalho manual. A recusa soma as
duas parcelas ("ela tem 1 produto e 2 subcategorias"), porque é o par que
dimensiona o trabalho de esvaziar.

#### As portas que a categoria guardada fecha

`_categoria_viva()` é o guarda por onde passam editar, ativar, desativar,
associar impressora, criar subcategoria e criar/atualizar produto. Não é
simetria com `ativar_produto`: a linha guardada existe **só** para segurar a FK
das vendas, e reativá-la traria de volta um grupo cujos itens continuam
arquivados — uma categoria vazia com nome de lápide. As listagens do Cardápio,
do seletor de cadastro, dos KPIs e da tela de Impressoras passaram a filtrar.

#### Conferência

* suíte **1628** (de 1596), 0 falhas, 32 testes novos em dois arquivos
  (`test_categoria_em_cascata.py`, `test_migracao_categoria_arquivada.py`) mais
  a seção 6b de `test_barra_de_acoes_do_cardapio.py`;
* **18 mutações, as 18 reprovam**. A primeira passada teve uma sobrevivente — o
  filtro de `arquivado` em `listar_ativas`, que a cascata torna redundante ao
  desligar `ativo` junto — e ela virou o teste que prende o cinto, o mesmo par
  (e a mesma razão) do `Produto.arquivado` no §9.13;
* bancada visual a 1366x738: as **24 telas idênticas byte a byte** às do §9.13.
  É o esperado e vale registrar: o item inteiro vive em diálogos, e a tela
  parada não mudou um pixel;
* bancada de cupons: os **2 idênticos** linha a linha;
* boot de ponta a ponta em banco novo: migrations + seed duas vezes, 60 mesas,
  15 categorias, 113 produtos, 0 arquivados, WAL ligado, head `c7b4e0f12a86`.

**Um defeito do próprio teste, achado por mutação e corrigido:** o helper
`encenar()` do §9.13 **travava** quando o diálogo aberto era de tipo diferente
do que o roteiro esperava — foi o que aconteceu com a mutação que tirava o aviso
de bloqueio, fazendo o cartão de PIN abrir onde se esperava um `QMessageBox`. O
relógio girava para sempre dentro do `exec()`. Ele ganhou um teto de espera e
passa a fechar o diálogo inesperado: um teste que pendura a suíte é pior que um
teste que falha.

#### Ficou de fora, de propósito

- **Desarquivar categoria pela tela** — não existe lixeira, pela mesma razão do
  §9.13.
- **Escolher para onde mover os produtos com histórico.** Seria mais uma decisão
  no meio de um gesto destrutivo; a regra automática (guarda quem tem venda,
  apaga o resto) é a que não exige pensar na hora.
- **Relatório de vendas por categoria**, que é o que daria valor a preservar a
  associação do produto arquivado com a categoria guardada. O dado está lá para
  quando for.

### 9.15 A composição do combo em cartão, com stepper por linha ✅ CONCLUÍDO — 2026-09-13

Pedido do Vitor com um mockup: trocar o `_ComboComponentesDialog` — moldura do
sistema, uma `QTableWidget` de duas colunas e dois botões chapados, dentro de
`cardapio_view.py` — por um cartão com uma linha por componente e o stepper de
quantidade na própria linha. É o **nono modal em cartão** do app:
`src/gestor_comercial/ui/widgets/composicao_combo_dialog.py`.

O defeito de uso que o mockup resolve é concreto: na tabela antiga, **mudar a
quantidade de um componente era removê-lo e associá-lo de novo** — dois
commits, e entre eles um combo com um item a menos (e, se era o único, um combo
que tinha deixado de ser combo).

#### Duas decisões do Vitor, respondendo a perguntas feitas antes de começar

1. **"Produto principal" / "Adicional" não existem no banco.** O mockup desenha
   um selo âmbar com visto para o principal e um neutro para o adicional, mas
   `combo_itens` é só combo + produto + quantidade. As opções eram inventar por
   heurística ("o primeiro é o principal", sem jeito de trocar), gravar uma
   coluna nova que nenhuma outra tela leria, ou não ter papel. O Vitor escolheu a
   terceira: **o subtítulo de cada linha é a CATEGORIA real do componente** e
   **o selo âmbar marca a linha SELECIONADA** — a que o "Remover" vai tirar. O
   schema ficou intacto, sem migração.
2. **"+ Adicionar componente" reusa o cartão "Adicionar item"** (§9.4) num modo
   componente, em vez de manter o formulário de fábrica ou criar uma segunda
   busca de produto. O modo comanda tinha de continuar intacto.

#### O que foi feito

- **Um método novo no service, e só um:** `alterar_quantidade_componente`, com
  as mesmas travas de `associar_componente` (gerente, inteiro, maior que zero,
  o `True` que é `int` em Python). Grava na hora — o rodapé do mockup diz
  "ALTERAÇÕES APLICADAS NESTE COMBO", e não há Salvar/Cancelar para esquecer.
  Na tela, **o número só muda depois de o service aceitar**: recusa não mexe no
  stepper e o motivo aparece no status.
- **Linhas com widget**, e não delegado: a regra do §9.4/§9.11 é "widget por
  linha só quando a linha tem controle de verdade dentro", e o stepper tem dois
  botões que gravam. O stepper não remonta a lista (a mesma instância de linha
  continua na tela, banco não é relido); a remoção destrói a linha na hora; a
  volta do cartão de adição **sincroniza** — só nasce a linha nova, as que
  ficaram são as mesmas. A chave da sincronização é o par (componente, produto),
  e não só o id: o SQLite reaproveita o maior id quando a última linha é
  apagada, e casar só pelo id reescreveria o nome de uma linha em vez de
  trocá-la.
- **Teclado:** ↑/↓ trocam a linha, Delete/Backspace removem, Esc fecha. A
  seleção passa para quem ocupou o lugar da removida (o comportamento da tabela
  antiga). Nenhum botão aceita foco (`preparar_botao`), então o Espaço não
  "clica" o stepper sem ninguém ver.
- **Modo componente no "Adicionar item"** (`MODOS`, uma linha por modo, a forma
  do §9.6/§9.12): título, sufixo do contexto, frases de teclado e aviso, teto de
  99 (o do `QSpinBox` antigo, e o mesmo do stepper), e **sem observação e sem
  prévia em R$ — não criadas**, e não só escondidas. A lista já chega sem o que o
  service recusaria (o próprio combo, quem já é combo, quem já está na
  composição); o service continua recusando. É lida na hora do clique, e não na
  abertura da composição: o stepper faz commit e expiraria um instantâneo velho
  (o N+1 do §9.4).
- **A view só recarrega o Cardápio se algo foi gravado** (`modal.alterou`).
  Abrir, conferir e fechar deixou de custar a recarga da tela inteira.
- **Família de cor própria** (`composicao_*`, nos dois temas). A borda e o selo
  da linha selecionada usam `acento`, de propósito; o "Remover" é pílula escura
  com texto coral, e **não** o Vermelho Ferrari chapado do Excluir — tirar um
  componente se desfaz adicionando de novo, e o vermelho chapado fica para o que
  não volta.
- **Apagados:** `_ComboComponentesDialog`, `_ComponenteDialog` e o
  `BuscaProdutoWidget`, que ficou sem ninguém que o usasse (o §9.4 o tinha
  mantido só por causa do formulário de componente). `busca_produto.py` ficou
  com a regra de busca, que o cartão usa.

#### O que o pedido escrito dizia e não foi seguido ao pé da letra

- **"Entre 560 e 600px" não fecha**, pelo mesmo motivo do §9.12: o rodapé de uma
  linha pede **635px** com a fonte da marca. A 600px o botão primário saía como
  "olonar compone" e o contexto perdia o "COMBO". O cartão ficou em **640px**,
  entre o teto do pedido e os 672px da própria imagem do mockup, com teste que
  mede `width() < sizeHint()` de cada peça do rodapé. Altura: 527px, sob os
  728px úteis.
- **O vocabulário do Tkinter** (`destroy()`, `unbind`, `with conn:`) virou o do
  projeto: `executar_modal`/`deleteLater`, `disconnect` nominal com a trava
  `_limpo`, e a atomicidade é a de sempre — `@transacional` na classe do service
  e um `uow.commit()` por operação (§3.1). Não existe conexão SQLite crua para
  um `with conn:` neste código.
- **"`produtos_combo`" e "baixa de estoque dos componentes" não existem na V1.**
  Só há `combo_itens`; a baixa que o Java fazia é backlog da V2
  (`comanda_service.py`), e a impressão não lê `combo_itens` — o combo sai no
  cupom como um produto, pela impressora da categoria DELE (§9.8). Nada disso
  foi tocado, e a bancada prova (abaixo).
- **Hex literais do pedido** viraram tokens: a paleta "Concreto" já é a do
  mockup, e hex cravado some no tema claro (§3.15).
- **O teto de ~90 MB** continua valendo o que o §9.11 registrou: o processo já
  mede ~100 MB antes do Cardápio existir, e nenhuma tela sozinha o alcança. O que
  este item pode garantir é não crescer — medido abaixo.

#### Achados no caminho, todos com teste

1. **O escurecedor de um cartão sobre outro cartão pintava cantos quadrados.**
   O "Adicionar componente" abre por cima da composição, que é uma janela
   translúcida com cantos de 16px; o `Backdrop` enchia o retângulo inteiro.
   Medido no pixel (1,1) do cartão de baixo: **alfa 150 antes, 0 depois**.
   `cartao_modal.montar` passou a arredondar quando a janela de trás é
   translúcida (`RAIO_CARTAO_PX`). É o primeiro caso de cartão sobre cartão; o
   próximo já nasce certo.
2. **A barra de rolagem deslocava os steppers.** A partir da quarta linha ela
   come 8px do viewport e todos os números andavam para a esquerda de uma vez,
   descasando do rótulo "QUANTIDADE". `_acomodar_barra` devolve a largura pela
   margem direita (o mesmo cuidado do cartão de Recebimentos do Caixa, §9).
3. **`border-radius` maior que metade da altura deixa o botão quadrado.** Com
   20px num botão de 38px o Qt desiste de arredondar, sem aviso. Ficou 18px.
4. **N+1 na listagem de componentes:** `listar_por_combo` carrega produto e
   categoria por `selectinload` (1+2N consultas → 3 fixas), e
   `remover_componente`, que só perguntava "sobrou alguém?", passou a usar o
   `EXISTS` que já existia em vez de carregar a lista.
5. **Um `showEvent` idêntico ao do `cpf_dono_dialog`**, que
   `test_nenhuma_funcao_da_ui_repete_o_corpo_de_outra` reprovou: a rotina saiu
   para `cartao_modal.apresentar` e os dois cartões a usam.

#### Conferência

- suíte **1698** (de 1628), 0 falhas, **70 testes novos**: 52 em
  `test_composicao_combo_dialog.py`, 11 em `test_cardapio_service.py`, 7 em
  `test_adicionar_item_dialog.py`;
- **30 mutações na primeira passada, 25 reprovaram.** As 5 sobreviventes viraram
  4 testes e 1 remoção de código:
  - tirar o `commit()` do stepper passava a suíte inteira — a leitura na mesma
    Session ainda via o valor. **É o achado sério do item**: sem o commit, o
    rollback da próxima operação recusada, qualquer uma, desfaria a quantidade
    calado. O teste agora faz `rollback()` e confere;
  - tirar o filtro do "próprio combo" não reprovava porque o filtro `is_combo`
    o mascarava — só o produto que AINDA não tem componente o exercita;
  - "a seleção vai para quem ocupou o lugar" só era testada com 2 linhas, onde
    vizinho e primeira coincidem — ganhou o caso de 3;
  - o teste da linha removida só olhava depois do `deleteLater`, e tirar o
    `setParent(None)` passava — agora mede antes e depois (e o comentário que
    prometia "filha até o diálogo fechar" foi corrigido: é só até o laço girar);
  - um ramo que engolia o Enter não mudava nada (nenhum botão é padrão) e
    **saiu**.

  Segunda passada: as 4 reprovam;
- **memória**, banco em arquivo com WAL e `synchronous=FULL`, 5 ciclos de
  aquecimento e 4 blocos de 60 ciclos (abrir, 6 cliques no stepper, remover,
  abrir o cartão de adição, readicionar, fechar): widgets vivos **1 → 1** em
  todos os blocos, nenhum diálogo preso; RSS +0,77 MB no primeiro bloco e depois
  **+0,05 / +0,10 / +0,17 MB**. A primeira medição dava +0,3 MB por bloco — era a
  lista de consultas da própria bancada crescendo, e sumiu ao tirar o listener;
- **tempo:** abrir o cartão 14 ms / 4 consultas; clique no stepper **2,5 ms**
  (mediana, commit em disco) / 3 consultas;
- bancada visual a 1366x738 contra `2a87dcf`: **as 24 telas idênticas byte a
  byte** — o item vive em diálogos, e a tela parada não mudou um pixel;
- bancada de cupons: os **2 idênticos**, e — como a bancada padrão não vende
  combo nenhum — uma venda a mais com o "Combo Fritas + Coca Cola Lata" ×2 ao lado
  de um X Tudo: pedido de produção, pré-conta e recibo **idênticos** linha a
  linha nos dois códigos;
- renderização nativa com o cardápio real nos estados que importam: dois temas,
  linha selecionada trocada, erro do service, lista vazia, cinco componentes com
  rolagem e nome de combo com reticências, e o cartão de adição por cima.

#### Ficou de fora, de propósito

- **Reordenar componentes.** A ordem é a de associação; sem "principal", ordem
  não significa nada para o sistema.
- **Confirmação ao remover.** A tabela antiga não tinha, o mockup não desenha, e
  remover um componente se desfaz em dois cliques. Excluir PRODUTO continua com
  confirmação.
- **O modal no inventário de `test_vazamento_modais.py`.** O ciclo de vida dele
  (30 aberturas com `exec()`, escurecedor, sinais, linhas removidas) está
  coberto no arquivo próprio, como o do §9.12.
- **Os dois formulários de fábrica que sobraram no Cardápio:** `_ProdutoDialog`
  e a exclusão de categoria no `QMessageBox` do sistema.

### 9.16 A foto do produto: formato recusado na porta, miniatura presa na caixa ✅ CONCLUÍDO — 2026-09-13

Relato do Vitor com captura do bloco "Sucos e Vitaminas" (subcategoria de
Bebidas): as fotos saíam cada uma de um tamanho, a Limonada Suíça e o SucoAcerola
eram pintados **por cima do próprio nome**, e escolher um `.avif` dava erro.

#### O diagnóstico, medido antes de mexer

- **O estouro não era do delegado, era do cache.** `processar_imagem_produto`
  guardava a miniatura "cabendo em 120x120" com a proporção original, e o
  `thumbnail_cache` a **escalava** com `KeepAspectRatioByExpanding` — que enche
  o quadrado pelo lado menor e deixa o maior passar, sem cortar (só o formato
  círculo cortava). No banco real, **18 das 35 miniaturas em disco não eram
  quadradas** (120x67, 67x120, 93x120...). A 36px a 120x67 virava 64x36, e os
  28px de sobra caíam no começo do nome; a 67x120 passava do divisor da linha.
- **O `.avif` não era do Pillow**: o pipeline é `QImage` desde o começo (sem
  Pillow como dependência, decisão registrada no módulo). O Qt do projeto não lê
  AVIF nem HEIC ("Unsupported image format"), a leitura voltava nula e a tela
  abria um `QMessageBox` com o caminho inteiro do arquivo. O filtro do seletor
  ainda oferecia `*.bmp`.
- **Um terceiro defeito, achado pela sonda do pipeline e não relatado:** PNG com
  fundo transparente virava **quadrado preto** no JPEG salvo. JPEG não tem alfa,
  e o Qt grava a cor que estava por baixo do transparente — (0, 0, 0).

#### O que foi feito

- **`ler_quadrado_central(caminho, lado)`** em `services/imagem_service.py`: o
  enquadramento do `ImageOps.fit` (escala pelo lado menor, corta o excesso igual
  dos dois lados), pedido ao **leitor** com `setClipRect` + `setScaledSize`. Nunca
  devolve outro tamanho — é contrato. Quem grava a foto nova e o cache usam a
  mesma função, e por isso **as miniaturas antigas em disco ficaram certas sem
  regravar nenhuma**.
- **Miniatura em disco exatamente 120x120**, achatada sobre branco se tiver alfa.
  120 e não os 44 do pedido: a mesma miniatura serve a prévia de 80px do cadastro
  e os cinco lados que as telas pedem (28, 32, 36, 40, 80), e em tela de 125% os
  36px lógicos já são 45 físicos. Continua JPEG (1-6 KB): WebP com alfa seria
  melhor para o transparente, mas dependeria do plugin `qwebp` no `.exe`, que a
  máquina limpa ainda não conferiu.
- **Formatos homologados num lugar só**: `EXTENSOES_ACEITAS` (png, jpg, jpeg,
  webp), e o `FILTRO_DO_SELETOR` sai dela — separado por espaço, que é a grafia do
  Qt (`*.png,` com vírgula seria um padrão que não casa com nada). **O filtro não
  é barreira**: no seletor nativo do Windows dá para digitar `*.*` ou colar um
  caminho, então a extensão é conferida no service, sem diferenciar maiúsculas
  (`FOTO.JPG` de câmera passa). Um `.avif` renomeado para `.jpg` passa pela lista
  e é recusado pela leitura — com a **mesma frase**.
- **Recusa discreta**: `ValueError("Formato inválido. Selecione PNG, JPG ou
  WEBP.")` para a tela, e o caminho com o motivo técnico no log do app
  (`logger_do_app().exception`, o `gestor.log` rotativo da caixa-preta — não um
  `error.log` paralelo, que partiria o registro em dois). No `_ProdutoDialog` o
  aviso é uma linha `campoErroRotulo` ao lado dos botões da foto, **sem
  `QMessageBox`**; nome, preço, custo e descrição ficam como estavam, a foto que
  já estava continua valendo e não é marcada para apagar.
- **Cartão com cantos de 8px e borda `borda_card`**, na foto e no placeholder,
  com a mesma silhueta (teste confere os pixels de canto de um contra o outro).
  O raio tem teto de um quarto do lado, para o 28px do ranking não virar círculo.
  O círculo do "Adicionar item" ficou como era, sem borda.
- **Placeholder**: a letra passou de `texto_fraquissimo` para `texto_fraco`, que
  no Escuro é exatamente o `#A1A1AA` pedido. O fundo segue `superficie_2`
  (`#1C1C1A`, a 2 pontos do `#1E1E1C` do pedido): o único token com aquele hex é
  `tecla_numerica_bg`, e pegá-lo seria o empréstimo de cor do §9.5.
- **Segunda trava no delegado do Cardápio**: `setClipRect` na caixa da miniatura.
  Com o cache consertado ela não muda um pixel, e existe para o dia em que alguém
  devolver um pixmap maior — o que pagava o defeito era o nome do produto.

#### O que o pedido escrito dizia e não foi seguido ao pé da letra

- **Pillow e `ImageOps.fit`** viraram `QImageReader`, com o mesmo enquadramento.
  Trocar de biblioteca não seria cirúrgico, e o leitor do Qt dá uma coisa que o
  `Image.open` + `fit` não dá sem `draft()`: o JPEG já é decodificado na escala
  reduzida. Medido (2 rodadas, memória privada do processo, foto 4000x3000):
  escolher a foto levava o processo de **64 → 110 MB** no pipeline antigo, e vai
  de **65 → 68 MB** no novo.
- **"LRU ou limite de 100 itens"**: o LRU já existia, com teto 200, e ficou.
  O cardápio real tem 113 produtos e duas telas com lados diferentes; com 100,
  rolar a lista inteira despejaria o que acabou de ser pintado e voltaria ao
  disco a cada repintura. A 36px um pixmap tem 5,2 KB — o cache cheio fica perto
  de 1 MB.
- **"`deleteLater()` nos widgets de imagem ao trocar de categoria"**: desde o
  §9.11 o Cardápio **não tem widget por linha** (é delegado, com
  `test_nenhuma_linha_das_duas_listas_e_widget`). Não há o que destruir, e voltar
  a ter widget para poder destruí-lo seria a regressão. Comanda e ranking do
  Dashboard continuam com `QLabel` de tamanho fixo, que já recortava.
- **44x44 e 14px de margem**: a geometria da linha (36px + 12px) não mudou. Na
  captura do Vitor, a 125%, ela já mede 45 e 15 pixels físicos — os números do
  pedido são os da própria tela.

#### Conferência

- suíte **1773** (de 1698), 0 falhas, **75 testes novos**: 59 em
  `tests/ui/test_foto_do_produto.py` (lado exato do cache nas 5 proporções do
  banco real × 5 lados × 2 recortes, cantos, placeholder por arquivo ilegível,
  silhueta, a foto deitada pintada numa linha real do delegado, a trava do clip
  sozinha com um pixmap 64x36 injetado, e o cadastro) e 16 em
  `tests/unit/test_imagem_service.py`;
- os testes de pixel da linha têm **duas asserções**: que a foto foi pintada, e
  que não saiu da caixa — sem a primeira, um `paint` que estourasse (o
  `nao_deixa_escapar` engole) passaria verde sem ter pintado nada;
- **13 mutações, as 13 reprovam**: sem checagem de extensão, recorte no canto
  (0,0), sem recorte, sem achatar o alfa, sem log, `.bmp` de volta na lista, o
  cache do defeito original, foto sem cantos, placeholder com o raio antigo,
  delegado sem clip, `QMessageBox` de volta, aviso que não some no sucesso e o
  filtro literal antigo;
- **renderização com o banco e as fotos reais** (cópias na pasta temporária),
  Bebidas rolada até "Sucos e Vitaminas", código de antes e de depois, nos dois
  temas: o "antes" reproduz a captura do Vitor, o "depois" tem as seis fotos no
  mesmo quadrado e os nomes alinhados;
- bancada visual a 1366x738 contra o código anterior: **18 das 24 telas idênticas
  byte a byte**; as 6 que diferem (Cardápio, Comanda e Dashboard, nos dois temas)
  mudam **só na coluna das miniaturas** — Cardápio x=614..649, Comanda
  x=295..326, Dashboard x=741..768 —, que é o placeholder com o raio de 8px e a
  letra nova.

#### Ficou de fora, de propósito

- **Regravar as 35 miniaturas antigas.** O recorte na leitura já as conserta na
  tela. As que vieram de PNG transparente continuam com o fundo preto gravado no
  JPEG até a foto ser escolhida de novo.
- **Tirar o fundo branco das fotos de catálogo** (Suco de Laranja, Jarra 1L). É
  a foto, não o pipeline; a borda e os cantos agora dizem onde ela acaba.
- **Miniatura nítida em tela de 125%** (`devicePixelRatio`): o pixmap de 36px é
  ampliado para 45 pixels físicos. Não foi pedido, e o monitor do food truck é o
  de 1366x768 a 100%.
- **O `_ProdutoDialog` em cartão** — continua o último formulário de fábrica do
  Cardápio; aqui só ganhou o aviso em linha.

### 9.17 O acordeão da árvore do Cardápio: clicar na categoria aberta a recolhe ✅ CONCLUÍDO — 2026-09-13

Relato do Vitor: clicar numa categoria só expandia. Clicar de novo na mesma não
fechava, e as subdivisões ficavam na tela para sempre.

#### O diagnóstico

- **O gesto inverso não existia.** `_ao_clicar` só tinha o ramo "fechada →
  abre"; na aberta ele reescolhia o "Todas" e parava.
- **Inverter a condição não bastava — duas coisas do Qt, medidas numa sonda
  antes de mexer:** (1) recolher o pai deixa o "atual" preso num filho que saiu
  da tela; (2) `setCurrentItem` num filho de ramo fechado **não é recusado**: o
  `scrollTo` do Qt **reabre o ramo sozinho**. A docstring de
  `_primeiro_filho_visivel` dizia o contrário e foi corrigida.
- **A recarga reabria.** `_montar` tratava "categoria selecionada" como
  "categoria aberta": a recolhida voltaria aberta na primeira navegação até a
  tela ou no primeiro produto salvo.

#### O que foi feito

- **`_ao_clicar` alterna**: aberta recolhe (`_expandida_id = None` e a seleção vai
  para a linha da categoria, que já é o "Todas" dela); fechada abre por
  `_abrir_somente`, que fecha as outras. Vale na linha inteira — seta, nome e
  contador são pintura da mesma linha (§9.11), não alvos separados.
- **A recarga respeita a recolhida**: `_expandida_id` em `None` com categoria
  selecionada em "Todas" é esse estado, e a seleção volta para a **linha** (mirar
  o filho reabriria o ramo). Só em "Todas": com uma subdivisão escolhida — a seta
  → do teclado abre a categoria por fora do acordeão — a recarga abre a categoria
  e **não** troca a subdivisão por "Todas" em silêncio.
- **Três caminhos abrem por conta própria**, porque a recarga agora respeita a
  recolhida: criar categoria (a nova abre), criar subcategoria (subdivisão vazia
  não vira bloco em "Todas" — recolhida, o cadastro não apareceria em lugar
  nenhum) e clicar num cabeçalho de bloco à direita (reabre pelo acordeão; pelo
  Qt, `_expandida_id` ficaria `None` e a busca da árvore fecharia o ramo debaixo
  da subdivisão escolhida).
- **Ampliar não solta o produto** (`_ProdutosPainel.atualizar`): de uma
  subdivisão para "Todas" na **mesma** categoria — que é o que recolher faz — o
  produto escolhido fica, e sem produto a lista rola até o bloco de onde o
  gerente veio (`ListaDeProdutos.rolar_ate_o_bloco`) em vez de ir ao topo. É uma
  regra de lugar, e não de gesto: clicar em "Todas as subcategorias" dá o mesmo
  resultado que recolher, porque os dois levam ao mesmo lugar. **Estreitar e
  trocar de categoria continuam soltando (§9.13)**, e a âncora é presa à mesma
  categoria porque "Podrão" pode existir em duas.
- Os três helpers `_abrir` das suítes do Cardápio passaram a descrever o estado
  de chegada ("aberta em Todas"), e não o gesto: numa já aberta, o clique agora a
  recolheria.

#### O que o pedido escrito dizia e não foi seguido ao pé da letra

- **"Destruir explicitamente sub-itens, badges e linhas-guia ao recolher"
  (`destroy()`/`deleteLater()`)**: desde o §9.11 a árvore **não tem widget por
  linha** — badge, contador, seta e guia são pintura do `DelegadoArvore`. As
  subdivisões são `QTreeWidgetItem` (objetos C++ sem widget), criados uma vez
  por recarga em `_montar` e destruídos pelo `clear()` dela. Recolher não cria
  nem esconde contêiner nenhum que acumule. Destruí-las ao fechar obrigaria a
  recriá-las a cada abertura — mais alocação por clique, não menos — e quebraria
  a busca da árvore, que casa pelo nome da subdivisão com a categoria fechada.
- **"Desconectar sinais das closures `command=lambda`" e "`after_cancel`"**: são
  idiomas de Tkinter. Aqui não há sinal por linha (os dois da árvore são ligados
  uma vez no `__init__`, a métodos, sem `lambda`) e não há timer: o
  `QTreeView.isAnimated()` é `False` (conferido), então abrir e fechar não agenda
  nada.
- **"~90 MB no Celeron"**: o gesto não move esse número, para cima nem para
  baixo — o §9.11 já registrou que o processo passa disso antes de o Cardápio
  existir. O que se mede é o que o gesto acrescenta, abaixo.

#### Conferência

- suíte **1794** (de 1773), 0 falhas, **21 testes novos** em
  `tests/ui/test_acordeao_do_cardapio.py`, com **clique de mouse de verdade**
  (`QTest`) na seta, no nome e no contador: alternância, seta que perde o âmbar
  e filhas fora da tela, seleção na linha (pelo mouse e pelo código), recarga
  que não reabre e que não troca subdivisão por "Todas", a direita conferida
  passo a passo abrindo/fechando/reabrindo categoria com e sem subdivisão,
  produto mantido vindo de "Todas" e de "Podrão", o limite (escolher a
  subdivisão do próprio produto solta), âncora da rolagem e o caso das duas
  "Podrão", os três caminhos que abrem sozinhos, e 200 cliques com os mesmos
  widgets, `QObject`s e itens e **zero SQL**;
- **16 mutações, as 16 reprovam**. A única sobrevivente da primeira passada — a
  exigência de "Todas" na regra da recarga — virou o teste do caminho que a
  exige (seta → do teclado);
- **cardápio do seed** (15 categorias, 113 produtos, subdivisões em três),
  `MainWindow` com QSS e fontes: 1.000 cliques na mesma categoria com **0
  consultas**, ~1 ms por clique, widgets 72→72, `QObject`s 117→117; RSS +0,38 MB
  no primeiro bloco de 100 cliques (cache de glifo do Qt) e **plano** nos 900
  seguintes e em 10 voltas pelas 15 categorias;
- renderização a 1366x738 dos três estados (aberta em "Podrão", recolhida,
  reaberta) nos dois temas; bancada visual contra o código anterior com as **24
  telas idênticas byte a byte** — o esperado: o item vive no clique, e a tela
  parada não muda um pixel.

#### Ficou de fora, de propósito

- **O teclado.** ← e → abrem e fecham pelo próprio Qt, por fora do acordeão: →
  abre uma segunda categoria sem fechar a primeira. É anterior a este item, e o
  pedido era o clique.
- **A categoria recolhida e selecionada usa o mesmo tom do hover** (é o `realce`
  do delegado desde o §9.11). Com o mouse fora dela, é o único sinal de onde a
  seleção está; não foi pedido.

### 9.18 A exclusão do Cardápio num cartão só, e o produto vendido arquivado ✅ CONCLUÍDO — 2026-09-14

Pedido do Vitor, com três mockups (categoria com produtos, produto sem venda,
subcategoria bloqueada): trocar as caixas de mensagem do sistema da exclusão de
categoria, subcategoria e produto por cartões no desenho do app — e, escrito em
destaque, **um diálogo base só**, parametrizado pela entidade, pela quantidade de
itens vinculados e pelo nível de proteção.

#### As duas decisões do Vitor, perguntadas antes de começar

O pedido e o que já estava decidido não batiam em dois pontos, e os dois são
regra de negócio:

1. **Subcategoria com produtos.** A Foto 3 desenha o botão apagado ("Mova ou
   exclua os produtos antes de continuar"); o §9.13 tinha decidido que a Senha
   Master libera a cascata. **Decisão: fica a cascata do §9.13.** O cartão avisa
   quantos produtos são e o botão "Excluir com Senha Master" fica ligado. O
   bloqueio rígido existe no diálogo (`para_subcategoria(..., cascata=False)`)
   porque o mockup o desenha, mas nenhuma tela o usa hoje.
2. **Produto já vendido, ou preso a um combo.** Até aqui `excluir_produto` só
   RECUSAVA ("Desative-o"), e isso depois de o gerente já ter clicado "Sim".
   **Decisão: arquivar com a Senha Master**, com a amarração de combo desfeita
   antes, "para não deixar referências ativas quebradas". Sem histórico nenhum,
   continua o DELETE físico depois da confirmação simples da Foto 2.

#### O desenho: dois eixos, duas tabelas, uma classe

`src/gestor_comercial/ui/widgets/confirmacao_exclusao_dialog.py`, o décimo modal
em cartão. As três imagens são o mesmo cartão com outras palavras, e o que muda
entre elas se divide em dois eixos que não se misturam:

| eixo | tabela | o que decide |
|---|---|---|
| a entidade | `ENTIDADES` | glifo do item (pasta, etiqueta, caixa), rótulo ("PRODUTO SELECIONADO"), título e a palavra do botão |
| o nível de proteção | `NIVEIS` | a tarja de cima, o tom do aviso (coral ou âmbar) e o que o botão faz: confirma, pede a Senha Master ou nem liga |

É a forma do §9.6 e do §9.12 (uma classe e uma tabela por papel), e não a de
base + subclasses do §9.7: as três entidades não têm nenhuma coluna própria, só
palavras.

**Quem transforma contagem em nível são os construtores nomeados**
(`para_categoria`, `para_subcategoria`, `para_produto`), e só eles. A view lê
`modal.protecao` depois do `exec()` para escolher o método do service, então a
regra que escolhe o cartão e a que escolhe o service são a mesma linha. Antes
eram dois `if` sobre a mesma contagem, um na view e outro implícito na caixa de
mensagem escolhida.

**A tarja é do NÍVEL, e não da entidade**, ao contrário de como o pedido escrito
a distribuía (A = categoria, B = produto, C = subcategoria). As três imagens
fecham com as duas leituras: "EXCLUSÃO PROTEGIDA" é Senha Master, "AÇÃO
PERMANENTE" é a confirmação simples e "CONFIRMAR EXCLUSÃO" é o bloqueio. Só a
leitura por nível impede o cartão de chamar de "ação permanente" um produto que
vai ser arquivado, ou de "exclusão protegida" uma categoria vazia.

#### A Senha Master abre POR CIMA do cartão

O botão "Excluir com Senha Master" não fecha o cartão. Ele chama `autorizar`,
que a view entrega pronto: `_pedir_senha_master` com `partial`, que é o
`PinPadDialog.para_exclusao` (Nível 3, §9.10) nascido **filho do cartão**. O
escurecedor do PIN cobre o cartão com os cantos de 16px (a mesma solução do
§9.15). Se o PIN for recusado ou fechado, o gerente volta ao cartão, que continua
dizendo o que ia sair. Com os `QMessageBox` de antes, fechar o PIN encerrava o
gesto inteiro.

O diálogo não conhece `AuthService`: recebe uma função que diz se passou. E
recusa nascer com `Protecao.SENHA_MASTER` sem ela (`ValueError` na construção),
porque um cartão que promete a Senha Master e confirma sem ela é o pior defeito
possível desta tela, e ele só apareceria na hora de apagar algo.

Os sites de modal da UI foram de **40 para 38**. Saíram seis (duas caixas e um PIN
para cada uma das duas entidades de estrutura) e entraram quatro: um cartão por
entidade, contando o produto, cujo `QMessageBox.question` nem passava pelo
`executar_modal`, e **um PIN só** para as três.

#### O produto com histórico: `arquivar_produto`

Três peças novas no service, e nenhuma migração, porque `produtos.arquivado`
existe desde o §9.13:

- **`VinculosDoProduto`** (`vendido`, `combos_que_o_contem`, `componentes`) e
  `vinculos_do_produto()`: a pergunta que a tela faz antes, em números. O cartão
  precisa DIZER "ele sai da composição de 2 combos", e um `bool` só diria que
  algo vai acontecer. `_tem_historico` (o critério das cascatas) passou a ler o
  mesmo `_vinculos`, então a tela e a cascata usam uma definição só de
  histórico.
- **`arquivar_produto()`**: remove as linhas de `combo_itens` dos dois lados (ele
  como componente de outros combos e, se ele próprio for combo, a composição
  dele), devolve a produto comum todo combo que ficou sem componente e marca
  `arquivado` + `ativo=False`, **num commit só**. O "combo sem componente vira
  produto" saiu de dentro de `remover_componente` para
  `_desfazer_combo_sem_componentes`, que os dois chamam. `combo_itens` não é
  histórico na V1 (impressão e estoque não o leem, §9.15), então desfazer a
  composição não reescreve nada que já saiu na bobina.
- **`quantidades_do_conteudo()`** e **`contagem()`**: "3 produtos e 2
  subcategorias" saiu de dentro de `conteudo_da_categoria`, porque o cartão diz a
  mesma contagem com outro começo ("Esta categoria contém…").

**Uma escolha feita aqui, com o porquê.** O caminho da Senha Master **sempre
arquiva**, inclusive o produto cujo único vínculo era um combo, que depois de
desamarrado poderia ter saído do banco. Foi a instrução literal do Vitor ("após
autenticar, aplique o arquivamento"), e é também a regra das cascatas ("quem tem
vínculo fica marcado"). A diferença para o gerente é nenhuma: nos dois casos o
produto some de todas as telas.

#### O que o pedido escrito dizia e não foi seguido ao pé da letra

- **`destroy()`, `unbind()` e `after_cancel()`** são de Tkinter. Os equivalentes
  estão no cabeçalho do módulo: `executar_modal` destrói, as três ligações saem
  nominalmente em `_soltar_recursos()` com a trava `_limpo`, o escurecedor é
  solto da janela em `done()`, e não há timer nenhum.
- **"Exclusão lógica (`ativo = 0`)"** virou `arquivado = True` **e**
  `ativo = False`. `ativo=False` sozinho deixaria o produto no Cardápio com o selo
  DESATIVADO, podendo ser reativado, o contrário de excluir. A diferença entre as
  duas marcas está no §9.13.
- **"PRODUTO SELECIONADA"** (Foto 2) virou "PRODUTO SELECIONADO". A imagem foi
  montada a partir da de categoria, e a concordância ficou para trás.
- **O Enter confirma**, como o pedido manda, e isso inverte os `QMessageBox`
  substituídos, cujo botão padrão era o Cancelar. O risco continua coberto por
  dois lados: chegar ao cartão já exige um gesto (Excluir ou Delete), e o que tem
  histórico ainda pede a Senha Master depois do Enter.
- **⚠ e 🗑 são desenhados** (`GLIFO_ALERTA`, `GLIFO_LIXEIRA`), pela armadilha de
  sempre (§9.4, §9.10): na fonte da marca eles não existem, e o Segoe UI Emoji os
  pintaria chapados e da mesma cor nos dois tons de aviso. O `BotaoComGlifo` do
  §9.15 saiu de `composicao_combo_dialog.py` para `cardapio_cartoes.py`, que é
  onde os glifos moram, agora que dois cartões o usam.
- **A largura ficou em 500px, dentro dos "460 a 500" pedidos.** Aqui fecha, ao
  contrário do §9.12 e do §9.15, porque o rodapé não tem a faixa de atalhos. O
  preço da fonte da marca, ~20% mais larga que a do desenho, é o título "Deseja
  excluir este produto permanentemente?" quebrar em duas linhas. Nada é cortado:
  o nome do item, o título e o texto do aviso quebram linha em vez de ganhar
  reticências, porque confirmação destrutiva com "Cachorro Quente Lin…" pede
  para o gerente confirmar o que não leu inteiro.
- **O botão vermelho é o coral `#EF4444` do mockup**, e não o `#DC2626` do
  rodapé do Cardápio: sobre o cartão escuro, o Ferrari lê como marrom. No tema
  claro volta ao `#DC2626`. Os tokens são uma família própria, `exclusao_*`, nos
  dois temas, pela lição do §9.5: metade dos hex coincide com `pin_exclusao_*`,
  `composicao_remover_*` e `cardapio_excluir_*`, e cada um veste outra coisa.
- **"Dispare o callback de sucesso e atualize a árvore preservando o nó pai"**:
  a view já fazia isso desde o §9.13. Excluir subcategoria volta ao "Todas" da
  mesma categoria; excluir produto mantém a categoria e a subdivisão; excluir
  categoria recomeça a árvore, porque não há mais pai para onde voltar. Os três
  estão trancados em teste.
- **"~90 MB"**: o cartão não move esse número, nem para cima nem para baixo (ver
  a medição abaixo; o processo já passa disso antes do Cardápio, §9.11).

#### Achados no caminho

- **O cartão do §9.12 fica mudo se reaberto depois de um erro do service.**
  Uma sonda confirmou: `done()` desconecta os três botões, e o
  `while modal.exec()` da view reabre a MESMA instância. Na segunda abertura só
  Enter e Esc funcionam. O defeito é anterior a este item e ficou registrado como
  tarefa separada. O cartão de exclusão não o herda porque é de uma abertura só
  (`executar_modal`), e o cabeçalho do módulo diz isso.
- **O helper `encenar()` da suíte do rodapé travaria diante do cartão novo.**
  Com o PIN aberto dentro do clique, clicar de dentro do relógio de teste poria o
  `exec()` do PIN dentro do disparo do timer, e o Qt não dispara de novo um timer
  cujo disparo não terminou. O clique passou a ser agendado.
- **Uma mutação sobreviveu na primeira passada**: criar o PIN como filho da tela,
  e não do cartão. A suíte do cartão testava com uma barreira de mentira, e nada
  prendia a da view. Virou `test_o_pin_da_tela_nasce_filho_do_cartao`.

#### Conferência

- suíte **1893** (de 1794), 0 falhas, **99 testes a mais**:
  `tests/ui/test_confirmacao_exclusao_dialog.py` (as três imagens frase por
  frase, a contagem virando nível, as nove combinações entidade × nível, o PIN de
  verdade por cima do cartão, teclado, nada espremido nas seis variantes × dois
  temas com a fonte da marca, ciclo de vida), `tests/unit/test_produto_arquivado.py`
  (vínculos, arquivamento, os dois lados do combo, transação única, e o teste que
  diz em voz alta que as cascatas continuam SEM desamarrar) e a seção de exclusão
  de `test_barra_de_acoes_do_cardapio.py`, reescrita para o cartão com o fluxo
  real (`exec()`, PIN digitado, banco respondendo);
- **30 mutações, as 30 reprovam**. Na primeira passada 29 reprovaram; a
  sobrevivente virou teste (ver acima);
- memória sobre o cardápio do seed, `CardapioView` a 1366x738 com QSS e fonte:
  **300 ciclos** de cartão → PIN → cartão → cancelar, com widgets **73→73**,
  `QObject`s da tela **117→117** e **0 diálogos vivos**; RSS +0,69 MB no primeiro
  bloco de 60 e +0,04 a +0,13 MB nos quatro seguintes;
- tempo para montar e pintar o cartão: **~43 ms** nesta máquina, contra 4,4 ms do
  `QMessageBox` substituído e ~100 ms do cartão de organização do §9.12;
- renderização das nove variantes nos dois temas: 500px de largura, de 351px
  (bloqueada) a 419px (produto vendido em combo, com nome de duas linhas) de
  altura, bem abaixo dos 728px úteis;
- bancada visual a 1366x738 contra `b3e851f`: **24 telas idênticas byte a byte**
  (o item vive em diálogos); bancada de cupons: **2 idênticos** linha a linha.

#### Ficou de fora, de propósito

- **As cascatas continuam SEM desamarrar combo.** `excluir_categoria_em_cascata`
  e `excluir_subcategoria_em_cascata` arquivam o componente e deixam a linha de
  `combo_itens` de pé, que é exatamente a "referência ativa quebrada" que o Vitor
  mandou evitar na exclusão do produto. O pedido era sobre o produto, e estender
  a regra às cascatas é outra decisão dele. Está trancada em teste
  (`test_a_cascata_continua_sem_desamarrar`), para mudar só de propósito.
- **O erro do service depois de fechado o cartão** continua na linha vermelha da
  tela, como antes. O cartão é de uma abertura só, pelo achado acima.
- **A recusa de `excluir_produto`** ainda diz "Desative-o". A tela não chega mais
  a ela (o cartão sabe antes), só um instantâneo velho chegaria, e desativar
  continua sendo uma saída verdadeira.
- **Os `QMessageBox` que sobraram no app**: o "Produto já existe" do cadastro de
  produto (é aviso de duplicidade, não de exclusão), um da comanda e o erro de
  exportação do comprovante.
- **Desarquivar pela tela** — não existe lixeira (§9.13).

---

## 10. As melhores mudanças que o programa teve — em português de balcão

> **Por que esta seção existe.** Todo o resto do documento é escrito para quem
> vai mexer no código. Esta é a mesma remasterização contada para quem vai
> **usar** o programa: o que mudou no balcão, sem jargão. Nenhum número aqui é
> novo — todos vêm do §7 e das fases. É o resumo para mostrar ao pai do Vitor,
> e para o próprio Vitor lembrar, daqui a seis meses, o que estas 8 fases
> compraram.

### 1. O dinheiro parou de ter duas versões

A conta de "como escrever um valor em reais" existia **10 vezes copiada** — e
uma delas era diferente das outras: a tela de Mesas escrevia de um jeito e as
outras nove, de outro. Hoje existe **uma regra só**, `R$ 1.234,50`, em todas as
telas.

Mais sério que a aparência: a tela e o cupom impresso **arredondavam para lados
diferentes**. Dava para a tela mostrar `R$ 0,00` e o papel na mão do cliente
mostrar `0,01`. Hoje os dois passam pela mesma regra, e um teste reprova se
alguém separar de novo. (§3.8, Fase 3)

### 2. O sistema parou de poder gravar dado pela metade

Antes, quando uma operação falhava no meio, o que ela já tinha mexido ficava
pendurado — e a **próxima** operação gravava aquela sujeira junto com o dado
dela. Era o único achado da auditoria capaz de corromper dado de verdade. Hoje
toda operação desfaz o que fez quando falha.

Junto, o banco passou a **recusar ligação impossível** (um pagamento apontando
para uma comanda que não existe). Ligar isso revelou um defeito que dormia
desde uma migração antiga, invisível para os testes, que quebraria em produção.
(§3.1 e §3.5, Fase 1 e 2)

### 3. As telas pesadas ficaram rápidas — na máquina fraca

Medido num banco com **3 meses de operação real**:

| Tela | Antes | Depois |
|---|---|---|
| Dashboard Mensal | 2.502 consultas, 960 ms | **217 consultas, 108 ms** |
| Histórico do mês | 183 consultas, 127 ms | **79, 28 ms** |
| Grade de Mesas | 26 consultas, 22 ms | **16, 4 ms** |

O pior de todos buscava a comanda de **cada pagamento**, uma por uma: 1.326
consultas para montar um mês. Virou 6.

E gravar não ficou mais caro por causa disso: os índices triplicaram o custo de
escrita, o WAL devolveu tudo, e o resultado final **grava mais rápido que o
ponto de partida** (1,11 ms contra 1,17 ms por item lançado). (§7.1, Fase 2)

### 4. Perder o dia de vendas ficou muito mais difícil

- Backup automático **a cada fechamento de caixa**, guardando os 60 mais
  recentes — e um botão para gerar uma cópia na hora, antes de mexer no
  cardápio ou para levar num pendrive.
- O arquivo do banco fica **sempre completo no disco** com o programa fechado.
- A proteção contra **queda de energia no meio da gravação** foi mantida de
  propósito, contra a recomendação padrão que se lê por aí — porque o cenário
  do food truck é exatamente esse. Existe um teste que **mata o processo de
  verdade** no meio da escrita para provar. (§8, Fase 2)

### 5. Defeitos que o pai do Vitor veria, e que morreram

Nenhum destes é sutileza de código — todos aparecem na tela:

- **Cartão fantasma** sobrando na grade de Mesas e no rodapé do Caixa: um
  pedaço de tela que continuava pintado depois de deixar de existir.
- **Texto empilhado por cima de texto**: "CoCozinha", "SIM SIMONLI" — a célula
  nova desenhada em cima da antiga, no Cardápio e nas Impressoras. E um botão
  "2ª via" sobrevivendo numa tabela já esvaziada.
- **No tema Claro**, o título "Mesa 3" sumia no branco e o avatar mostrava a
  letra errada.
- **Configurações espremida**: os botões de senha viravam pílulas de 14px, sem
  rótulo nenhum, num monitor de 768px.
- **Recebimentos cortado ao meio** na tela de Caixa, na mesma altura de tela
  (§9).
- Uma **tela inteira invisível** (Estoque), montada toda vez que o programa
  abria e sem nenhum caminho até ela: peso morto no boot e no `.exe`.

### 6. A rede de segurança que não existia

Metade do código do sistema — as telas, ~8.000 linhas — **não tinha um único
teste**. Hoje tem 18 arquivos de teste, e a suíte foi de **621 testes com 1
falha para 800 verdes** (801 com o item do §9).

Isso não melhora nada hoje. Melhora tudo daqui para frente: é a diferença entre
mexer no sistema e descobrir o estrago no balcão, ou descobrir em 26 segundos
na máquina do Vitor.

E a prova final: as **11 telas em 24 estados** foram fotografadas e comparadas
pixel a pixel com o código de antes da faxina, e os **6 cupons** conferidos
linha a linha. Os cupons saem idênticos; das telas, as únicas diferenças são os
defeitos consertados. Mudou o que devia mudar, e **nada mais**. (Fase 7)

### 7. O achado mais importante foi um erro nosso

A auditoria dizia que o app vazava **40 MB de memória** e deixava 300 janelas
vivas. Acreditar nisso teria custado semanas caçando um fantasma. A medição
refeita provou que os três achados de memória **não existiam** — eram artefato
de medir sem o laço de eventos do Qt. O consumo real de 300 aberturas é **0,5
MB, com zero janelas vivas**.

O ganho é ter parado de perseguir o problema errado. E a bancada de medição
ficou versionada no projeto, com uma opção que reproduz a medição errada ao
lado da certa, para ninguém repetir. (§2.3, §3.2, §3.3 e §7.2)

---

**Em uma frase:** o sistema ficou mais rápido onde travava, parou de poder
gravar dado quebrado, ganhou backup automático, perdeu uma dúzia de defeitos
visíveis — e, o mais valioso, ganhou uma rede de testes que torna seguro
continuar mexendo nele.
