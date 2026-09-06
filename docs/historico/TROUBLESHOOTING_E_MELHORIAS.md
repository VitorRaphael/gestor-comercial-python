# 🔧 Troubleshooting & Próximas Melhorias

## 🚨 Problemas Comuns & Soluções

### Problema 1: "Nenhum usuário disponível no sistema"
**Sintoma**: Mensagem na tela de login, campos desabilitados

**Causa provável**: 
- Banco de dados vazio
- Seed do projeto não rodou
- Nenhum funcionário ativo cadastrado

**Solução**:
```bash
# Delete o banco de dados (se estiver em dev)
rm src/gestor_comercial/database/pdv.db

# Execute o app novamente para rodar as migrations + seed
python -m gestor_comercial
```

---

### Problema 2: "Dropdown mostra nomes mas PIN não funciona"
**Sintoma**: Seleciona usuário, digita PIN, recebe "A senha não corresponde"

**Causa provável**:
- PIN do funcionário é diferente do que está digitando
- Funcionário está inativo

**Solução**:
1. Verifique o PIN padrão do seed (geralmente "0000" para ADMIN)
2. Verifique se o funcionário está ativo:
   ```python
   # No DB:
   SELECT nome, ativo, pin_hash FROM funcionarios;
   ```
3. Se inativo, ative via Tela de Funcionários

---

### Problema 3: "Tab não navega entre campos"
**Sintoma**: Pressionar Tab não muda de campo

**Causa provável**:
- QComboBox/QLineEdit sem tabOrder correto
- Outro widget capturando Tab

**Solução**:
```python
# Em _montar_layout(), após montar todos os widgets:
self.setTabOrder(self._combo_usuario, self._campo_senha)
self.setTabOrder(self._campo_senha, self._botao_entrar)
self.setTabOrder(self._botao_entrar, self._combo_usuario)  # cicla
```

---

### Problema 4: "Enter não submete no campo de senha"
**Sintoma**: Pressionar Enter não faz nada

**Causa provável**:
- Sinal `returnPressed` não conectado corretamente
- Campo de senha perdeu o sinal

**Verificar**:
```python
# Em _montar_layout():
self._campo_senha.returnPressed.connect(self._tentar_login)  # ✅ Deve estar lá
```

---

### Problema 5: "Dropdown vazio ou mostra apenas um usuário"
**Sintoma**: Combo box sem itens ou com poucos itens

**Causa provável**:
- `listar_ativos()` retorna lista vazia ou pequena
- Funcionários estão inativos

**Solução**:
```python
# Debug em _carregar_usuarios():
funcionarios = self._auth_service.listar_ativos()
print(f"Funcionários ativos: {len(funcionarios)}")  # ← adicione isso
for f in funcionarios:
    print(f"  - {f.nome} (ID: {f.id}, Ativo: {f.ativo})")
```

---

## 💡 Próximas Melhorias (Recomendadas)

### 1. **Toggle de Visibilidade de Senha** ⭐ Recomendado
Adicionar botão "👁️" para mostrar/ocultar PIN

```python
# Em _montar_layout(), após criar _campo_senha:

self._botao_toggle_senha = QPushButton("👁️")
self._botao_toggle_senha.setFixedWidth(40)
self._botao_toggle_senha.setProperty("variante", "secundario")
self._botao_toggle_senha.clicked.connect(self._toggle_visibilidade_senha)

# Layout horizontal para campo + botão:
layout_senha = QHBoxLayout()
layout_senha.addWidget(self._campo_senha)
layout_senha.addWidget(self._botao_toggle_senha)
layout_cartao.addLayout(layout_senha)

# Novo método:
def _toggle_visibilidade_senha(self) -> None:
    if self._campo_senha.echoMode() == QLineEdit.EchoMode.Password:
        self._campo_senha.setEchoMode(QLineEdit.EchoMode.Normal)
        self._botao_toggle_senha.setText("🚫")
    else:
        self._campo_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self._botao_toggle_senha.setText("👁️")
```

**Benefício**: Usuário pode verificar se digitou certo antes de submeter

---

### 2. **Ícones nos Campos** ⭐ Bom para UX
Adicionar ícones de usuário e chave

```python
# Imports:
from PySide6.QtGui import QIcon

# Em _montar_layout(), para o dropdown:
label_usuario = QLabel("👤 Usuário:")  # ou usar emoji ou ícone SVG
label_senha = QLabel("🔐 Senha:")
```

**Benefício**: Visual mais moderno e intuitivo

---

### 3. **Desabilitar Campos até Seleção**
Desabilitar campo de senha enquanto não há usuário selecionado

```python
# Em _montar_layout():
self._campo_senha.setEnabled(False)  # começa desabilitado

# Em _carregar_usuarios():
self._campo_senha.setEnabled(True)  # ativa depois de carregar

# Opcional: ativar/desativar dinamicamente:
self._combo_usuario.currentIndexChanged.connect(
    lambda: self._campo_senha.setEnabled(self._combo_usuario.currentIndex() >= 0)
)
```

**Benefício**: Força fluxo correto (selecionar usuário primeiro)

---

### 4. **Animação de Erro**
Piscar o campo de senha quando há erro

```python
from PySide6.QtCore import QTimer, Qt

def _tentar_login(self) -> None:
    # ... código existente ...
    except NaoAutorizadoError as erro:
        self._label_erro.setText(str(erro))
        self._campo_senha.clear()
        self._campo_senha.setFocus()
        
        # Novo: piscar o campo
        self._piscar_campo_erro()

def _piscar_campo_erro(self) -> None:
    self._campo_senha.setStyleSheet(
        "border: 2px solid #f43f5e;"
    )
    QTimer.singleShot(200, lambda: self._campo_senha.setStyleSheet(""))
```

**Benefício**: Feedback visual mais claro de erro

---

### 5. **Caps Lock Detector**
Avisar se Caps Lock está ativo

```python
def _detectar_caps_lock(event) -> None:
    if event.type() == QKeyEvent.KeyPress:
        if event.key() in (Qt.Key.Key_CapsLock,):
            caps_ativo = not event.isAutoRepeat()
            if caps_ativo:
                self._label_erro.setText("⚠️ Caps Lock ativo!")
            else:
                self._label_erro.setText("")

# Em __init__:
self._campo_senha.installEventFilter(self)

def eventFilter(self, obj, event):
    if obj is self._campo_senha and event.type() == QEvent.KeyPress:
        self._detectar_caps_lock(event)
    return super().eventFilter(obj, event)
```

**Benefício**: Evita confusão com PIN não aceito (especialmente se tiver letras depois)

---

### 6. **Tema Escuro/Claro Toggle**
Adicionar botão para alternar tema

```python
# Não implementar aqui, mas aplicar globalmente em MainWindow
# Já que QSS é aplicado em main.py via app.setStyleSheet()
```

**Benefício**: Acessibilidade

---

### 7. **Tela de Recuperação de PIN**
Se esquecer o PIN, pode fazer "login de recuperação" com gerente

```python
# Botão "Esqueci meu PIN" que abre diálogo
# Gerente confirma que é gerente com seu PIN
# Permite resetar PIN do funcionário para um temporário
```

**Benefício**: Não precisa reiniciar o sistema manualmente

---

## 📋 Priorização de Melhorias

| # | Melhoria | Esforço | Impacto | Recomendação |
|---|----------|---------|--------|--------------|
| 1 | Toggle visibilidade | 1h | Alto | ⭐⭐⭐ Recomendado |
| 2 | Ícones nos campos | 30min | Médio | ⭐⭐ Nice to have |
| 3 | Desabilitar campos | 15min | Baixo | ⭐ Opcional |
| 4 | Animação de erro | 45min | Médio | ⭐⭐ Nice to have |
| 5 | Caps Lock detector | 1h | Baixo | ⭐ Opcional |
| 6 | Tema toggle | Longo | Alto | 📅 Futuro |
| 7 | Recuperação de PIN | Muito longo | Médio | 📅 Futuro |

---

## 🧪 Testes Recomendados (Antes de Produção)

### Teste 1: Validação de Entrada
```python
# Em test_login_view.py (novo):

def test_login_sem_usuario_selecionado():
    # Limpar dropdown
    # Clicar entrar
    # Verificar erro: "Selecione um usuário"

def test_login_sem_senha():
    # Não digitar PIN
    # Clicar entrar
    # Verificar erro: "Digite a senha"

def test_login_pin_errado():
    # Digitar PIN inválido
    # Clicar entrar
    # Verificar erro: "PIN inválido"

def test_login_usuario_errado():
    # Selecionar usuário A
    # Digitar PIN do usuário B
    # Clicar entrar
    # Verificar erro: "A senha não corresponde"
```

### Teste 2: Navegação
```python
def test_tab_navigation():
    # Verify tab order: dropdown → senha → botão
    
def test_enter_submits():
    # Focus no campo senha
    # Digitar PIN
    # Pressionar Enter
    # Verificar que fez login (ou mostrou erro)
```

### Teste 3: Integridade
```python
def test_login_com_usuario_correto():
    # Selecionar "ADMIN"
    # Digitar "0000" (PIN padrão)
    # Pressionar Enter
    # Verificar que emitiu sinal autenticado
```

---

## 📊 Métricas de Sucesso

Depois de implementar a refatoração, verificar:

| Métrica | Alvo | Como medir |
|---------|------|-----------|
| **Tempo de login** | < 3s | Cronometrar do app abrir até shell aparecer |
| **Taxa de erro PIN** | < 5% | Registrar quantas tentativas até sucesso |
| **Usabilidade (solo)** | ✅ | Um novo atendente consegue logar sem treinamento |
| **Performance** | < 500ms | App não deve travar durante login |
| **Responsividade** | ✅ | Digitar não deve ter lag, UI responsiva |

---

## 🐛 Como Reportar Bugs

Se encontrar problemas:

1. **Reproduzir** o problema (passos exatos)
2. **Capturar** o erro (console output, screenshots)
3. **Contexto**: Qual PIN, qual usuário, qual SO
4. **Esperado vs Atual**: O que deveria acontecer vs o que aconteceu

**Exemplo de bug bem reportado:**
```
Título: "Login não funciona com PIN que tem espaço"
Passos:
1. Criar funcionário com PIN " 0000 " (espaços)
2. Tentar fazer login com "0000"
3. Esperado: Login OK (trim do PIN)
4. Atual: "PIN inválido"
```

---

## ✅ Validação Final

Antes de considerar a refatoração "pronta":

- [ ] App não lança exceções ao iniciar
- [ ] Tela de login abre sem erros
- [ ] Dropdown mostra todos os funcionários ativos
- [ ] ADMIN está pré-selecionado
- [ ] Tab navega entre campos
- [ ] Enter submete o login
- [ ] Pin correto → entra no app
- [ ] Pin incorreto → mostra erro
- [ ] Usuário incorreto → mostra erro
- [ ] Campos se limpam após erro
- [ ] Focus retorna ao campo de senha após erro
- [ ] App responde rápido (sem travamentos)
- [ ] Layout é responsivo em diferentes tamanhos

---

**Qualquer dúvida, só chamar!** 🚀
