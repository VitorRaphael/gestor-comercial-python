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
> **Legenda de confiança dos achados:**
> ✅ **provado** — reproduzido nesta máquina, com saída de execução colada aqui.
> 🔍 **verificado** — código aberto e conferido linha a linha.
> ⚠️ **reportado** — levantado pela auditoria, ainda sem verificação independente.

---

## 0. Onde paramos — 2026-09-06

**Fases 0 a 6 concluídas. Falta só a Fase 7 (validação final).**
Suíte: **799 passando, 0 `xfail`, 0 falhas** — de 775 ao fim da Fase 5.

| Fase | Estado |
|---|---|
| 0 — Rede de segurança | ✅ concluída |
| 1 — Integridade de dados | ✅ concluída |
| 2 — Núcleo de dados e performance | ✅ concluída |
| 3 — Utilitários compartilhados | ✅ concluída |
| 4 — Ciclo de vida da UI (escopo enxuto) | ✅ concluída |
| 5 — Higiene da UI | ✅ concluída — 9 de 9 itens |
| 6 — Arquitetura da UI | ✅ **concluída — só a duplicação real** |
| **7 — Validação final** | ⏸️ **próxima**, sem decisão pendente bloqueando |

### O que a Fase 6 fechou

A fase começou como "quebrar as 5 views gigantes" e a medição mudou o alvo. Uma
varredura de **corpo de função** (pelo `ast.dump`, então o nome não conta) na
camada de UI inteira acusou **8 cópias** — e as 8 estavam entre as duas telas de
Relatórios. Nas cinco views gigantes: **nenhuma**.

| Item | O que entrou | Prova |
|---|---|---|
| Painéis do rodapé | `PainelGaveta` e `PainelAtendentes` em `ui/widgets/paineis_relatorio.py` | Teste de adoção nas 2 telas reais: cópia local de volta reprova |
| Linha com barra | `linha_barra_proporcao` — existia 2x com 2 nomes (`_criar_linha_forma`/`_criar_linha_atendente`) | 3 testes, incluindo a saturação em 0–100 |
| Barra de filtro | `FiltroPeriodoOperador` — dona do estado que as 2 telas duplicavam em 3 atributos cada | 5 testes: mês vigente primeiro, pílula sem destaque antes do 1º clique, volta pra "Todos" quando o operador some |
| Campo editável | `formatar_para_campo()` — as 2 cópias de `_formatar_campo` | Passa por `dinheiro()`, como manda o §3.8 |
| Diferença do turno | `ResumoCaixa.diferenca_total` — **3 regras divergentes** viraram 1 | Teste de premissa: as 2 contagens sempre viajam juntas |
| Catraca | Varredura que reprova quando um corpo de função é recolado entre arquivos da UI | Testada com uma cópia injetada; e com teste de premissa contra varredor cego |
| Bancada | `tools/comparar_telas.py` — paridade visual em PNG | 6 renderizações idênticas byte a byte ao código de antes |

### 🔴 O que a Fase 6 encontrou: a mesma conta com três regras

"Diferença total do turno" era calculada em três lugares, com três critérios
diferentes para o caso de faltar uma das duas contagens — e um deles somava
`Decimal + None`, que estoura. Não dá para escrever um teste que pegue isso:
as duas contagens sempre viajam juntas, então o caminho é **inalcançável
hoje** (pôr a regra antiga de volta deixa a suíte inteira verde). Virou uma
regra só em `ResumoCaixa.diferenca_total`, com um teste que trava a premissa e
avisa se o fechamento parcial um dia existir. Detalhe no §6, Fase 6.

### Por que as views gigantes continuam gigantes

Porque a varredura mostrou que elas não duplicam nada — nem entre si, nem com o
resto da UI. Quebrá-las seria mover ~4.500 linhas sem nenhum teste capaz de
dizer se melhorou. Decisão registrada no §8, não pendência.

### Retomada

Ler este bloco e a **Fase 7** no §6. Não há decisão pendente do Vitor
bloqueando. O empacotamento continua aberto: falta testar o `.exe` numa máquina
limpa de verdade (`docs/checklist-maquina-limpa.md`).

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

### Fase 7 — Validação final — FASE 4

- [ ] Suíte inteira verde
- [ ] Paridade tela a tela: Login, Mesas, Comanda, Caixa, Histórico, Dashboard,
      Cardápio, Funcionários, Impressoras, Configurações
- [ ] Impressão ESC/POS byte a byte idêntica (tipo ARQUIVO, `diff` dos `.txt`)
- [ ] Métricas do §7 preenchidas
- [ ] `docs/arquitetura.md` e `TODO.md` atualizados

---

## 7. Métricas de saída — FASE 4

| Métrica | Antes | Depois |
|---|---|---|
| Testes verdes | 620/621 (1 falha) | **799, 0 xfail, 0 falhas** (Fase 6) |
| Arquivos de teste de UI | 0 | **17** (Fase 6) |
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
| Telas com paridade visual provada pixel a pixel | 0 | **2**, em 6 estados (Fase 6) |
| "Constantes planas" de tema sem leitor | 14 de 22 | ✅ **bloco inteiro removido** (Fase 5) |
| Linhas em `src/` | 17.697 | **18.596** (+899) — ver nota |
| Linhas em `tests/` | 6.794 | **10.429** (+3.635) |

> **Sobre `src/` ter crescido 829 linhas.** Uma faxina que aumenta o código
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
