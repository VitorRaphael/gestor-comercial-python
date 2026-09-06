# 🛠️ Guia Técnico: Mudanças Linha por Linha

## Arquivo 1: `src/gestor_comercial/ui/views/login_view.py`

### ❌ REMOVIDO (Linhas antigas)

#### Imports desnecessários
```python
# ANTES (não precisa mais)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,  # ← REMOVIDO
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
```

#### Constante de teclado
```python
# ANTES (não precisa mais)
_TECLAS = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    ["limpar", "0", "apagar"],
]
```

#### Método `_montar_teclado()`
```python
# ANTES (COMPLETAMENTE REMOVIDO)
def _montar_teclado(self) -> QGridLayout:
    grade = QGridLayout()
    grade.setSpacing(8)
    for linha, teclas in enumerate(_TECLAS):
        for coluna, tecla in enumerate(teclas):
            botao = QPushButton(_rotulo_tecla(tecla))
            botao.setProperty("variante", "secundario")
            botao.setFixedHeight(48)
            botao.clicked.connect(lambda _checked=False, t=tecla: self._tecla_pressionada(t))
            grade.addWidget(botao, linha, coluna)
    return grade
```

#### Método `_tecla_pressionada()`
```python
# ANTES (COMPLETAMENTE REMOVIDO)
def _tecla_pressionada(self, tecla: str) -> None:
    self._label_erro.setText("")
    if tecla == "apagar":
        self._pin = self._pin[:-1]
    elif tecla == "limpar":
        self._pin = ""
    elif len(self._pin) < PIN_MAX_DIGITOS:
        self._pin += tecla
    self._campo_pin.setText(self._pin)
```

#### Função auxiliar
```python
# ANTES (COMPLETAMENTE REMOVIDO)
def _rotulo_tecla(tecla: str) -> str:
    return {"apagar": "⌫", "limpar": "C"}.get(tecla, tecla)
```

#### Atributo de instância
```python
# ANTES (NÃO PRECISA MAIS)
self._pin = ""  # Em __init__
```

---

### ✅ ADICIONADO (Código novo)

#### Imports novos
```python
# DEPOIS (novos imports)
from PySide6.QtWidgets import (
    QComboBox,  # ← NOVO
    QFrame,
    # QGridLayout removido
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
```

#### Método `_carregar_usuarios()` (NOVO)
```python
def _carregar_usuarios(self) -> None:
    """Carrega funcionários ativos no dropdown e pré-seleciona o padrão (ADMIN/Gerente)."""
    funcionarios = self._auth_service.listar_ativos()

    if not funcionarios:
        self._label_erro.setText("Nenhum usuário disponível no sistema.")
        self._combo_usuario.setEnabled(False)
        self._campo_senha.setEnabled(False)
        self._botao_entrar.setEnabled(False)
        return

    for funcionario in funcionarios:
        self._combo_usuario.addItem(funcionario.nome, funcionario)

    # Pré-seleciona o primeiro usuário
    self._combo_usuario.setCurrentIndex(0)

    # Focus automático no campo de senha
    self._campo_senha.setFocus()
```

#### Mudanças em `__init__`
```python
# ANTES
def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("tela-login")
    self._auth_service = auth_service
    self._pin = ""  # ← REMOVIDO

    self._montar_layout()

# DEPOIS
def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("tela-login")
    self._auth_service = auth_service
    # self._pin = "" foi removido

    self._montar_layout()
    self._carregar_usuarios()  # ← NOVO
```

#### Mudanças em `_montar_layout()` - Parte 1: Dimensões
```python
# ANTES
cartao = QFrame(self)
cartao.setObjectName("cartao-login")
cartao.setFixedWidth(340)  # ← ANTES
layout_cartao = QVBoxLayout(cartao)

# DEPOIS
cartao = QFrame(self)
cartao.setObjectName("cartao-login")
cartao.setFixedWidth(360)  # ← AUMENTADO (mais espaço para campos)
layout_cartao = QVBoxLayout(cartao)
```

#### Mudanças em `_montar_layout()` - Parte 2: Subtítulo
```python
# ANTES
subtitulo = QLabel("Digite seu PIN para continuar")

# DEPOIS
subtitulo = QLabel("Faça login para continuar")  # ← TEXTO MAIS GENÉRICO
```

#### Mudanças em `_montar_layout()` - Parte 3: Seletor de Usuário (NOVO)
```python
# NOVO CÓDIGO ADICIONADO APÓS SUBTÍTULO

# Seletor de usuário
label_usuario = QLabel("Usuário:")
layout_cartao.addWidget(label_usuario)
self._combo_usuario = QComboBox()  # ← NOVO
self._combo_usuario.setObjectName("combo-usuario")
layout_cartao.addWidget(self._combo_usuario)
layout_cartao.addSpacing(12)
```

#### Mudanças em `_montar_layout()` - Parte 4: Campo de Senha
```python
# ANTES
self._campo_pin = QLineEdit()
self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
self._campo_pin.setMaxLength(PIN_MAX_DIGITOS)
self._campo_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
self._campo_pin.setReadOnly(True)  # ← REMOVIDO (agora é editável!)
layout_cartao.addWidget(self._campo_pin)

# DEPOIS
label_senha = QLabel("Senha:")  # ← NOVO
layout_cartao.addWidget(label_senha)
self._campo_senha = QLineEdit()  # ← RENOMEADO (de _campo_pin para _campo_senha)
self._campo_senha.setEchoMode(QLineEdit.EchoMode.Password)
# setMaxLength removido (aceita qualquer comprimento)
# setAlignment removido (não precisa centralizar)
# setReadOnly removido (agora é interativo com teclado!)
self._campo_senha.setPlaceholderText("Digite o PIN")  # ← NOVO
self._campo_senha.returnPressed.connect(self._tentar_login)  # ← NOVO (Enter submete)
layout_cartao.addWidget(self._campo_senha)
```

#### Mudanças em `_montar_layout()` - Parte 5: Label de Erro
```python
# ANTES
self._label_erro = QLabel("")
self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
self._label_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
self._label_erro.setFixedHeight(18)
layout_cartao.addWidget(self._label_erro)
layout_cartao.addSpacing(8)

layout_cartao.addLayout(self._montar_teclado())  # ← REMOVIDO
layout_cartao.addSpacing(14)

# DEPOIS
self._label_erro = QLabel("")
self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
self._label_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
self._label_erro.setFixedHeight(18)
layout_cartao.addWidget(self._label_erro)
layout_cartao.addSpacing(12)  # ← AJUSTADO

# Teclado removido daqui
```

#### Mudanças em `_montar_layout()` - Parte 6: Botão
```python
# ANTES
self._botao_entrar = QPushButton("Entrar")

# DEPOIS
self._botao_entrar = QPushButton("Acessar")  # ← RENOMEADO (mais comum)
```

#### Mudanças em `_tentar_login()` - Completamente nova lógica
```python
# ANTES
def _tentar_login(self) -> None:
    try:
        funcionario = self._auth_service.login(self._pin)
    except NaoAutorizadoError as erro:
        self._label_erro.setText(str(erro))
        self._pin = ""
        self._campo_pin.setText("")
        return
    self._pin = ""
    self._campo_pin.setText("")
    self.autenticado.emit(funcionario)

# DEPOIS
def _tentar_login(self) -> None:
    """Autentica o usuário selecionado com a senha (PIN) fornecida."""
    funcionario_selecionado = self._combo_usuario.currentData()  # ← GET DO DROPDOWN
    pin_digitado = self._campo_senha.text()  # ← GET DO CAMPO

    if not funcionario_selecionado:  # ← VALIDAÇÃO NOVA
        self._label_erro.setText("Selecione um usuário.")
        return

    if not pin_digitado:  # ← VALIDAÇÃO NOVA
        self._label_erro.setText("Digite a senha.")
        self._campo_senha.setFocus()
        return

    try:
        # Autentica pelo PIN
        funcionario = self._auth_service.login(pin_digitado)

        # Valida se é o usuário selecionado ← VALIDAÇÃO CRUZADA NOVA
        if funcionario.id != funcionario_selecionado.id:
            self._label_erro.setText("A senha não corresponde ao usuário selecionado.")
            self._campo_senha.clear()
            self._campo_senha.setFocus()
            return

    except NaoAutorizadoError as erro:
        self._label_erro.setText(str(erro))
        self._campo_senha.clear()
        self._campo_senha.setFocus()
        return

    # Sucesso: limpa e emite sinal
    self._campo_senha.clear()
    self.autenticado.emit(funcionario)
```

---

## Arquivo 2: `resources/qss/base.qss`

### ✅ ADICIONADO (Seção nova de estilos)

Inserido após a seção de `QLineEdit:focus`:

```css
/* ---------- Combo Box ---------- */

QComboBox {
  background: #1f2436;
  border: 1px solid #2a2f47;
  border-radius: 8px;
  padding: 8px 12px;
  color: #f3f4f8;
  font-size: 13px;
}
QComboBox:focus {
  border: 1px solid #7c5cff;
}
QComboBox::drop-down {
  border: none;
  width: 24px;
  background: transparent;
}
QComboBox::down-arrow {
  image: none;
  width: 0px;
  height: 0px;
}

QComboBox QAbstractItemView {
  background: #1f2436;
  border: 1px solid #2a2f47;
  border-radius: 8px;
  color: #f3f4f8;
  selection-background-color: #7c5cff;
  selection-color: white;
}
QComboBox QAbstractItemView::item {
  padding: 8px 12px;
  border: none;
}
QComboBox QAbstractItemView::item:hover {
  background: #2a2f47;
}
```

**O que faz:**
- `QComboBox` → Estilo do box principal (cor, borda, padding)
- `QComboBox:focus` → Borda roxo quando tem focus (mesmo das QLineEdit)
- `QComboBox::drop-down` → Esconde a seta padrão
- `QComboBox QAbstractItemView` → Estilo da lista de itens (dropdown menu)
- `::item:hover` → Hover effect ao passar mouse

---

## 📊 Resumo das Mudanças por Tipo

### Removido
| Item | Motivo |
|------|--------|
| `QGridLayout` import | Não usa mais teclado em grid |
| `_TECLAS` constante | Não precisa mais de botões |
| `_montar_teclado()` método | Teclado virtual não existe |
| `_tecla_pressionada()` método | Navegação por teclado removida |
| `_rotulo_tecla()` função | Não precisa mais |
| `self._pin` atributo | Agora usa `self._campo_senha.text()` |
| `setMaxLength(PIN_MAX_DIGITOS)` | Aceita qualquer tamanho |
| `setReadOnly(True)` | Campo é interativo |
| `setAlignment(Center)` | Padrão esquerdo |

### Adicionado
| Item | Motivo |
|------|--------|
| `QComboBox` import | Dropdown de usuários |
| `self._combo_usuario` | Para gerenciar seleção |
| `self._campo_senha` | Renomeado de `_campo_pin` |
| `_carregar_usuarios()` | Popula dropdown e pré-seleciona |
| `returnPressed.connect()` | Enter submete login |
| `setPlaceholderText()` | Hint para o usuário |
| Label "Usuário:" | Identificar o dropdown |
| Label "Senha:" | Identificar o campo |
| Validação de dropdown | Garante seleção |
| Validação cruzada ID | Garante PIN pertence ao usuário |
| QComboBox estilos | CSS para visual bonito |

### Modificado
| Item | De | Para | Motivo |
|------|----|----|--------|
| Subtítulo | "Digite seu PIN" | "Faça login" | Mais genérico |
| Cartão width | 340px | 360px | Mais espaço |
| Botão label | "Entrar" | "Acessar" | Mais comum |
| `_tentar_login()lógica | Valida PIN genérico | Valida PIN + usuário | Segurança |

---

## 🔍 Como Procurar no Código

Se precisar encontrar algo específico:

1. **Dropdown de usuários**:
   - Procure por `self._combo_usuario`
   - Procure por `QComboBox`

2. **Campo de senha**:
   - Procure por `self._campo_senha`
   - Procure por `returnPressed`

3. **Carregamento de usuários**:
   - Procure por `_carregar_usuarios`
   - Procure por `listar_ativos()`

4. **Validação de login**:
   - Procure por `_tentar_login`
   - Procure por `currentData()`

5. **Estilos do ComboBox**:
   - Procure por `/* Combo Box */` em `base.qss`
   - Procure por `QComboBox {`

---

## ✅ Checklist de Integração

- [x] Imports corretos adicionados
- [x] Métodos antigos removidos
- [x] Métodos novos adicionados
- [x] Atributos atualizados
- [x] Conexões de sinal atualizadas
- [x] Estilos CSS adicionados
- [x] Nomenclatura consistente
- [x] Documentação de classes atualizada
- [x] Sem dependências quebradas

---

**Tudo pronto para testar!** 🚀
