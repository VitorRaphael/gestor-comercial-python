# DEPLOYMENT — o .exe de produção

## Em uma linha

```
.venv\Scripts\python.exe packaging\gerar_exe.py
```

Roda a suíte, gera `dist\GestorComercial.exe` com o cardápio e as fotos
embutidos, e abre o `.exe` de verdade numa pasta de usuário descartável para
provar que ele sobe. Termina com **BUILD APROVADO** ou **BUILD REPROVADO** e o
motivo. Nenhum passo manual.

---

## O que o .exe leva dentro

| Item | De onde vem |
|---|---|
| Código + dependências (PySide6, SQLAlchemy, Alembic, python-escpos) | análise do PyInstaller |
| `alembic.ini` + `migrations/` | raiz do repo |
| Fonte da marca + `app_icon.ico` | `resources/` |
| **Semente do banco** (`banco_seed.db` + fotos) | o seu banco de trabalho, `~/.gestor_comercial/`, **no momento do build** |

A semente é tirada do banco que você usa no dia a dia em desenvolvimento. Para
mudar o cardápio que vai para o pai: abra o programa em dev
(`python -m gestor_comercial.main`), edite, e gere o `.exe` de novo.

### O build recusa a semente (e para) quando

- o banco tem **movimento de venda** (caixa, comanda, pagamento…) — a semente é
  só cadastro. Um teste feito na tela antes do build faria o programa do pai
  nascer com vendas que não aconteceram. Nada é apagado: a mensagem diz quais
  tabelas têm linhas, e a decisão de limpar é sua;
- um produto aponta para uma **foto que não está em disco**;
- o banco está **corrompido** ou com referência quebrada.

A cópia usa a API de backup do SQLite, a partir de uma conexão somente leitura:
pega também o que ainda está no `-wal` (medido em 2026-09-16: uma cópia só do
`.db` teria levado 182 produtos em vez de 188 e 169 fotos em vez de 177) e não
consegue alterar o seu banco.

---

## Onde o .exe grava

```
%APPDATA%\GestorComercial_V2\
├── gestor_comercial.db        ← vendas, cardápio, senhas
├── uploads\thumbnails\        ← fotos dos produtos
├── backups\                   ← cópia automática a cada fechamento de caixa
├── logs\gestor.log            ← caixa-preta (erros, boot, "Janela principal aberta")
└── cupons\                    ← impressora tipo ARQUIVO
```

- **Primeira abertura** (pasta sem banco): as fotos e depois o banco são
  copiados da semente. Se a energia cair no meio, a abertura seguinte refaz do
  zero — o banco só aparece depois de todas as fotos gravadas.
- **Todas as outras aberturas**: o banco existente é usado como está. A semente
  nunca mais é lida, e nunca sobrescreve nada.
- **A pasta do .exe antigo** (`%USERPROFILE%\.gestor_comercial\`, do build de
  2026-09-01) não é lida, não é apagada e não serve de reserva. A variável
  `GESTOR_COMERCIAL_DB` também é ignorada pelo `.exe` — ela só vale rodando do
  código-fonte.

Desinstalar o programa não apaga `%APPDATA%\GestorComercial_V2\`.

---

## Levar para a máquina do pai

1. Copie **só** `dist\GestorComercial.exe` (pendrive, ou o instalador — abaixo).
2. Na máquina do pai, coloque numa pasta local fora do OneDrive e dê duplo
   clique. O SmartScreen pode avisar ("Windows protegeu seu PC" → Mais
   informações → Executar assim mesmo): é esperado num `.exe` sem assinatura.
3. Não copie `.db` nenhum. O cardápio já está dentro do `.exe`.
4. Siga `docs/checklist-maquina-limpa.md`.

### Instalador (opcional)

Com o Inno Setup instalado:

```
ISCC.exe packaging\instalador.iss
```

Gera `packaging\output\GestorComercial-Setup.exe` (atalho no Menu Iniciar e na
Área de Trabalho, com o mesmo identificador de barra de tarefas do programa).

---

## Refazer do zero na máquina do pai

Feche o programa e apague (ou renomeie) `%APPDATA%\GestorComercial_V2\`. Na
próxima abertura ele nasce de novo da semente embutida. **Isso descarta as
vendas daquela pasta** — faça uma cópia antes (Configurações → Cópia de
Segurança).

---

## Trocar o ícone

```
.venv\Scripts\python.exe packaging\gerar_icone.py caminho\do\novo.png
```

Converte para `resources\icons\app_icon.ico` (16 a 256 px, cantos brancos
viram transparentes) e guarda a arte em `packaging\app_icon_fonte.png`.

---

## Peças, para quem for mexer

| Arquivo | Papel |
|---|---|
| `packaging/gerar_exe.py` | fluxo completo: ícone → testes → build → prova de fumaça |
| `packaging/app.spec` | PyInstaller: prepara a semente, empacota, poda o Qt que o app não usa |
| `packaging/preparar_semente.py` | gera `build/semente/` (roda sozinho para conferir o cardápio sem gerar o `.exe`) |
| `src/gestor_comercial/repository/preparo_da_semente.py` | regras do que entra e do que é recusado na semente |
| `src/gestor_comercial/core/banco_semente.py` | a cópia da semente no primeiro boot |
| `src/gestor_comercial/core/caminhos.py` | onde o programa lê recursos e grava dados, em dev e no `.exe` |

Para depurar um `.exe` que não abre: troque `console=False` por `console=True`
em `packaging/app.spec`, gere de novo e rode pelo terminal. Volte para
`console=False` antes do build de distribuição.
