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
- [ ] Entidades SQLAlchemy em `domain/`: Funcionario, Mesa, Comanda, ItemComanda, Produto, Categoria, ComboItem, Pagamento, Caixa, MovimentoCaixa, QuitacaoConsumo, Impressora
- [ ] Enums em `domain/enums.py` (StatusMesa, StatusComanda, FormaPagamento, PerfilFuncionario, TipoMovimento)
- [ ] `repository/base.py` — engine SQLite + sessionmaker
- [ ] Configuração inicial do Alembic (`alembic init`, primeira migration com todas as tabelas)
- [ ] Seed inicial de Mesas (conjunto fixo) e Funcionário admin de teste
- [ ] Testes de integração: criar/consultar cada entidade via repository

## Fase 2 — Lógica de negócio (Services)
- [ ] `auth_service.py` — hash SHA-256+salt, validação de PIN, usuário logado em memória
- [ ] `cardapio_service.py` — CRUD produto/categoria, montagem de combo (regra de 1 nível)
- [ ] `comanda_service.py` — abrir por mesa (idempotente), abrir balcão, lançar/remover/cancelar item, fechar, cancelar
- [ ] `pagamento_service.py` — registrar pagamento parcial/múltiplo, calcular troco, consumo interno, fechamento automático
- [ ] `caixa_service.py` — abrir/fechar, sangria/reforço/despesa, saldo esperado, total maquininha
- [ ] Testes unitários de cada service (casos de sucesso + regras de bloqueio)

## Fase 3 — Interface PySide6 (Views)
- [ ] Extrair paleta de cores/CSS do front-end web (`GESTOR COMERCIAL/.../desktop/style.css`) para `resources/qss/`
- [ ] `login_view.py` — PIN pad
- [ ] `mesas_view.py` — grid de mesas (livre/ocupada/balcão), espelhando o `grid-mesas` web
- [ ] `comanda_view.py` — lista de itens + total, modal de adicionar item
- [ ] `pagamento_dialog.py` — resumo, forma, valor, troco, consumo interno
- [ ] `caixa_view.py` — status, abrir/fechar, tabela de movimentos
- [ ] `cardapio_view.py` — CRUD produto/categoria/combo
- [ ] `funcionarios_view.py` — CRUD básico + saldo devedor
- [ ] Modal de cancelamento (item/comanda) com PIN de Gerente

## Fase 4 — Hardware (Impressão)
- [ ] `hardware/impressora_escpos.py` — abstração de conexão (USB/Serial)
- [ ] `impressao_service.py` — roteamento por categoria, fallback para grupo genérico
- [ ] Teste manual com impressora física do food truck

## Fase 5 — Empacotamento e Testes de Homologação
- [ ] `packaging/build.spec` (PyInstaller)
- [ ] Gerar `.exe` e testar em máquina limpa (sem Python instalado)
- [ ] Simular quedas de energia / fechamento forçado — checar integridade do SQLite
- [ ] Testes de estresse: inputs inválidos, digitação errada, dupla submissão
- [ ] Validação final com o pai antes de ir para produção real

## Backlog (V2/V3 — não iniciar antes da V1 estar em produção)
1. App Mobile do Atendente
2. Controle de Estoque
3. Ficha Técnica
