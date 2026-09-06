# Checklist — Teste em Máquina Limpa (Fase 5)

> Objetivo: provar que `dist/GestorComercial.exe` roda sozinho numa máquina
> Windows **sem Python, sem venv, sem nada deste repositório instalado** —
> só o `.exe` copiado. É a única forma de saber se o `build.spec` esqueceu
> alguma dependência que só existia por acidente na máquina de dev.

## 0. Preparar o .exe (na máquina de dev)
- [ ] `.venv\Scripts\pyinstaller.exe packaging/build.spec --noconfirm`
- [ ] Copiar **só** `dist\GestorComercial.exe` (não a pasta `dist` toda, não o
      repo) para um pendrive/pasta compartilhada — se algo além do `.exe`
      for necessário, isso já seria uma falha do empacotamento.

## 1. Máquina limpa — pré-condições
- [ ] Confirmar que a máquina **não tem Python instalado** (`python
      --version` deve falhar/não existir)
- [ ] Confirmar que é a mesma arquitetura (Windows 64-bit) — o build é
      `win_amd64`
- [ ] Copiar o `.exe` para uma pasta local (ex.: `Área de Trabalho\`), fora
      de qualquer pasta sincronizada (OneDrive pode bloquear/atrasar o
      arquivo)

## 2. Primeira execução
- [ ] Dar duplo-clique no `.exe`
- [ ] Se o Windows SmartScreen bloquear ("Windows protegeu seu PC"): clicar
      em "Mais informações" → "Executar assim mesmo" — **isso é esperado**
      para um `.exe` sem assinatura digital, não é bug
- [ ] O app deve abrir direto na tela de **Login (PIN pad)**, maximizado,
      sem nenhum console preto atrás e sem diálogo de erro
- [ ] Se aparecer o diálogo **"Erro ao iniciar"**: anotar a mensagem exata
      (é o único canal de erro nesse build — não tem console). Ver seção
      "Se der erro" no fim deste checklist.

## 3. Confirmar que o banco foi criado no lugar certo
- [ ] Fechar o app
- [ ] Abrir `%USERPROFILE%\.gestor_comercial\` no Explorer
- [ ] Confirmar que existe `gestor_comercial.db` e que o tamanho é > 0 KB
- [ ] Confirmar que `gestor_comercial.db-wal` **não existe ou está com 0 KB**
      com o app fechado — é o `wal_checkpoint(TRUNCATE)` do encerramento
      fazendo o trabalho dele (ver `repository/backup.py`). Se estiver com
      tamanho depois de fechar o app, o checkpoint não rodou: anotar
- [ ] (opcional) Reabrir o `.exe` uma segunda vez — deve subir mais rápido
      (não recria nada) e sem erro de "migration já aplicada"

## 4. Fluxo funcional mínimo (fumaça)
- [ ] Login com o PIN do gerente seed
- [ ] Abrir o Caixa
- [ ] Abrir uma Mesa → lançar 1 item do cardápio
- [ ] Fechar a comanda com um pagamento (dinheiro, com troco)
- [ ] Registrar uma sangria/reforço no Caixa
- [ ] Fechar o Caixa no fim
- [ ] Conferir que apareceu um arquivo em
      `%USERPROFILE%\.gestor_comercial\backups\gestor_backup_*.db` — o backup
      automático do fechamento
- [ ] Em **Configurações → Cópia de Segurança**, clicar em "Gerar cópia agora"
      e conferir que o caminho aparece na tela (é o backup que vai pro pendrive)
- [ ] Testar 1 impressão com impressora tipo **ARQUIVO** (ver
      `docs/arquitetura.md` — o cupom deve virar um `.txt` legível)

## 5. Simular queda de energia / fechamento forçado
> Objetivo: garantir que uma comanda em andamento não corrompe o SQLite.
- [ ] Com uma comanda aberta e item lançado, matar o processo no Gerenciador
      de Tarefas (não fechar pela janela) — simula queda de energia
- [ ] Reabrir o `.exe`
- [ ] Confirmar que o app sobe normalmente e que a comanda/itens lançados
      antes da queda continuam íntegros (nem sumiram, nem duplicaram)
- [ ] Repetir matando o processo **durante** o fechamento de uma comanda
      (logo após clicar em "Confirmar pagamento")

## 6. Testes de estresse de input
- [ ] Digitar PIN errado 3x seguidas
- [ ] Tentar lançar item com quantidade 0 ou negativa
- [ ] Clicar duas vezes rápido em "Confirmar pagamento" (dupla submissão) —
      não pode gerar pagamento duplicado
- [ ] Tentar fechar uma comanda sem pagamento registrado
- [ ] Cancelar item/comanda sem PIN de gerente válido

## 7. Validação final
- [ ] Rodar o fluxo do dia a dia real com o pai do Vitor observando, sem
      intervenção do Vitor
- [ ] Coletar o feedback dele antes de marcar a Fase 5 como concluída no
      `TODO.md`

---

## Se der erro
Como o build de produção roda com `console=False` (sem janela preta), o
único jeito de ver um erro de inicialização é o diálogo "Erro ao iniciar".
Se ele aparecer com uma mensagem tipo `No module named 'X'`, normalmente é
um import dinâmico que o PyInstaller não detectou por análise estática
(mesma causa raiz do bug do `logging.config` corrigido em 2026-08-22) —
resolve adicionando o módulo em `hiddenimports` no
`packaging/build.spec` e gerando o `.exe` de novo.

Para depurar sem precisar adivinhar: editar `packaging/build.spec`
temporariamente com `console=True`, gerar o `.exe` de novo e rodar — o
traceback completo aparece na janela de console. Reverter para
`console=False` antes de gerar o `.exe` final de distribuição.
