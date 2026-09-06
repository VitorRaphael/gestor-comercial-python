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
| `PRAGMA foreign_keys` | ✅ **0 — desligado.** As 38 FKs do schema não são aplicadas |
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

### 3.2 🔴 Os 31 modais nunca são destruídos

**Severidade: ALTA.** ✅ **provado.** É o vazamento dominante de memória — e é
exatamente o que o briefing suspeitava, só que em Qt.

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

### 3.3 🔴 `setCellWidget` não destrói o widget anterior no PySide6

**Severidade: ALTA.** ✅ **provado** — e é mais frequente que o §3.2, porque
dispara a cada `atualizar()` de tela, não a cada clique do usuário.

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

### 3.5 🔴 Zero índices contra 38 chaves estrangeiras

**Severidade: ALTA.** ✅ **provado.** É a causa raiz da degradação com o tempo
— o problema que o briefing chama de "operar semanas sem degradar".

```
index=True no domain/ ......... 0
Index() / __table_args__ ...... 0
create_index nas migrations ... 0
ForeignKey declaradas ......... 38
```

O SQLite cria índice sozinho para PK e UNIQUE, **nunca para FK**. Então toda
consulta quente (`comanda.itens`, `listar_por_caixa`, `pagamento.comanda`,
`mesa.comandas`) é **varredura de tabela inteira**. Hoje, com o banco pequeno,
não dói. Depois de meses de operação, cada uma dessas varreduras cresce
linearmente — e elas rodam dentro de laços N+1 (§3.6).

> Nota: `TODO.md` afirma que `caixas.numero_sequencial_dia` é "indexado por
> `fechado_em`". **Não é** — não existe índice nenhum no projeto. Corrigir a doc.

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

### 3.7 🟠 Quatro a seis cópias do "limpar layout", com comportamentos divergentes

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

**Correção:** `ui/widgets/layout_utils.py` com a versão corrigida
(`setParent(None)` + `deleteLater()` + sub-layouts recursivos), e todos os sites
importando dele.
**Cuidado:** `mesas_view.py:421-424` usa `while layout.count() > 1` porque o
último item é um stretch fixo — o helper genérico precisa preservar isso.

### 3.8 🟠 Dez cópias de `_formatar_reais` — e uma delas diverge

**Severidade: MÉDIA (bug visível ao usuário).** ✅ **provado.**

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

### 3.9 🟠 PIN do gerente fica em texto claro na memória para sempre

**Severidade: ALTA.** 🔍 verificado. `ui/widgets/gerente_pin_dialog.py:72-76`

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

Aplicar idêntico em `loja_pin_dialog.py:74-78`. Necessário **mas não
suficiente** — sem o §3.2 o widget continua vivo.

### 3.10 🟠 Cache de miniaturas: teto OK, chave errada

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

### 3.11 🟡 Tela fantasma: `EstoqueView` é inalcançável

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

**Decisão pendente:** remover até a fase de Estoque começar, ou manter e
documentar como placeholder consciente?

### 3.12 🟡 Código morto, QSS órfão e documentação que mente

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

### 3.14 🟡 Assinantes do tema por lambda sem receptor

**Severidade: MÉDIA (armadilha latente, não vazamento ativo).** 🔍 verificado.

`grep -rn "disconnect" src` → **zero**. Os dois assinantes de `ThemeController.mudou`
são lambdas sem objeto receptor (`login_view.py:313`, `configuracoes_view.py:130`).
Hoje **não cresce**, porque os receptores também vivem o processo inteiro. Vira
vazamento no instante em que alguém recriar uma dessas telas.

**Preservar:** a linha 130 forma realimentação (`mudou` → `setChecked` →
`toggled` → `alternar_para`) que **só não entra em laço infinito por causa da
guarda `if claro == self._claro: return`** (`controller.py:53-54`).

### 3.15 🟡 Cores de tema congeladas em `setStyleSheet` inline

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

### Fase 2 — Núcleo de dados e performance

- [ ] Índices nas 38 FKs, via migration Alembic (§3.5)
- [ ] **Decidir sobre `journal_mode = WAL`** — medido na Fase 1: `delete`
      (atual) gasta **1,17 ms** por ação gravada, WAL gasta **0,11 ms** (10x).
      O ganho relativo é grande, mas 1 ms por lançamento de item é
      imperceptível para o operador. Contra: o WAL guarda transações recentes
      num arquivo `-wal` separado, então **copiar só o `.db` para um pendrive
      com o app aberto perde as últimas vendas** — armadilha real para um dono
      não-técnico. Depende de como o backup vai ser feito no food truck
- [ ] Corrigir `TODO.md`, que afirma um índice que não existe
- [ ] `selectinload`/`joinedload` nos N+1 do §3.6, começando por
      `mesas_view.py:371` (tela principal) e `caixa_service.resumo_mensal`
- [ ] Medir queries antes/depois de cada correção e registrar no §7
- [ ] Suíte verde, **contrato do §4 conferido**

### Fase 3 — Utilitários compartilhados

- [ ] `ui/formatacao.py` — centralizar as 10 cópias de `_formatar_reais` + as 2
      com sinal (§3.8) — **decidir o formato antes** (§8)
- [ ] `ui/widgets/layout_utils.py` — helper único de limpeza (§3.7)
- [ ] `ui/widgets/modais.py` — `executar_modal()` (§3.2)
- [ ] `ui/widgets/tabelas.py` — limpeza de tabela que destrói cell widgets (§3.3)
- [ ] Testes de unidade dos quatro

### Fase 4 — Ciclo de vida da UI 🔴

- [ ] `executar_modal()` nos 31 sites (§3.2)
- [ ] Limpeza de tabela nas 6 views com tabela (§3.3)
- [ ] `closeEvent` → `done()` nos dois diálogos de PIN (§3.9)
- [ ] Unificar as cópias de `_limpar_layout` (§3.7)
- [ ] Lambdas do tema → métodos ligados (§3.14), **mantendo a guarda anti-laço**
- [ ] **`tests/ui/test_vazamento_*.py` passam a verde** ← critério de pronto
- [ ] Medir RSS com o roteiro do §2.3 e registrar o "depois"

### Fase 5 — Higiene da UI

- [ ] Chave do cache de miniaturas (§3.10)
- [ ] Decidir o destino de `EstoqueView` (§3.11)
- [ ] Código morto, QSS órfão, constantes não lidas (§3.12)
- [ ] **Corrigir os comentários que mentem** (§3.12) — especialmente
      `auth_service.py:50-52`, que convida a uma limpeza que quebra o boot
- [ ] Cores inline → QSS global (§3.15)
- [ ] Tipagem `typing` nas funções públicas; nomes autoexplicativos
- [ ] `gc.collect()` **apenas** na destruição de telas pesadas, **se a medição
      mostrar ganho** — não por dogma

### Fase 6 — Arquitetura da UI

- [ ] Quebrar views gigantes **só onde compensar** (`cardapio_view` 1.343,
      `comanda_view` 953, `funcionarios_view` 759, `caixa_view` 744,
      `impressoras_view` 744)
- [ ] Camadas: **nada a fazer** — já está limpo (§3.13)

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
| Testes verdes | 620/621 (1 falha) | **633 + 7 xfail, 0 falhas** (Fase 1) |
| Arquivos de teste de UI | 0 | **3** (Fase 0) |
| Caminhos de produção com `rollback()` | 0 | **todos** (Fase 1) |
| `PRAGMA foreign_keys` no app real | 0 | **1** (Fase 1) |
| Widgets na tabela do Cardápio após 20 recargas | 138 → **1.338** | _a preencher (Fase 4)_ |
| RSS do shell montado | 154,5 MB | _a preencher_ |
| RSS após 300 modais | 195,3 MB (+40,8) | _a preencher_ |
| Modais vivos após 300 aberturas | 300 | **0** (meta) |
| Cell widgets vivos após 50 refreshes | 50 | **0** (meta) |
| Linhas em `src/` | 17.697 | _a preencher_ |
| Cópias de `_formatar_reais` | 10 (+2 com sinal) | 1 (+1) (meta) |
| Cópias de "limpar layout" | 4–6 | 1 (meta) |
| Índices em FK | 0 de 38 | _a definir_ |
| `PRAGMA foreign_keys` | 0 | ✅ 1 (Fase 1) |
| Caminhos com `rollback()` | **0** | ✅ todos (Fase 1) |

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
| 2026-09-06 | 5 `.md` de refatoração → `docs/historico/` com README de aviso | Documentação que contradiz o código convida a uma "limpeza" que quebra o app; arquivar preserva o porquê das decisões sem poluir a raiz (§3.12) |

### Decisões pendentes do Vitor

1. **Formato monetário** (§3.8) — *bloqueia a Fase 3*: `R$ 1234,50` (9 telas
   hoje) ou `R$ 1.234,50` (tela de Mesas)? Recomendo o segundo; muda a
   aparência de 9 telas.
2. **`EstoqueView`** (§3.11) — *bloqueia a Fase 5*: remover até a fase de
   Estoque começar, ou manter como placeholder consciente e documentado?
