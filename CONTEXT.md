---
project: gestor-comercial-python
domain: PDV desktop offline (food truck do pai do Vitor)
status: Remasterização da V1 CONCLUÍDA em 2026-09-06 — as 8 fases (0 a 7) fechadas, suíte 800 verdes, 0 xfail, 0 falhas. Onde paramos e o porquê: §0 do REMASTERIZACAO-V1.md. A Fase 7 comparou o sistema com o código de ANTES da faxina (b22da75) pelos dois produtos que o pai do Vitor vê: 11 telas em 24 estados (2 temas + filtro por operador) e os 6 cupons ESC/POS. Cupons idênticos linha a linha; das 24 telas, 9 idênticas byte a byte e 15 diferentes — 13 delas são os defeitos que a faxina matou (cartão fantasma, célula empilhada, cor congelada no tema claro), agora visíveis lado a lado. A comparação achou UMA regressão da própria remasterização, corrigida com teste: a seção "Cópia de Segurança" (Fase 2) empurrou Configurações além da altura da página e o layout espremeu os botões de Senhas e Acesso até ficarem sem rótulo num monitor de 768px. Bancadas versionadas: tools/comparar_telas.py e tools/comparar_cupons.py. Depois disso, em 2026-09-06, o item de layout que a Fase 7 deixou registrado foi feito (§9 do REMASTERIZACAO-V1.md): o cartão "Recebimentos" da tela de Caixa cortava as linhas ao meio a 1366x738 — defeito anterior à faxina, igual em b22da75 — e ganhou a mesma QScrollArea da Configurações na coluna de resumo, com a largura da barra reservada para não trocar corte de cima por corte de lado. Suíte 801, teste próprio, e as 24 renderizações conferidas nos dois tamanhos: 22 idênticas byte a byte, diferindo só a tela corrigida. A bancada tools/comparar_telas.py ganhou --tamanho LxA. PRÓXIMO passo da V1: gerar o .exe e rodar docs/checklist-maquina-limpa.md numa máquina limpa de verdade, e depois a validação com o pai
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
