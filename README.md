# Gestor Comercial — PDV Food Truck (Python)

PDV desktop standalone, feito para rodar 100% offline em uma máquina fraca no food truck do meu pai. É a reestruturação, em Python, do [Gestor Comercial](../GESTOR%20COMERCIAL) original (Java/Spring Boot) — não um projeto separado, mas o mesmo sistema portado para uma arquitetura de máquina única, sem servidor e sem dependência de Wi-Fi.

## Por quê

O Gestor Comercial original resolve o problema certo, mas sua arquitetura (Spring Boot + PWA em rede local) exige mais hardware e uma rede estável do que a máquina do food truck oferece. Em vez de esperar um SaaS completo amadurecer, este projeto entrega uma versão enxuta e real primeiro: um executável único, sem instalação, que funciona mesmo se o Wi-Fi cair no meio do expediente.

## Stack

| Camada | Tecnologia | Papel |
|---|---|---|
| Interface | **PySide6** | Telas desktop (Qt/LGPL), réplica visual do front-end web já validado |
| Regras de negócio | Python puro | Camada de serviços — troco, fechamento de caixa, cancelamentos |
| Persistência | **SQLAlchemy** + **Alembic** | ORM (equivalente ao JPA/Hibernate) + migrações versionadas de schema |
| Banco | **SQLite** | Arquivo local único, sem servidor de banco |
| Impressão | **python-escpos** | Comandos ESC/POS para a impressora térmica da comanda |
| Empacotamento | **PyInstaller** | Gera o `.exe` final para a máquina do food truck |

## Escopo da V1 (MVP)

Autenticação por PIN, Mesas, Comandas, Itens de Comanda, Pagamentos (com troco e consumo interno), Caixa (abertura/fechamento/sangria/reforço), Cardápio (Produtos/Categorias/Combos) e Impressão roteada por categoria.

**Fora da V1** (backlog, nesta ordem de prioridade): app mobile para atendentes, Controle de Estoque, Ficha Técnica.

Detalhes completos de requisitos, regras de negócio e diagramas em [`docs/arquitetura.md`](docs/arquitetura.md).

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
alembic upgrade head
python -m gestor_comercial.main
```

## Estrutura do projeto

Ver árvore completa e responsabilidade de cada camada em [`docs/arquitetura.md`](docs/arquitetura.md#árvore-de-pastas).

## Progresso

Acompanhado em [`TODO.md`](TODO.md).
