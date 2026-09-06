---
project: gestor-comercial-python
domain: PDV desktop offline (food truck do pai do Vitor)
status: Remasterização da V1 — Fases 0-5 concluídas em 2026-09-06, PRÓXIMA é a Fase 6 (Arquitetura da UI: quebrar as views gigantes só onde compensar), sem decisão pendente bloqueando. Onde paramos e o porquê: §0 do REMASTERIZACAO-V1.md. Suíte: 775 verdes, 0 xfail, 0 falhas. A Fase 5 fechou os 9 itens de higiene da UI — EstoqueView removida, os 31 modais e as 6 tabelas padronizados, lambdas do tema viraram métodos ligados, chave do cache de miniaturas corrigida, código morto e 3 comentários que mentiam eliminados, 20 cores congeladas foram para o QSS global e a tipagem pública ficou completa (403/403). Dois achados no caminho: a MainWindow não era coberta por teste nenhum (agora é), e a troca das tabelas teria apagado a seleção do usuário se não fosse medida antes. Empacotamento continua aberto: falta testar o .exe em máquina limpa de verdade
local: C:\Vitor Raphael\Códigos\Gestor Comercial Python
repo: https://github.com/VitorRaphael/gestor-comercial-python
---

# O que é
PDV desktop standalone em Python, para a máquina fraca do food truck do pai
do Vitor. **Projeto próprio e independente** — repositório e código-fonte
próprios. Faz o *porte* das regras de negócio, Casos de Uso e Diagrama de
Classes já validados no `GESTOR COMERCIAL` (Java/Spring Boot) para uma stack
Python, mas **não edita nem depende em runtime daquele projeto**. Esse
projeto Java continua existindo separado e intocado.

# Por que existe (não confundir com o Java)
A arquitetura cliente-servidor do Gestor Comercial Java (Spring Boot + PWA em
rede local) está correta como produto, mas exige mais hardware e uma rede
Wi-Fi estável do que a máquina do food truck oferece. Este projeto resolve
isso virando um `.exe` único, standalone, 100% offline, sem servidor.

Uma tentativa anterior (pasta `PVD Python`, repo `pvd-food-truck`) foi
descartada em 2026-08-20 por ter partido de um escopo "inspirado" no Gestor
Comercial em vez de portar o sistema real — a pasta foi então renomeada para
`Gestor Comercial Python` para eliminar essa ambiguidade de vez.

# Regras inegociáveis (RNFs)
- Otimização: leve o suficiente pra máquina fraca do food truck.
- Desempenho: zero travamentos.
- Resiliência offline: nenhuma operação de venda depende de rede.
- Confiabilidade: tratado e testado antes de produção real.

# Escopo V1 (ver docs/arquitetura.md §3 pro detalhe completo)
Autenticação por PIN, Mesas, Comandas, Itens, Pagamentos, Caixa,
Cardápio/Combos, Impressoras, Funcionários, Consumo Interno.
**Fora da V1** (backlog, nesta ordem): App Mobile do Atendente, Controle de
Estoque, Ficha Técnica.

# Stack
PySide6 (LGPL) · SQLAlchemy + Alembic (ORM + migrações) · SQLite · python-escpos
(impressão térmica) · PyInstaller (empacotamento em `.exe` único).

# Modo de trabalho
Write mode — Claude escreve o código diretamente neste projeto (decisão
explícita do Vitor, diferente do teach-mode usado no `ifood-merchant-api`).

# Documentação de referência
- `docs/arquitetura.md` — documento vivo com escopo, regras de negócio,
  árvore de pastas e justificativas de stack.
- `TODO.md` — plano de implementação por fases.
- Diagrama de Classes (V1): https://claude.ai/code/artifact/ef046c14-4e1e-42fb-a27c-8b7c9bf1ddda
