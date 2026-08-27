# Plano de Implementação — Gestor Comercial Python

> Progresso da V1. Marcar `[x]` conforme cada etapa for concluída e testada. Detalhes de regras/escopo em [`docs/arquitetura.md`](docs/arquitetura.md).

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
- [x] Controle de Turnos: `caixas.numero_sequencial_dia` (indexado por `fechado_em`, virada de madrugada), `aberto_por_id`/`fechado_por_id`, `titulo_fechamento`, `listar_historico`, `totais_por_forma` — 2026-08-26, migration `c3f9a7d21b6e`

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
- [ ] Ícone `.ico` do app (`resources/`) + `icon=` no `build.spec` (hoje `icon=None`) e instalador (Inno Setup) que cria atalho no Menu Iniciar/Desktop
- [ ] Validação final com o pai antes de ir para produção real

## Backlog (V2/V3 — não iniciar antes da V1 estar em produção)
1. App Mobile do Atendente
2. Controle de Estoque
3. Ficha Técnica
