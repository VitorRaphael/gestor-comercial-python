# Plano de Implementação — Gestor Comercial Python

> Progresso da V1. Marcar `[x]` conforme cada etapa for concluída e testada. Detalhes de regras/escopo em [`docs/arquitetura.md`](docs/arquitetura.md).

> **2026-09-06 — Remasterização da V1.0 em andamento.** A faxina final antes da
> produção (memória, integridade de dados, duplicação, código morto) tem plano
> próprio em [`REMASTERIZACAO-V1.md`](REMASTERIZACAO-V1.md), com 8 fases e
> contrato de zero-regressão. Suíte: **706 passando + 7 `xfail`** — e a Fase 3
> descobriu que esses 7 medem a coisa errada: ver a nota da Fase 3 abaixo.
> **Paramos no início da Fase 4**, aguardando decisão de escopo — o estado
> completo está no §0 do [`REMASTERIZACAO-V1.md`](REMASTERIZACAO-V1.md).
>
> - **Fase 0** — a camada `ui/`, que não tinha nenhum teste, ganhou rede (`tests/ui/`).
> - **Fase 1** — `rollback()` passou a existir em produção (`@transacional`) e
>   `PRAGMA foreign_keys` foi ligado.
> - **Fase 2** — índices nas 20 FKs, `journal_mode = WAL` + rotina de backup
>   (`VACUUM INTO` no fechamento de caixa e sob demanda em Configurações), e a
>   eliminação dos N+1: **Dashboard Mensal caiu de 2.502 para 217 consultas**.
>   Também consertou uma FK apontando para a tabela errada que só existia no
>   banco migrado — invisível para a suíte, quebra em produção.
> - **Fase 3** — quatro utilitários compartilhados (`ui/formatacao.py`,
>   `layout_utils`, `modais`, `tabelas`) + 48 testes. O dinheiro passou a
>   aparecer como **`R$ 1.234,50`** nas 10 telas, acabando com a divergência em
>   que a tela de Mesas mostrava um formato e as outras nove, outro.
>   **A fase também derrubou dois achados do diagnóstico:** as tabelas não
>   vazam e os modais só vazam por um caminho que o app não percorre — as
>   medições originais rodaram sem laço de eventos, e sem laço `deleteLater()`
>   nunca sai do papel. A Fase 4 caiu de 🔴 para 🟡.

> **2026-08-28 — Refatoração Usuario/Funcionario:** `Funcionario` (Fases 1-3 abaixo)
> foi cindida em `Usuario` (login/PIN, tela de login) e `Funcionario` (atendimento,
> sem login). Os itens marcados `[x]` abaixo que mencionam "Funcionario" descrevem
> o estado *antes* dessa cisão — ver §3.1/§3.11 de `docs/arquitetura.md` para o
> estado atual. Migration: `d23a4f888a77`.

## Fase 0 — Setup do repositório
- [x] `.gitignore` (Python/PySide6/venv/PyInstaller)
- [x] `README.md`
- [x] `docs/arquitetura.md`
- [x] `TODO.md`
- [x] `git init` + commit zero (Vitor)
- [x] `pyproject.toml` com dependências (PySide6, SQLAlchemy, Alembic, python-escpos, pytest)
- [x] Estrutura de pastas vazia criada (`src/gestor_comercial/...`, `tests/`, `resources/`, `migrations/`)

## Fase 1 — Núcleo de dados (Model + Repository)
- [x] Entidades SQLAlchemy em `domain/`: Funcionario, Mesa, Comanda, ItemComanda, Produto, Categoria, ComboItem, Pagamento, Caixa, MovimentoCaixa, QuitacaoConsumo, Impressora
- [x] Enums em `domain/enums.py` (StatusMesa, StatusComanda, FormaPagamento, PerfilFuncionario, TipoMovimento)
- [x] `repository/base.py` — engine SQLite + sessionmaker
- [x] Configuração inicial do Alembic (`alembic init`, primeira migration com todas as tabelas)
- [x] Seed inicial de Mesas (conjunto fixo) e Funcionário admin de teste
- [x] Testes de integração: criar/consultar cada entidade via repository

## Fase 2 — Lógica de negócio (Services) — ✅ concluída em 2026-08-20
- [x] `auth_service.py` — hash SHA-256+salt, validação de PIN, usuário logado em memória
- [x] `cardapio_service.py` — CRUD produto/categoria, montagem de combo (regra de 1 nível)
- [x] `comanda_service.py` — abrir por mesa (idempotente), abrir balcão, lançar/remover/cancelar item, fechar, cancelar
- [x] `pagamento_service.py` — registrar pagamento parcial/múltiplo, calcular troco, consumo interno, fechamento automático
- [x] `caixa_service.py` — abrir/fechar, sangria/reforço/despesa, saldo esperado, total maquininha
- [x] Testes unitários de cada service (casos de sucesso + regras de bloqueio) — 319 testes, ver `docs/arquitetura.md` §8 para o resumo da revisão adversarial que corrigiu 9 problemas antes de fechar a fase
- [x] Controle de Turnos: `caixas.numero_sequencial_dia` (numerado pelo eixo `fechado_em`, não por `aberto_em` — é a regra da virada de madrugada, não um índice de banco), `aberto_por_id`/`fechado_por_id`, `titulo_fechamento`, `listar_historico`, `totais_por_forma` — 2026-08-26, migration `c3f9a7d21b6e`

## Fase 3 — Interface PySide6 (Views)
- [x] Extrair paleta de cores/CSS do front-end web (`GESTOR COMERCIAL/.../desktop/style.css`) para `resources/qss/`
- [x] `login_view.py` — PIN pad
- [x] `mesas_view.py` — grid de mesas (livre/ocupada/balcão), espelhando o `grid-mesas` web
- [x] `comanda_view.py` — lista de itens + total, modal de adicionar item
- [x] `pagamento_dialog.py` — resumo, forma, valor, troco, consumo interno
- [x] `caixa_view.py` — status, abrir/fechar, tabela de movimentos
- [x] `historico_caixa_view.py` — Histórico de Fechamentos: filtro por período/operador, reimpressão do relatório — 2026-08-26
- [x] `cardapio_view.py` — CRUD produto/categoria/combo
- [x] `funcionarios_view.py` — CRUD básico + saldo devedor
- [x] Modal de cancelamento (item/comanda) com PIN de Gerente
- [x] `ui/main_window.py` + `main.py` — integra as telas (login → shell com sidebar → páginas) e é o ponto de entrada de verdade do app (`python -m gestor_comercial.main`)

## Fase 4 — Hardware (Impressão) — ✅ concluída em 2026-08-21
- [x] `hardware/impressora_escpos.py` — abstração de conexão (USB/Serial/Rede/Windows/Arquivo)
- [x] `impressao_service.py` — roteamento por categoria, fallback para a impressora padrão
- [ ] Teste manual com impressora física do food truck — depende do hardware, que o Vitor ainda não tem. O tipo de conexão **ARQUIVO** grava o cupom num `.txt` legível e permite validar o fluxo inteiro (comanda de produção, via de acréscimo, 2ª via, recibo, fechamento) antes de a impressora chegar; quando ela chegar, só o cadastro muda de tipo.

## Fase 5 — Empacotamento e Testes de Homologação
- [x] `packaging/build.spec` (PyInstaller) — build local validado (migrations + seed + QSS rodando dentro do .exe)
- [ ] Gerar `.exe` e testar em máquina limpa (sem Python instalado) — roteiro em [`docs/checklist-maquina-limpa.md`](docs/checklist-maquina-limpa.md)
- [x] Simular quedas de energia / fechamento forçado — checar integridade do SQLite — automatizado em `tests/integration/test_resiliencia_queda_energia.py` (mata o processo de verdade no meio da escrita; confirma rollback automático sem commit e persistência com commit)
- [x] Testes de estresse: inputs inválidos, digitação errada, dupla submissão — coberto pela suíte de services (PIN errado, quantidade 0/negativa, cancelar sem PIN de gerente, fechar sem pagamento, e o novo `test_confirmar_pagamento_duas_vezes_seguidas_e_bloqueado`)
- [x] Ícone `.ico` do app (`resources/icons/app.ico`, gerado por `packaging/gerar_icone.py`) + `icon=` no `build.spec` e instalador (`packaging/instalador.iss`, Inno Setup) que cria atalho no Menu Iniciar/Desktop — 2026-09-01
- [ ] Gerar em máquina limpa de verdade na loja do pai do Vitor (levar `packaging/output/GestorComercial-Setup.exe` no pendrive) e rodar o roteiro de [`docs/checklist-maquina-limpa.md`](docs/checklist-maquina-limpa.md)
- [ ] Validação final com o pai antes de ir para produção real

## Backlog (V2/V3 — não iniciar antes da V1 estar em produção)
1. App Mobile do Atendente
2. Controle de Estoque
3. Ficha Técnica
