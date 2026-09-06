# Histórico — documentos obsoletos

> ⚠️ **Nada aqui descreve o sistema atual.** São diários de migrações já
> concluídas, guardados só como registro de por que certas decisões foram
> tomadas. Não use nenhum deles como referência para mexer no código.

Arquivados em 2026-09-06, na Fase 0 da [Remasterização da Versão 1.0](../../REMASTERIZACAO-V1.md).

Motivo: a auditoria (§3.12 da Remasterização) constatou que os cinco arquivos
abaixo, ~1.004 linhas no total, descrevem uma tela de login que **não existe
mais** — inclusive afirmando ter removido o numpad, que continua lá, vivo e em
uso. Documentação que contradiz o código é pior que documentação nenhuma:
convida a uma "limpeza" que quebra o app.

| Arquivo | Do que trata |
|---|---|
| `COMPARACAO_LOGIN.md` | Comparação entre versões da tela de login |
| `GUIA_TECNICO_REFACTORING.md` | Guia técnico de um refactor já concluído |
| `README_REFACTORING.md` | Visão geral desse mesmo refactor |
| `REFACTORING_LOGIN.md` | Notas da refatoração da tela de login |
| `TROUBLESHOOTING_E_MELHORIAS.md` | Problemas e melhorias de então |

**A referência viva é:**

- [`docs/arquitetura.md`](../arquitetura.md) — escopo, regras de negócio e stack
- [`TODO.md`](../../TODO.md) — plano de implementação por fases
- [`REMASTERIZACAO-V1.md`](../../REMASTERIZACAO-V1.md) — a faxina final antes da produção
