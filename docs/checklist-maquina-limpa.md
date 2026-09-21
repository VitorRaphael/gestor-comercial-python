# Checklist — Teste em Máquina Limpa (Fase 5)

> Objetivo: provar que a pasta `App_Pendrive` roda sozinha numa máquina
> Windows **sem Python, sem venv, sem nada deste repositório instalado** —
> só a pasta copiada. É a única forma de saber se o `app.spec` esqueceu
> alguma dependência que só existia por acidente na máquina de dev.

## 0. Preparar a pasta (na máquina de dev)
- [ ] `.venv\Scripts\python.exe packaging\gerar_exe.py` terminou com
      **BUILD APROVADO** (suíte, build, prova de fumaça, `App_Pendrive` e prova
      do modo portátil — ver `DEPLOYMENT.md`)
- [ ] Copiar a pasta **`App_Pendrive` inteira** (o `.exe`, o
      `gestor_comercial.db`, `uploads\` e o `LEIA-ME.txt` — e nada do repo)
      para o pendrive — se algo além dela for necessário, isso já seria uma
      falha do empacotamento.

## 1. Máquina limpa — pré-condições
- [ ] Confirmar que a máquina **não tem Python instalado** (`python
      --version` deve falhar/não existir)
- [ ] Confirmar que é a mesma arquitetura (Windows 64-bit) — o build é
      `win_amd64`
- [ ] Copiar a pasta inteira para o disco local (ex.: `C:\GestorComercial\`),
      fora de qualquer pasta sincronizada (OneDrive pode bloquear/atrasar o
      arquivo). Rodar do pendrive também funciona, mas o banco de vendas
      grava nele — tirar o pendrive com o programa aberto pode perder a venda
      em andamento

## 2. Primeira execução
- [ ] Dar duplo-clique no `.exe`
- [ ] Se o Windows SmartScreen bloquear ("Windows protegeu seu PC"): clicar
      em "Mais informações" → "Executar assim mesmo" — **isso é esperado**
      para um `.exe` sem assinatura digital, não é bug
- [ ] O app deve abrir direto na tela de **Login (PIN pad)**, maximizado,
      sem nenhum console preto atrás e sem diálogo de erro
- [ ] O botão na barra de tarefas mostra o ícone **GC dourado** (não o do
      Python nem o genérico do Windows)
- [ ] Entrar e abrir o **Cardápio**: as categorias, subcategorias, combos e
      as **fotos** são as do cardápio do Vitor (vieram do
      `gestor_comercial.db` e do `uploads\` da pasta)
- [ ] A tela de **Caixa** não mostra caixa aberto nem venda nenhuma: o banco
      da pasta sai do build sem movimento
- [ ] Se aparecer o diálogo **"Erro ao iniciar"**: anotar a mensagem exata
      (é o único canal de erro nesse build — não tem console). Ver seção
      "Se der erro" no fim deste checklist.

## 3. Confirmar que o banco usado é o da pasta
- [ ] Fechar o app
- [ ] Na pasta do programa, confirmar que apareceu `logs\gestor.log` e que ele
      diz "banco existente preservado" com o caminho do `gestor_comercial.db`
      **desta pasta**
- [ ] Colar `%APPDATA%\GestorComercial_V2\` na barra de endereço do Explorer:
      a pasta **não deve existir** — no modo portátil nada é gravado lá
- [ ] Se a máquina já rodou o `.exe` antigo: `%USERPROFILE%\.gestor_comercial\`
      continua como estava (mesma data de modificação) — a versão nova não lê
      nem grava lá
- [ ] Confirmar que `gestor_comercial.db-wal` **não existe ou está com 0 KB**
      com o app fechado — é o `wal_checkpoint(TRUNCATE)` do encerramento
      fazendo o trabalho dele (ver `repository/backup.py`). Se estiver com
      tamanho depois de fechar o app, o checkpoint não rodou: anotar
- [ ] (opcional) Reabrir o `.exe` uma segunda vez — deve subir mais rápido
      (não recria nada), sem erro de "migration já aplicada", e o log diz
      "banco existente preservado"

## 4. Fluxo funcional mínimo (fumaça)
- [ ] Login com as senhas que o Vitor configurou no banco de trabalho (a
      semente leva as senhas junto com o cardápio)
- [ ] Abrir o Caixa
- [ ] Abrir uma Mesa → lançar 1 item do cardápio
- [ ] Fechar a comanda com um pagamento (dinheiro, com troco)
- [ ] Registrar uma sangria/reforço no Caixa
- [ ] Fechar o Caixa no fim
- [ ] Conferir que apareceu um arquivo em `backups\gestor_backup_*.db`, dentro
      da pasta do programa — o backup automático do fechamento
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
`packaging/app.spec` e gerando o `.exe` de novo.

Para depurar sem precisar adivinhar: editar `packaging/app.spec`
temporariamente com `console=True`, gerar o `.exe` de novo e rodar — o
traceback completo aparece na janela de console. Reverter para
`console=False` antes de gerar o `.exe` final de distribuição.
