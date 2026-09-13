# DEPLOYMENT - Gerando o .exe com Banco Completo

## Situação Atual (2026-09-09)

✅ **Banco de dados resetado e vazio**
- O arquivo `.db` foi deletado de `~/.gestor_comercial/`
- Quando você abrir o app pela primeira vez, ele vai recriar as tabelas automaticamente
- Ele vai também popular com dados padrão de seed (mesas, usuários, cardápio seed)

---

## Fase 1: Montar o Banco Real (AGORA)

### 1️⃣ Abra o app e deixe criar as tabelas
```bash
python -m gestor_comercial.main
```

Isso vai:
- Rodar as migrações (criar todas as tabelas)
- Rodar o seed (popular mesas e dados iniciais)
- Abrir a interface

### 2️⃣ Agora CRIE seu cardápio real
No app:
1. Abra **Cardápio** (tela à esquerda)
2. Crie as categorias (ex: Lanches, Bebidas, Combos)
3. Crie as subcategorias (ex: Lanches > Podrão, Lanches > Artesanal)
4. **Crie cada produto:**
   - Nome
   - Preço
   - Foto (ela vai ser compactada e salva no banco)
   - Subcategoria (se tiver)
5. **Crie os combos** (produtos montados a partir de outros)

### 3️⃣ Configure funcionários, turnos, etc.
- **Funcionários**: adicione os operadores que vão usar o caixa
- **Configurações**: ajuste as senhas, preferências, etc.
- **Impressoras**: configure os portos (se tiver impressora térmica)

### 4️⃣ Nenhuma restrição agora
- Teste tudo
- Crie quantos produtos quiser
- As fotos vão ser armazenadas direto no `.db` (o arquivo vai crescer)

**Resultado:** Um banco em `~/.gestor_comercial/gestor_comercial.db` com TODO seu cardápio

---

## Fase 2: Gerar o .exe (DEPOIS)

Quando o cardápio estiver **100% pronto e testado**:

### Comando para gerar o .exe
```bash
pyinstaller packaging/build.spec
```

Isso vai:
1. Compilar o código Python
2. Agrupar as dependências (PySide6, SQLAlchemy, etc.)
3. Copiar as migrações, temas e ícones
4. Gerar um **bundle único** em `dist/gestor_comercial.exe`

**Tempo estimado:** 2-5 minutos

### Onde fica o .exe
```
dist/gestor_comercial.exe    ← Seu executável único
```

---

## Fase 3: Levar para o Pendrive (DEPOIS)

### O que copiar

Você vai copiar **2 coisas** para o pendrive:

#### 1. O .exe
```
dist/gestor_comercial.exe → /pendrive/
```

#### 2. O banco completo
```
~/.gestor_comercial/gestor_comercial.db → /pendrive/
```

**Estrutura no pendrive:**
```
pendrive/
├── gestor_comercial.exe
└── gestor_comercial.db      ← Seu banco com TUDO
```

---

## Fase 4: Instalar na Máquina do Pai (DEPOIS)

Na máquina fraca do food truck:

### Passo 1: Copiar do pendrive
- Coloque em uma pasta (ex: `C:\GestorComercial\`)
- Copie os 2 arquivos para lá

### Passo 2: Criar a pasta do app
Na máquina do pai, crie:
```
C:\Users\[USUARIO]\.gestor_comercial\
```

### Passo 3: Copiar o banco para o lugar certo
Mova o arquivo `.db` que você copiou do pendrive para:
```
C:\Users\[USUARIO]\.gestor_comercial\gestor_comercial.db
```

### Passo 4: Executar o .exe
Clique 2x em `gestor_comercial.exe`

✅ **Resultado:** O app abre com TODO o cardápio, fotos e configurações já carregadas

---

## ⚠️ Pontos Importantes

### O .exe é portável
- Você pode copiar para qualquer pasta
- Não precisa instalar nada (nenhuma dependência Python)
- Pode colocar direto no pendrive e rodar de lá

### O banco fica fora do .exe
- O `.db` **não está dentro** do executável
- Ele fica na pasta `~/.gestor_comercial/` do usuário
- Isso permite que os dados persistam mesmo se reinstalar o .exe

### Primeira execução na máquina do pai
- Se o banco NÃO existir em `~/.gestor_comercial/`, o app vai criar um VAZIO
- **É por isso que você precisa copiar o `.db`** - para trazer seu cardápio completo junto

### Backup é seguro
- O arquivo `.db` é um SQLite normal
- Você pode fazer backup dele antes de passar para o pai
- Pode restaurar a qualquer momento

---

## Checklist Final Antes de Gerar o .exe

- [ ] Abri o app e deixei criar as tabelas
- [ ] Criei todas as categorias e subcategorias
- [ ] Populei o cardápio inteiro (todos os produtos)
- [ ] Adicionei as fotos de cada produto
- [ ] Testei o cardápio (lancar itens, ver preços corretos)
- [ ] Criei os combos necessários
- [ ] Adicionei os funcionários/operadores
- [ ] Testei a impressão (se aplicável)
- [ ] O app está estável e pronto
- [ ] Fechei o app (para garantir que tudo foi gravado)

**Depois de OK em tudo acima:**
```bash
pyinstaller packaging/build.spec
```

---

## Troubleshooting

### P: Gerei o .exe mas não aparece na pasta `dist/`
R: Espere a compilação terminar (pode levar alguns minutos). Procure por mensagens de erro no terminal.

### P: O .exe abre mas está vazio (sem cardápio)
R: Você não copiou o arquivo `.db` para `~/.gestor_comercial/` na máquina do pai. Copie manualmente.

### P: Quero fazer mais alterações no cardápio depois de gerar o .exe
R: Nenhum problema. Abra o app na sua máquina de desenvolvimento, faça as alterações, feche, e gere um novo .exe. O banco (`~/.gestor_comercial/gestor_comercial.db`) é sempre a fonte de verdade.

### P: Posso atualizar o app no pendrive?
R: Sim. Gere um novo `.exe`, substitua o arquivo no pendrive. O banco (`.db`) que estava lá continua, então os dados não são perdidos.

---

## Próxima Ação

Agora você pode:
1. Abrir o app
2. Começar a popular o cardápio
3. Quando terminar, volte aqui e gere o .exe

Qualquer dúvida, é só chamar! 🚀
