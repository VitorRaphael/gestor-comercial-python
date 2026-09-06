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

A tela de **Caixa** entrou depois, pelo mesmo caminho: era o defeito que a Fase
7 deixou registrado por ser anterior à faxina (§8). A coluna de resumo somava
mais altura do que a página oferece a 1366x738 e as quatro linhas de
"Recebimentos" saíam com 6px de 16px — o nome e o valor cortados ao meio.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView


def _emoldurar_pela_metade(tela: QWidget) -> QWidget:
    """Põe `tela` numa página com METADE da altura que ela pede.

    Uma moldura de altura fixa, como a página dentro do `QStackedWidget` de
    `MainWindow` — um `resize()` direto não serviria, porque como janela de
    primeiro nível o Qt recusa encolher abaixo do `minimumSizeHint` e o aperto
    nunca aconteceria.
    """
    moldura = QWidget()
    layout = QVBoxLayout(moldura)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(tela)
    moldura.setFixedSize(1000, max(120, tela.sizeHint().height() // 2))
    moldura.show()
    return moldura


def test_botoes_de_senha_nao_encolhem_quando_a_pagina_e_baixa(qapp, auth):
    tela = ConfiguracoesView(auth)
    moldura = _emoldurar_pela_metade(tela)
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


def test_linhas_de_recebimentos_nao_encolhem_quando_a_pagina_e_baixa(
    qapp, caixas_service, impressao
):
    tela = CaixaView(caixas_service, impressao)
    moldura = _emoldurar_pela_metade(tela)
    qapp.processEvents()

    nomes = ("caixaFormaNome", "caixaFormaValor")
    linhas = [r for r in tela.findChildren(QLabel) if r.objectName() in nomes]
    assert len(linhas) == 8, "as 4 formas de recebimento deveriam ter nome e valor"

    espremidas = [r for r in linhas if r.height() < r.sizeHint().height()]
    assert not espremidas, (
        f"{len(espremidas)} de {len(linhas)} linhas de Recebimentos ficaram menores "
        "que o próprio sizeHint — é assim que o texto sai cortado ao meio"
    )

    moldura.close()
