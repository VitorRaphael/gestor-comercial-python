# 🔄 Refatoração da Tela de Login

## O que foi mudado

### 1. **LoginView refatorada** (`src/gestor_comercial/ui/views/login_view.py`)
- ✅ **Removido**: Teclado virtual em tela (pin pad) com botões numéricos
- ✅ **Adicionado**: QComboBox para seleção de usuários/funcionários ativos
- ✅ **Adicionado**: QLineEdit padrão para entrada de PIN (tipo "password")
- ✅ **Melhorado**: Suporte completo a teclado físico (Tab, Enter)
- ✅ **Automático**: Focus é direcionado para o campo de senha (usuário ADMIN pré-selecionado)
- ✅ **Feedback**: Mensagens de erro claras e intuitivas

### 2. **Estilos atualizados** (`resources/qss/base.qss`)
- ✅ **Adicionado**: Estilos consistentes para QComboBox
- ✅ **Tema**: Segue o design system existente (escuro, cores da paleta do projeto)
- ✅ **Responsividade**: Dropdown com itens bem espaçados e legíveis

---

## ✨ Fluxo de Uso

1. **Iniciar app** → Tela de login abre
2. **Usuário pré-selecionado** → "ADMIN" (primeiro da lista de ativos)
3. **Campo de senha com focus** → Pronto para digitação via teclado
4. **Navegação via Tab** → Navega entre: Dropdown → Campo de senha → Botão "Acessar"
5. **Submissão**:
   - Pressionar **Enter** no campo de senha = submete automaticamente
   - Clicar no botão **"Acessar"** = submete também
6. **Validação**:
   - Verifica se um usuário está selecionado
   - Valida o PIN digitado
   - Confirma se o PIN pertence ao usuário selecionado
7. **Sucesso** → Emite `autenticado` e o app passa para a tela principal

---

## 🔐 Segurança & Lógica de Autenticação

- ✅ **PIN continua criptografado** (SHA-256 + Salt, igual antes)
- ✅ **Validação dupla**: Usuário selecionado + PIN do usuário devem bater
- ✅ **Proteção contra timing attacks** mantida (hmac.compare_digest)
- ✅ **AuthService.login()** continua funcionando igual
- ✅ **Nenhuma mudança no banco de dados**

---

## 📝 Instruções de Teste

### Teste Visual Local
```bash
# Terminal, a partir da raiz do projeto
python -m gestor_comercial
```

**Passos para validar:**
1. App abre com tela de login
2. Dropdown mostra usuários (ex: "ADMIN", "Atendente", etc.)
3. "ADMIN" vem pré-selecionado
4. Focus automático no campo de senha
5. Digite um PIN e pressione Enter → deve autenticar ou exibir erro
6. Tente clicar no botão "Acessar" → mesma coisa
7. Teste Tab para navegar entre os campos
8. Tente errar o PIN → mensagem "PIN inválido." aparece
9. Tente selecionar outro usuário no dropdown → deve funcionar

### Teste com PIN correto
- Default no seed: Funcionário "Gerente" tem PIN **"0000"**
- Selecione "ADMIN" no dropdown (se for o gerente padrão)
- Digite **0000** e pressione Enter
- Deve entrar na tela principal

---

## 📦 Arquivos Modificados

```
src/gestor_comercial/ui/views/login_view.py
├─ Classe LoginView
│  ├─ _montar_layout() [refatorado]
│  ├─ _carregar_usuarios() [novo]
│  ├─ _tentar_login() [atualizado]
│  └─ Removido: _montar_teclado(), _tecla_pressionada()

resources/qss/base.qss
├─ Adicionado: Estilos para QComboBox
├─ Adicionado: Estilos para QAbstractItemView (dropdown items)
└─ Mantido: Todos os estilos antigos
```

---

## 🚀 Próximos Passos (Opcionais)

1. **Bônus - Toggle de visibilidade de senha**:
   - Adicionar um botão com ícone "olho" perto do campo de senha
   - Clicar alterna entre `QLineEdit.Password` e `QLineEdit.Normal`

2. **Melhorias de UX**:
   - Desabilitar campo de senha até que um usuário seja selecionado
   - Adicionar ícones de usuário/chave no dropdown e campo
   - Animação suave ao focar nos campos

3. **Acessibilidade**:
   - Adicionar labels associadas (já feito com `QLabel` acima dos campos)
   - Tab order automático (PySide6 já cuida disso)

---

## ⚠️ Notas Importantes

- **PIN continua sendo necessário** (não é senha em texto livre)
- **Banco de dados não foi tocado** (compatível com dados existentes)
- **AuthService.login() não mudou** (mesma validação de antes)
- **Nenhuma quebra de compatibilidade** com outras views ou services

---

## ✅ Checklist de Validação

- [ ] App inicia sem erros
- [ ] Tela de login abre com dropdown visível
- [ ] ADMIN pré-selecionado
- [ ] Focus automático no campo de senha
- [ ] Tab navega entre campos
- [ ] Enter submete o login
- [ ] Botão "Acessar" também submete
- [ ] Erros são exibidos corretamente
- [ ] Login com PIN correto funciona
- [ ] App passa para tela principal

---

Qualquer dúvida ou ajuste necessário, é só avisar! 🎯
