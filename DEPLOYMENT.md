# DEPLOYMENT — o .exe de produção

## Em uma linha

```
.venv\Scripts\python.exe packaging\gerar_exe.py
```

Roda a suíte, gera `dist\GestorComercial.exe` com o cardápio e as fotos
embutidos, abre o `.exe` de verdade numa pasta de usuário descartável para
provar que ele sobe, monta a pasta `App_Pendrive\` (o `.exe` + o banco limpo +
as fotos) e prova que ela roda sozinha de qualquer lugar. Termina com **BUILD
APROVADO** ou **BUILD REPROVADO** e o motivo. Nenhum passo manual.

Com vendas de teste no banco de trabalho (o build recusa — abaixo):

```
.venv\Scripts\python.exe tools\limpar_vendas.py
.venv\Scripts\python.exe packaging\gerar_exe.py
```

Ou, sem fechar o programa nem mexer no banco de trabalho, a partir de uma cópia
limpa: `tools\limpar_vendas.py --banco <cópia>` e depois
`packaging\gerar_exe.py --origem <cópia>` (a cópia precisa de
`uploads\thumbnails\` ao lado, com as fotos).

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
  tabelas têm linhas, e a decisão de limpar é sua — `tools\limpar_vendas.py`
  (feche o programa antes; ele guarda uma cópia do banco de antes ao lado, apaga
  só as vendas e a numeração de caixa e comanda volta ao 1);
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

### Modo portátil: `gestor_comercial.db` ao lado do `.exe`

Se existe `gestor_comercial.db` **na mesma pasta do `.exe`**, a pasta de dados
é a própria pasta do `.exe` — banco, fotos (`uploads\thumbnails\`), `backups\`,
`logs\` e `cupons\` ficam ali, e `%APPDATA%` não é lido nem criado. É a pasta
`App_Pendrive\`:

```
App_Pendrive\
├── GestorComercial.exe
├── gestor_comercial.db        ← o cardápio, sem venda nenhuma (é a semente)
├── uploads\thumbnails\        ← fotos dos produtos
└── LEIA-ME.txt                ← o que o pai precisa saber, em uma tela
```

O caminho é lido do `.exe` em execução, nunca gravado: a pasta funciona no
pendrive (qualquer letra), copiada para `C:\` ou movida depois. É a pasta do
`.exe`, não a pasta atual do processo — um atalho com "Iniciar em" apontando
para outro lugar não troca o banco. Sem o banco ao lado (o `.exe` sozinho, ou o
instalado em `Program Files`), vale `%APPDATA%` como acima.

Rodar **direto do pendrive** funciona, mas o banco de vendas grava nele: tirar o
pendrive com o programa aberto pode perder a venda em andamento. O recomendado é
copiar a pasta inteira para o disco da máquina (ex.: `C:\GestorComercial\`).

O `gerar_exe.py` recusa sobrescrever uma `App_Pendrive` cujo banco já tenha
venda — se alguém usou o programa de dentro dela, as vendas são dela.

---

## Levar para a máquina do pai

1. Copie a pasta **`App_Pendrive` inteira** para o pendrive.
2. Na máquina do pai, copie a pasta para o disco, fora do OneDrive (ex.:
   `C:\GestorComercial\`), e dê duplo clique no `.exe`. O SmartScreen pode
   avisar ("Windows protegeu seu PC" → Mais informações → Executar assim
   mesmo): é esperado num `.exe` sem assinatura.
3. Siga `docs/checklist-maquina-limpa.md`.

(O caminho antigo continua valendo: copiar **só** `dist\GestorComercial.exe`,
que cria o banco em `%APPDATA%` a partir da semente embutida.)

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
Segurança). No modo portátil, é trocar a pasta inteira por uma `App_Pendrive`
nova — com o mesmo cuidado de guardar a antiga antes.

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
| `packaging/gerar_exe.py` | fluxo completo: ícone → testes → build → prova de fumaça → `App_Pendrive` → prova do modo portátil |
| `tools/limpar_vendas.py` | apaga as vendas de teste de um banco e mantém o cadastro (regras em `repository/limpeza_de_vendas.py`) |
| `packaging/app.spec` | PyInstaller: prepara a semente, empacota, poda o Qt que o app não usa |
| `packaging/preparar_semente.py` | gera `build/semente/` (roda sozinho para conferir o cardápio sem gerar o `.exe`) |
| `src/gestor_comercial/repository/preparo_da_semente.py` | regras do que entra e do que é recusado na semente |
| `src/gestor_comercial/core/banco_semente.py` | a cópia da semente no primeiro boot |
| `src/gestor_comercial/core/caminhos.py` | onde o programa lê recursos e grava dados, em dev, no `.exe` e no modo portátil |

Para depurar um `.exe` que não abre: troque `console=False` por `console=True`
em `packaging/app.spec`, gere de novo e rode pelo terminal. Volte para
`console=False` antes do build de distribuição.
