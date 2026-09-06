"""As telas não podem espremer o próprio conteúdo até ficar ilegível.

Achado da Fase 7 (`REMASTERIZACAO-V1.md` §6): a bancada `tools/comparar_telas.py`
mostrou a tela de Configurações com os quatro botões "Alterar"/"Cadastrar" de
Senhas e Acesso reduzidos a pílulas sem rótulo, e os rótulos das linhas
sobrepostos. Não era cor nem fonte: com a seção "Cópia de Segurança" (Fase 2),
o conteúdo passou a somar mais altura do que a área de página oferece num
monitor de 768px — a classe de máquina do food truck — e um `QVBoxLayout` sem
rolagem espreme os filhos abaixo do tamanho natural em vez de rolar. O botão é
o primeiro a sumir porque é o que mais aceita encolher.

A moldura do teste é apertada em relação ao que a PRÓPRIA tela pede (metade do
`sizeHint`), e não num número absoluto de pixels: a suíte roda na plataforma
`offscreen`, que sobe sem banco de fontes, e ali todo texto mede diferente. Com
a medida relativa, o teste reprova pelo aperto de verdade em qualquer máquina.
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView


def test_botoes_de_senha_nao_encolhem_quando_a_pagina_e_baixa(qapp, auth):
    tela = ConfiguracoesView(auth)
    # Metade da altura que a tela pede. Uma moldura de altura fixa, como a
    # página dentro do `QStackedWidget` de `MainWindow` — um `resize()` direto
    # não serviria, porque como janela de primeiro nível o Qt recusa encolher
    # abaixo do `minimumSizeHint` e o aperto nunca aconteceria.
    moldura = QWidget()
    layout = QVBoxLayout(moldura)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(tela)
    moldura.setFixedSize(1000, max(120, tela.sizeHint().height() // 2))
    moldura.show()
    qapp.processEvents()

    rotulos = ("Alterar", "Cadastrar")
    botoes = [b for b in tela.findChildren(QPushButton) if b.text() in rotulos]
    assert len(botoes) == 4, "as 4 linhas de Senhas e Acesso deveriam ter botão"

    espremidos = [b for b in botoes if b.height() < b.sizeHint().height()]
    assert not espremidos, (
        f"{len(espremidos)} de {len(botoes)} botões de Senhas e Acesso ficaram "
        "menores que o próprio sizeHint — é assim que o rótulo some da tela"
    )

    moldura.close()
