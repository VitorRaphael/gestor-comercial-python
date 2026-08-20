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
- Login por PIN numérico (hash SHA-256 + salt por funcionário), sem usuário/senha.
- Usuário autenticado mantido em memória do processo (não há token HTTP — é um app de processo único).
- Reautenticação de PIN de Gerente para ações críticas, sem trocar o usuário da sessão principal.
- Perfis: `ATENDENTE` / `GERENTE`. Ações administrativas exigem PIN de Gerente.
- Não permite dois funcionários ativos com o mesmo PIN.

### 3.2 Cardápio — Categorias e Produtos
- CRUD de categoria (nome único); exclusão bloqueada se houver produtos vinculados; desativação soft.
- CRUD de produto (nome, preço, custo, categoria, descrição); upload de foto; desativação soft; exclusão bloqueada se já vendido ou é componente de combo.
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
- Consulta de saldo devedor por funcionário e histórico de consumos/quitações.
- Quitação (total ou parcial, PIN de Gerente), abatendo os consumos mais antigos primeiro (FIFO).

### 3.9 Caixa
- Abertura (valor inicial), bloqueia se já houver caixa `ABERTO`.
- Fechamento (valor contado + observação), bloqueia se já fechado.
- Cálculo de saldo esperado (abertura + reforços − sangrias − despesas − consumos + dinheiro recebido).
- Cálculo do total vendido em maquininha (crédito + débito + PIX).

### 3.10 Movimentos de Caixa
- Registro de `SANGRIA` / `REFORCO` / `DESPESA` / `CONSUMO_FUNCIONARIO`, vinculado ao caixa aberto.

### 3.11 Funcionários
- Cadastro (nome, PIN, perfil), listagem de ativos, desativação soft.

### 3.12 Impressoras e Roteamento
- Cadastro de impressora; impressão da comanda roteada por categoria via `python-escpos`.
- Itens sem impressora vinculada caem em um grupo genérico (não bloqueia a impressão).

## 4. Diagramas de referência

- **Diagrama de Casos de Uso** — construído com o Jarvis (Gemini), mapeando Atendente/Gerente e os fluxos `Include`/`Extend`. Ver histórico da conversa (a ser colado/anexado aqui quando exportado).
- **Diagrama de Classes (V1)** — publicado como artifact: <https://claude.ai/code/artifact/ef046c14-4e1e-42fb-a27c-8b7c9bf1ddda>. Cobre Funcionario, Mesa, Comanda, ItemComanda, Produto, Categoria, ComboItem, Pagamento, Caixa, MovimentoCaixa, QuitacaoConsumo, Impressora e suas multiplicidades.

> As entidades em `src/gestor_comercial/domain/` devem espelhar 1:1 as classes desse diagrama.

## 5. Backlog — fora da V1

Nesta ordem de prioridade, para versões futuras:

1. **App Mobile do Atendente** — camada de API/sessão remota, para bater pedido fora do caixa central sem sobrecarregar um único ponto.
2. **Controle de Estoque** — entidades `MateriaPrima` e `MovimentoEstoque`, entrada de compra, ajuste manual.
3. **Ficha Técnica** — vínculo Produto ↔ MateriaPrima e baixa automática recursiva (direta e via componentes de combo).

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
│       │   └── impressao_service.py
│       │
│       ├── hardware/              # isolamento de periféricos físicos
│       │   └── impressora_escpos.py
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
│       │   │   └── funcionarios_view.py
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
