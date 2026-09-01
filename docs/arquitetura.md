# Arquitetura — Gestor Comercial Python

> Documento vivo. Atualizar sempre que uma decisão de escopo ou arquitetura mudar — é a fonte de verdade que guia qualquer sessão futura de desenvolvimento (humana ou de IA).

## 1. Contexto e relação com o Gestor Comercial (Java)

**Gestor Comercial Python é um projeto próprio e independente**: repositório próprio (`gestor-comercial-python`), pasta própria (`Gestor Comercial Python`), código-fonte próprio em Python. Ele **não edita nem depende em runtime** do [Gestor Comercial](../../GESTOR%20COMERCIAL) original (Java/Spring Boot) — aquele projeto continua existindo e intocado.

O que este projeto faz é **portar**, para uma stack Python, o conhecimento de domínio já validado no Gestor Comercial Java: as regras de negócio, os Casos de Uso e o Diagrama de Classes, além da identidade visual do front-end web. É um porte de conhecimento e design, não uma modificação do código-fonte Java.

**Motivação do porte (2026-08-20):** a máquina do food truck é fraca demais para rodar um servidor Spring Boot + PWA em rede local, e o Wi-Fi do local não é confiável. A arquitetura cliente-servidor do Gestor Comercial original está correta como *produto*, mas errada como *deployment* para este ambiente físico. A solução é portar as regras de negócio e a identidade visual para um aplicativo desktop standalone, de máquina única, 100% offline.

Uma tentativa anterior deste porte (pasta `PVD Python`, repositório `pvd-food-truck`) foi descartada porque partiu de um escopo simplificado "inspirado" no Gestor Comercial, em vez de portar o sistema real — e a pasta foi renomeada de `PVD Python` para `Gestor Comercial Python` em 2026-08-20 para eliminar essa ambiguidade de vez. Este documento reinicia do zero com esse erro corrigido.

## 2. Princípios não-negociáveis (RNFs)

1. **Otimização** — leve o suficiente para não pesar na máquina do food truck.
2. **Desempenho** — zero travamentos, resposta instantânea ao clique.
3. **Resiliência offline** — nenhuma operação de venda depende de rede. Tudo local.
4. **Confiabilidade** — tratamento de exceção robusto, validação de todo input, testado antes de produção real. Uma vez em produção oficial, não deve gerar erro.

## 3. Escopo da V1

Portado integralmente do Gestor Comercial, **exceto** os itens cortados abaixo (ver §5 Backlog).

### 3.1 Autenticação e Sessão
- **`Usuario` é a única entidade de login** — não confundir com `Funcionario` (§3.11), que não loga. Login por PIN numérico (hash SHA-256 + salt por usuário), sem usuário/senha tradicional.
- Usuário autenticado mantido em memória do processo (não há token HTTP — é um app de processo único).
- Reautenticação de PIN de Gerente para ações críticas, sem trocar o usuário da sessão principal.
- Perfis: `ADMIN` / `GERENTE` / `OPERADOR_CAIXA`. Ações administrativas (`exigir_gerente`) exigem `ADMIN` ou `GERENTE`.
- Não permite dois usuários ativos com o mesmo PIN.
- Migração de 2026-08-28 (separação Usuario/Funcionario): todo `ATENDENTE` existente virou `Usuario(OPERADOR_CAIXA)` — continuam logando normalmente. Atendentes/garçons sem login são cadastrados à parte como `Funcionario` (§3.11).

### 3.2 Cardápio — Categorias e Produtos
- CRUD de categoria (nome único); exclusão bloqueada se houver produtos vinculados; desativação soft.
- CRUD de produto (nome, preço, custo, categoria, descrição); desativação soft; exclusão bloqueada se já vendido ou é componente de combo.
- Associação de impressora à categoria (roteamento de impressão).

### 3.3 Combos
- Associação de componente a combo com quantidade.
- Regra: combo não pode conter a si mesmo, nem conter outro combo (máx. 1 nível de composição).

### 3.4 Mesas
- Conjunto fixo de mesas (seed inicial, sem criação/exclusão via UI na V1).
- Muda para `OCUPADA` no primeiro item lançado; volta a `LIVRE` ao fechar/cancelar a comanda.

### 3.5 Comandas
- Abertura vinculada a mesa (idempotente — reaproveita se já aberta) ou comanda de balcão (sem mesa).
- Fechamento: dá baixa (quando Estoque existir, na V2) e libera a mesa; bloqueia se já fechada.
- Cancelamento da comanda inteira (motivo + PIN de Gerente), cancela itens em cascata.
- Status: `ABERTA`, `FECHADA`, `CANCELADA`.

### 3.6 Itens de Comanda
- Lançamento de item (produto, quantidade, observação livre), com preço unitário **congelado** no momento do lançamento.
- Bloqueado se a comanda não estiver `ABERTA` ou o produto estiver inativo.
- Remoção física (só se comanda `ABERTA`); cancelamento individual soft (motivo + PIN de Gerente).

### 3.7 Pagamentos
- Registro de pagamento parcial/múltiplo até quitar 100% do total.
- Cálculo automático de troco (apenas em `DINHEIRO`).
- `CONSUMO_INTERNO` exige PIN de Gerente + funcionário consumidor; gera dívida rastreável.
- Fecha a comanda automaticamente ao quitar 100%.
- Formas: `CREDITO`, `DEBITO`, `DINHEIRO`, `PIX`, `CONSUMO_INTERNO`.

### 3.8 Consumo Interno / Quitação de Funcionários
- Devedor é sempre um `Funcionario` (§3.11, sem login) — não um `Usuario`. Consulta de saldo devedor e histórico de consumos/quitações — só gerente/admin logado (mesma exigência de §3.1).
- Quitação (total ou parcial, PIN de Gerente), abatendo os consumos mais antigos primeiro (FIFO).

### 3.9 Caixa
- Abertura (valor inicial), bloqueia se já houver caixa `ABERTO`. Grava `aberto_por_id` (quem declarou o fundo de troco).
- Fechamento (valor contado + observação), bloqueia se já fechado ou se houver comanda `ABERTA` com item lançado neste caixa (comanda vazia, sem item, não bloqueia — é rascunho). Grava `fechado_por_id`.
- Cálculo de saldo esperado (abertura + reforços − sangrias − despesas + dinheiro recebido). Consumo interno nunca desconta da gaveta: ele nunca foi dinheiro, é dívida rastreada só em `Pagamento`/`saldo_devedor` (§3.7/§3.8). `TipoMovimento.CONSUMO_FUNCIONARIO` existe no schema mas o registro manual dele é bloqueado, justamente para não descontar essa dívida da gaveta duas vezes.
- Cálculo do total vendido em maquininha (crédito + débito + PIX), e `totais_por_forma` para a quebra individual (Dinheiro, PIX, Débito, Crédito) do relatório e da tela de Histórico.

#### 3.9.1 Sequência diária de fechamentos e Histórico
- `Caixa.numero_sequencial_dia` é a ordem do fechamento dentro do dia **civil de `fechado_em`**, nunca de `aberto_em`: um turno aberto às 17h e fechado 01h do dia seguinte é o **1º fechamento do dia seguinte**, não do dia da abertura. Só existe depois de fechado, calculado uma única vez em `CaixaService.fechar` (contagem antes de sujar o próprio `caixa` no `Session`, senão o autoflush do SQLAlchemy contaria o caixa em fechamento como se já fosse um fechamento anterior) e nunca recalculado — fechar de novo o mesmo caixa já é bloqueado, então o número é imutável desde que gravado.
- `CaixaService.titulo_fechamento` monta a identificação oficial: `"Xº Fechamento do dia DD/MM/AAAA"`.
- `CaixaService.listar_historico(inicio, fim, usuario_id)` alimenta a tela de Histórico de Fechamentos: filtra por `fechado_em` (mesmo eixo da sequência diária) e por operador — casando com `aberto_por_id` OU `fechado_por_id`, porque quem consulta pode não lembrar qual das duas pontas do turno era o usuário procurado.
- App single-user/single-processo (mesma premissa de `UnitOfWork`, §"Repository"): não há concorrência real entre dois fechamentos, então a contagem-e-gravação dentro da mesma transação de commit é suficiente sem lock adicional.

### 3.10 Movimentos de Caixa
- Registro de `SANGRIA` / `REFORCO` / `DESPESA` / `CONSUMO_FUNCIONARIO`, vinculado ao caixa aberto.

### 3.11 Funcionários
- `Funcionario` é o colaborador de atendimento (garçom, cozinha, ...) — **não loga** (login é `Usuario`, §3.1). Serve só para vincular quem atendeu a comanda (`Comanda.atendente_id`, opcional) e para consumo interno (§3.8).
- Cadastro (nome, cargo livre, telefone opcional), edição, listagem de ativos/todos.
- Desativação soft: some da busca de atendimento, mas histórico (comandas atendidas, consumo, quitações) é preservado.
- Exclusão física, bloqueada se houver histórico vinculado (sugere desativar em vez de excluir).
- Tela de mesas/comanda mostra um seletor de busca rápida só com `Funcionario` ativos, para setar/trocar `Comanda.atendente_id` a qualquer momento (`ComandaService.definir_atendente`).

### 3.12 Impressoras e Roteamento
- **Cadastro de impressora** (`cardapio_service`, tela de Impressoras, tudo ação de Gerente): nome único, largura da bobina em colunas (32 = 58mm, 48 = 80mm), ativa/inativa, padrão, e os parâmetros de **5 tipos de conexão** — `USB` (vendor/product id), `SERIAL` (porta + baudrate), `REDE` (host + porta), `WINDOWS` (nome da fila instalada) e `ARQUIVO`. O tipo `ARQUIVO` grava o cupom num `.txt` legível e é o padrão de quem cadastra sem informar nada: permite rodar o food truck inteiro antes de a impressora física chegar.
- **Impressora padrão**: é quem recebe o recibo do cliente, o fechamento de caixa e o fallback de roteamento. O sistema mantém a invariante "havendo impressora ativa, uma delas é a padrão" nos quatro caminhos que podem quebrá-la — criar (a primeira nasce padrão), editar (desativar tira a marca), excluir (elege a próxima ativa) e a própria migration de dados.
- **Roteamento da comanda de produção** (porte de `RoteamentoImpressaoService.java`): os itens são agrupados por `item.produto.categoria.impressora`, preservando a ordem de lançamento — a cozinha lê o cupom na sequência em que o atendente digitou. Sai um cupom por impressora.
- **Fallback**: item cuja categoria não tem impressora (ou cuja impressora foi desativada) vai para a **impressora padrão**. Só quando não há padrão nenhuma o grupo vira um aviso acionável na tela ("associe uma impressora a essa categoria no Cardápio"), e mesmo assim os outros grupos imprimem normalmente. *DIVERGÊNCIA do Java*, que apenas logava o grupo órfão e o pedido nunca chegava na cozinha: comida que ninguém faz é pior do que um aviso na tela.
- **Imprimir só o que é novo (via de acréscimo)**: `ItemComanda.impresso_em` marca o que já foi para a produção. `imprimir_comanda` leva apenas itens não cancelados com `impresso_em IS NULL` — clicar duas vezes não repete o pedido, e nada novo não é erro (devolve lista vazia). O carimbo só é gravado nos grupos que **imprimiram com sucesso**, num commit único no fim: grupo que falhou continua NULL e sai de novo no próximo clique. `reimprimir_comanda` (2ª via) repete a comanda inteira e não mexe em `impresso_em`.
- Item já impresso não pode mais ser **removido** — só **cancelado**, que exige PIN de gerente e motivo (§3.6). Apagar do banco o que já está na chapa apagaria a venda sem deixar rastro.
- **Escopo dos cupons**: comanda de produção (cozinha), recibo do cliente (itens, total, pagamentos por forma, troco) e relatório de fechamento de caixa (abertura, total por forma, sangrias/reforços/despesas, saldo esperado — números vindos prontos do `caixa_service`, sem recalcular).
- **RNF inegociável**: falha de impressora nunca derruba a venda. `ErroDeImpressao` fica presa em `hardware/` + `impressao_service` e vira `ResultadoImpressao(sucesso=False)` com mensagem para o operador; só `RecursoNaoEncontradoError` e `NaoAutorizadoError` sobem.
- **A impressão roda na thread da UI**, com cursor de espera e timeout curto (3 s), e não em `QThread`: o app usa um único `UnitOfWork`/`Session` por processo, e `Session` do SQLAlchemy não é thread-safe — jogar isso para outra thread trocaria um congelamento de 3 s por corrupção de dados.

## 4. Diagramas de referência

- **Diagrama de Casos de Uso** — construído com o Jarvis (Gemini), mapeando Atendente/Gerente e os fluxos `Include`/`Extend`. Ver histórico da conversa (a ser colado/anexado aqui quando exportado).
- **Diagrama de Classes (V1)** — publicado como artifact: <https://claude.ai/code/artifact/ef046c14-4e1e-42fb-a27c-8b7c9bf1ddda>. Cobre Funcionario, Mesa, Comanda, ItemComanda, Produto, Categoria, ComboItem, Pagamento, Caixa, MovimentoCaixa, QuitacaoConsumo, Impressora e suas multiplicidades.

> As entidades em `src/gestor_comercial/domain/` devem espelhar 1:1 as classes desse diagrama.

## 5. Backlog — fora da V1

Nesta ordem de prioridade, para versões futuras:

1. **App Mobile do Atendente** — camada de API/sessão remota, para bater pedido fora do caixa central sem sobrecarregar um único ponto.
2. **Controle de Estoque** — entidades `MateriaPrima` e `MovimentoEstoque`, entrada de compra, ajuste manual.
3. **Ficha Técnica** — vínculo Produto ↔ MateriaPrima e baixa automática recursiva (direta e via componentes de combo).
4. **Foto do produto** — o Java tinha upload de foto (`Produto.fotoUrl`); o domain Python não tem esse campo. Cortado da V1 porque o app é uma lista/grid lida de perto no balcão, não uma vitrine para cliente — corte reavaliável se a tela de cardápio pedir imagem.

Cortados deliberadamente da V1 para reduzir a superfície de teste e entregar um sistema real operando o quanto antes — não são "esquecidos", são adiados.

## 6. Arquitetura técnica

```
PySide6 (UI)  →  Camada de Serviços (regras de negócio)  →  SQLAlchemy (ORM)  →  SQLite (arquivo local)
                                                                                        ↓
                                                                              python-escpos → Impressora
```

- Aplicativo desktop standalone, single-machine, 100% offline. Sem servidor, sem API REST.
- A "camada de serviços" cumpre o papel que os `@Service` do Spring cumpriam no projeto original, chamada diretamente pela UI, em memória.
- Empacotado com **PyInstaller** em um `.exe` único.
- PIN validado localmente contra a tabela `funcionarios`; sessão de usuário logado mantida em memória do processo, não em token HTTP.

### Árvore de pastas

```
gestor-comercial-python/
├── pyproject.toml
├── alembic.ini
├── .gitignore
├── README.md
│
├── migrations/
│   └── versions/
│
├── resources/
│   ├── qss/
│   │   ├── base.qss
│   │   ├── mesas.qss
│   │   └── comandas.qss
│   ├── icons/
│   └── fonts/
│
├── src/
│   └── gestor_comercial/
│       ├── __init__.py
│       ├── main.py
│       │
│       ├── domain/                # Model — entidades SQLAlchemy puras
│       │   ├── funcionario.py
│       │   ├── mesa.py
│       │   ├── comanda.py
│       │   ├── item_comanda.py
│       │   ├── produto.py
│       │   ├── categoria.py
│       │   ├── combo_item.py
│       │   ├── pagamento.py
│       │   ├── caixa.py
│       │   ├── movimento_caixa.py
│       │   ├── quitacao_consumo.py
│       │   ├── impressora.py
│       │   └── enums.py
│       │
│       ├── repository/            # Repository/DAO — único lugar com Session SQLAlchemy
│       │   ├── base.py
│       │   ├── comanda_repository.py
│       │   ├── caixa_repository.py
│       │   ├── produto_repository.py
│       │   └── funcionario_repository.py
│       │
│       ├── services/              # Service — regras de negócio
│       │   ├── auth_service.py
│       │   ├── comanda_service.py
│       │   ├── pagamento_service.py
│       │   ├── caixa_service.py
│       │   ├── cardapio_service.py
│       │   ├── impressao_service.py
│       │   └── formatador_cupom.py   # funções puras: centralizar, alinhar preço, quebrar na largura
│       │
│       ├── hardware/              # isolamento de periféricos físicos
│       │   └── impressora_escpos.py  # 5 tipos de conexão + BlocoTexto/Documento
│       │
│       ├── ui/                    # Controller/View — PySide6, zero SQL
│       │   ├── main_window.py
│       │   ├── views/
│       │   │   ├── login_view.py
│       │   │   ├── mesas_view.py
│       │   │   ├── comanda_view.py
│       │   │   ├── pagamento_dialog.py
│       │   │   ├── caixa_view.py
│       │   │   ├── cardapio_view.py
│       │   │   ├── funcionarios_view.py
│       │   │   └── impressoras_view.py
│       │   └── widgets/
│       │       ├── mesa_card.py
│       │       └── pin_dialog.py
│       │
│       └── config/
│           └── settings.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
└── packaging/
    └── build.spec
```

### Responsabilidade das camadas

- **`domain/`** — entidades SQLAlchemy, reflexo 1:1 do Diagrama de Classes. Sem lógica de negócio, sem query.
- **`repository/`** — único lugar que abre `Session`, faz `query()`/`commit()`. Services nunca tocam SQLAlchemy diretamente.
- **`services/`** — regras de negócio: troco, cancelamento, fechamento de caixa. Equivalente aos `@Service` do Java.
- **`hardware/`** — isolamento do `python-escpos`. Trocar de impressora/protocolo no futuro afeta só este arquivo.
- **`ui/`** — só PySide6. Toda `view` chama um `service`, nunca um `repository` ou SQL direto.
- **`resources/qss/`** — réplica visual do front-end web do Gestor Comercial (`GESTOR COMERCIAL/src/main/resources/static/desktop/`), usado como referência obrigatória ao construir cada tela — não inventar layout novo.

## 7. Stack técnica e justificativas

| Decisão | Escolha | Por quê |
|---|---|---|
| GUI | PySide6 | Licença LGPL (permite fechar o código se comercializar depois, ao contrário do PyQt5/GPL); componentes nativos robustos para grids/tabelas/modais (mesas, comandas, extrato de caixa). |
| ORM | SQLAlchemy + Alembic | Equivalente direto ao JPA/Hibernate já usado no Gestor Comercial Java; migrações versionadas sem perder dados reais de vendas ao evoluir o schema (essencial para a V2 com Estoque). |
| Banco | SQLite | Arquivo único local, sem servidor, alinhado ao princípio de resiliência offline. |
| Impressão | python-escpos | Biblioteca dedicada a comandos ESC/POS, portátil entre USB/Serial/Rede. |
| Empacotamento | PyInstaller | Gera `.exe` único, sem exigir Python instalado na máquina do food truck. |
| Modo de trabalho | Write mode | Vitor decidiu que, neste projeto, o Claude escreve o código diretamente — decisões de arquitetura/escopo ficam com ele. |

## 8. Estado do documento

- 2026-08-20 — Documento criado do zero após descarte total da tentativa anterior de `PVD Python`. Escopo, stack e árvore de pastas aprovados por Vitor.
- 2026-08-20 — Fase 1 iniciada: `domain/enums.py` e as 12 entidades SQLAlchemy criadas 1:1 a partir do Diagrama de Classes do artifact. `repository/base.py` com engine SQLite (`~/.gestor_comercial/gestor_comercial.db`) + sessionmaker. `.venv` criado e projeto instalado em modo editável (`pip install -e .`); `Base.metadata.create_all()` testado e cria as 12 tabelas sem erro.
- 2026-08-20 — Alembic configurado (`alembic init migrations`, `env.py` apontando para `Base.metadata` e `DB_PATH`). Primeira migration autogerada (`1eb3a1232a49_schema_inicial_v1.py`) e testada com `alembic upgrade head` em banco limpo — as 12 tabelas + `alembic_version` foram criadas.
- 2026-08-20 — Corrigida ambiguidade de FK em `Funcionario.quitacoes` (`quitacoes_consumo` tem duas FKs para `funcionarios`: `funcionario_id` e `autorizado_por_id`) especificando `foreign_keys` na relationship.
- 2026-08-20 — `repository/seed.py` criado, portando fielmente o seed do Java (`MesaSeeder`/`FuncionarioSeeder`): 60 mesas numeradas 1–60, e funcionário "Gerente" (perfil GERENTE, PIN padrão `264072`) usando o mesmo esquema de hash SHA-256(salt+pin) com salt aleatório de 16 bytes em Base64. Idempotente (não duplica mesas nem cria admin se já houver funcionário). Testado 2x seguidas — sem duplicação. **Atenção**: PIN padrão `264072` é o mesmo hardcoded do Java, deve ser trocado antes de produção real assim que existir tela de troca de PIN.
- 2026-08-20 — **Fase 1 concluída.** `tests/conftest.py` (fixture `session` com SQLite em memória) + `tests/integration/test_entidades.py` com 7 testes cobrindo criação/consulta das 12 entidades e seus relacionamentos (inclusive os dois casos de FK dupla: `ComboItem` combo/produto e `QuitacaoConsumo` funcionário/autorizador). `pytest` instalado no `.venv`; 7/7 passando. Próximo: Fase 2 — Services (`auth_service.py` primeiro, pois `cardapio_service`/`comanda_service` dependem de autenticação para ações de Gerente).
- 2026-08-20 — Domain ganhou 4 campos que a Fase 2 exigia e o diagrama original não tinha: `Pagamento.troco`/`valor_quitado` (§3.7/§3.8 — quitação FIFO precisa saber quanto de cada consumo já foi pago), `Comanda`/`ItemComanda.cancelado_em`+`cancelado_por_id` (auditoria de quem autorizou o cancelamento, §3.5/§3.6) e `Caixa.aberto_em`/`fechado_em` (ordenar caixas, montar extrato do turno). Migration `a6108ce87d55` — as duas colunas `NOT NULL` novas entram em 3 passos (nullable → backfill → aperta) para não quebrar em banco com venda real; testada com upgrade/downgrade/upgrade sobre linhas pré-existentes. `migrations/env.py` ganhou `render_as_batch=True` (obrigatório pro SQLite aceitar `ALTER COLUMN`).
- 2026-08-20 — Camada `repository/` criada: classe genérica `Repository[T]` (único lugar que fala SQLAlchemy) + 11 repositories com os finders portados do Java + `UnitOfWork` agrupando todos numa única `Session` (pagamento que fecha comanda e libera mesa é tudo-ou-nada). `services/exceptions.py` com as 4 exceções portadas.
- 2026-08-20 — **Fase 2 concluída: os 5 services** (`dinheiro.py`, `auth_service.py`, `cardapio_service.py`, `comanda_service.py`, `caixa_service.py`, `pagamento_service.py`) escritos em paralelo contra um contrato de assinaturas fixo, com 306 testes. Revisão adversarial (3 lentes independentes) achou 9 problemas reais, todos corrigidos na mesma sessão — suíte final com **319 testes, 100% verde**:
  - Escalação de privilégio: `AuthService.criar_funcionario`/`desativar_funcionario` não exigiam gerente (corrigido com exceção de bootstrap pro primeiro cadastro do sistema).
  - `ComandaService.fechar()` fechava comanda com saldo não pago, perdendo a venda em silêncio (agora exige quitação total ou PIN de gerente pra fechar fiado).
  - Comanda que zerava o restante por cancelamento de item (não por pagamento) ficava presa — não fechava, não cancelava, travava o fechamento do caixa (resolvido como efeito colateral do fix acima: `fechar()` sem saldo em aberto não exige PIN).
  - `TipoMovimento.CONSUMO_FUNCIONARIO` descontava a gaveta duas vezes (a dívida já é rastreada só via `Pagamento`/`saldo_devedor`) — registro manual desse tipo agora é bloqueado.
  - `CaixaService.fechar()` travava com comanda vazia (rascunho invisível em toda tela) — agora só bloqueia comanda `ABERTA` com item.
  - `dinheiro()` deixava `decimal.InvalidOperation` escapar sem tratamento para valores gigantes — ganhou teto de `99999999.99` (mesmo limite do `NUMERIC(10,2)` do domain).
  - `CardapioService` tratava preço em `float` como erro de digitação em vez de erro de programação (inconsistente com caixa/pagamento) — alinhado.
  - Consulta de saldo devedor/extrato de consumo interno não exigia gerente — corrigido (§3.8 atualizado).
  - `docs/arquitetura.md §3.2` prometia upload de foto que nunca foi implementado — corte movido pro §5 (Backlog).
  Próximo: Fase 3 — Interface PySide6 (Views), começando por `login_view.py` (PIN pad) e `mesas_view.py`.
- 2026-08-20 — `login_view.py` criado: pin pad numérico ligado a `AuthService.login()`. Testado com banco SQLite descartável (login correto, PIN errado, apagar/limpar) via smoke test headless (`QT_QPA_PLATFORM=offscreen`).
- 2026-08-20 — `mesas_view.py` criado: grid responsivo de mesas (recalcula colunas no `resizeEvent`, mesma ideia de `repeat(auto-fill, minmax(120px,1fr))` do CSS original) + botão Balcão, ligados a `ComandaService.abrir_por_mesa`/`abrir_balcao`. `ComandaService` ganhou `listar_mesas()` (view nunca toca repository direto, regra de §6). Revisão adversarial (2 lentes: regras de negócio e correção Qt) achou 1 problema real, corrigido: a view só capturava `RegraDeNegocioError`/`RecursoNaoEncontradoError`, deixando `NaoAutorizadoError` (sem funcionário logado) propagar e derrubar a UI — agora as três são tratadas. Smoke test headless cobre: 60 mesas livres no boot, abrir comanda por mesa, idempotência (2º clique não duplica), mesa **permanece LIVRE** ao abrir comanda (regra §3.4: só fica OCUPADA no 1º item lançado — confirmado contra `test_lancar_item_ocupa_a_mesa`), balcão, e os dois caminhos de erro (sem login / sem caixa aberto). 319 testes da suíte inteira continuam verdes. Próximo: `comanda_view.py`.
- 2026-08-20 — `comanda_view.py` criado: tabela de itens (descrição/preço/qtd/total + botão remover) com total ao rodapé, e modal `+ Item` (`_AdicionarItemDialog`) com combo de produto ativo, quantidade (`QSpinBox`) e observação livre, ligados a `ComandaService.listar_itens`/`calcular_total`/`lancar_item`/`remover_item`. Fechamento, cancelamento e pagamento ficam fora de propósito (entram em `pagamento_dialog.py` e no modal de cancelamento, próximos itens da Fase 3). Smoke test headless cobre: comanda vazia, item lançado aparece na tabela e no total, dados do modal, remoção de item atualizando tabela/total. 319 testes da suíte inteira continuam verdes. Próximo: `pagamento_dialog.py`.
- 2026-08-21 — **Fase 4 concluída: impressão de verdade (§3.12).** `domain/enums.py` ganhou `TipoConexaoImpressora` (USB/SERIAL/REDE/WINDOWS/ARQUIVO); `Impressora` deixou de ser só um nome e passou a guardar os parâmetros de conexão + largura da bobina + `ativa`/`padrao` (nome agora UNIQUE, como no Java); `ItemComanda` ganhou `impresso_em`. Migration `06b890e91ef1` (batch_alter_table, NOT NULL em 3 passos, downgrade funcional, testada com upgrade/downgrade sobre impressoras pré-existentes). Novos: `hardware/impressora_escpos.py` (única fronteira com o `python-escpos`, import tardio), `services/formatador_cupom.py` (funções puras de largura), `services/impressao_service.py` (roteamento, fallback, via de acréscimo, 2ª via, recibo, fechamento, teste) e `ui/views/impressoras_view.py`. Revisão adversarial (revisão + refutação) achou 8 problemas reais, todos corrigidos na mesma sessão — suíte final com **487 testes, 100% verde**:
  - **Crítico**: `_DriverEscpos` ligava o tamanho dobrado (número da mesa) e nunca desligava — o `set()` do python-escpos só emite comando de tamanho quando `normal_textsize`/`double_*` é verdadeiro, e com os três falsos não manda nada. O cupom inteiro, e o cupom seguinte, sairiam dobrados e cortados pela bobina até alguém desligar a impressora da tomada. Corrigido passando `normal_textsize` explicitamente em todo bloco, mais um `hw('INIT')` no começo de cada cupom; coberto com teste que lê os bytes ESC/POS no `Dummy`.
  - **Alto**: item já enviado para a produção podia ser apagado por qualquer atendente via `remover_item`, sem PIN e sem rastro — desviava comida sem deixar registro, contornando toda a auditoria de `cancelar_item`. `remover_item` agora barra item com `impresso_em`, e o botão "Remover" da comanda fica desabilitado com a explicação.
  - **Alto**: `SERIAL` era aberta sem `write_timeout` (no pyserial o `timeout` limita só a leitura) e com `dsrdtr=True` — impressora desligada em COM3 bloqueava a escrita para sempre, congelando a janela do PDV, já que a impressão roda na thread da UI. Corrigido impondo `write_timeout` logo após o `open()` e desligando o controle de fluxo por hardware.
  - **Médio**: no driver `WINDOWS` é o `close()` que faz `EndDocPrinter`, ou seja, é ele que efetiva o job — e o `close` estava sempre dentro de um `suppress(Exception)`, inclusive no caminho feliz. Spooler caído devolvia `sucesso=True`, marcava `impresso_em` e escondia para sempre um pedido que nunca saiu. Agora o `suppress` só vale quando já há exceção em curso.
  - **Médio**: a migration marcava todas as impressoras existentes como não-padrão e não elegia nenhuma — instalação que já rodava a Fase 3 ficava sem padrão, e recibo, fechamento e fallback paravam em silêncio. Passou a eleger a mais antiga.
  - **Médio**: `excluir_impressora` apagava a padrão sem eleger outra, quebrando a mesma invariante que criar/editar mantêm.
  - **Baixo**: nome da impressora ia direto para o cabeçalho do cupom sem passar pelo `formatador_cupom` (campo de 80 caracteres numa bobina de 20–48) — mesma inconsistência corrigida junto na instrução do cupom de teste.
  - **Baixo**: comentário da migration sobre `impresso_em` ensinava a regra invertida (dizia que NULL impedia o item de aparecer como novo, quando NULL é exatamente o que o faz aparecer).
  Falta só o teste manual com a impressora física, que depende do hardware que o Vitor ainda não tem — o tipo de conexão `ARQUIVO` cobre o fluxo inteiro até lá. Próximo: Fase 5 — empacotamento (PyInstaller).
- 2026-08-22 — **Fase 5 iniciada: empacotamento.** `packaging/build.spec` criado e validado com um build local real (`GestorComercial.exe`, ~69 MB, onefile). `main.py` ganhou `_raiz_recursos()`: em dev continua resolvendo a raiz do repo por `__file__`, mas rodando empacotado usa `sys._MEIPASS` — sem isso o `.exe` não acharia `alembic.ini`/`migrations/`/`resources/qss/base.qss`, que viajam no bundle via `datas` do spec. No caminho apareceu um bug real: o `.exe` abria e caía direto no diálogo "Erro ao iniciar" com `No module named 'logging.config'`, porque `migrations/env.py` só existe pro PyInstaller como arquivo de dado — o Alembic executa ele em runtime, e os imports de dentro dele não entram na análise estática do spec. Corrigido adicionando `logging.config` (e os módulos que o `python-escpos`/Windows-printing importam sob demanda: `escpos.printer`, `win32print`, `win32ui`) em `hiddenimports`. Build final (`console=False`) testado rodando o `.exe` isolado: sobe, aplica as migrations, roda o seed e cria `~/.gestor_comercial/gestor_comercial.db` sem erro — mas isso ainda é a máquina de dev, não prova nada sobre uma máquina sem Python (roteiro em `docs/checklist-maquina-limpa.md`, ainda não executado).
  Resiliência a queda de energia automatizada em `tests/integration/test_resiliencia_queda_energia.py`: sobe um processo Python real, escreve uma `Mesa`, e o processo de teste mata esse processo à força (`TerminateProcess`, sem cleanup) logo depois do `flush()`/`commit()` — a aproximação mais realista de queda de energia que dá pra automatizar sem desligar a máquina de verdade. Prova duas coisas sobre o SQLite puro (sem lógica nossa por trás — só não desligamos `synchronous`/`journal_mode` padrão nem commitamos cedo demais): escrita sem commit é desfeita sozinha ao reabrir o arquivo (rollback journal), escrita commitada sobrevive. Suíte em **489 testes, 100% verde**. Próximo: rodar `docs/checklist-maquina-limpa.md` numa máquina Windows de verdade sem Python instalado.
