"""Trocar uma propriedade de estilo e fazer o QSS reavaliar o widget.

Ver `REMASTERIZACAO-V1.md` §3.15.

O Qt calcula o estilo de um widget **uma vez**, no primeiro `polish`. Depois
disso, mudar uma propriedade lida por seletor (`QLabel[tom="sucesso"]`,
`QPushButton[variante="perigo-tabela"]`) não repinta nada sozinho: o
`setProperty` entra no objeto, e o QSS continua mostrando a regra antiga até
alguém pedir o recálculo. Por isso `setProperty` sem `unpolish`/`polish` é um
bug silencioso — o valor está certo no objeto e errado na tela.

O par estava copiado em nove lugares da UI. Aqui ele é um só.

## Por que isto existe, e não mais `setStyleSheet` inline

O §3.15 pegou onze cópias do mesmo `setStyleSheet(f"color: {tokens[...]}")`
resolvidas **na construção** da tela. Como `setStyleSheet` por widget tem
precedência sobre o QSS global, a cor do tema do boot vencia para sempre:
alternar Claro/Escuro repintava o app inteiro, menos aquelas linhas. Passando a
cor para o QSS global e deixando aqui só a propriedade, a troca de tema volta a
funcionar de graça — o `ThemeController` já reconstrói o QSS inteiro.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def repolir(widget: QWidget) -> None:
    """Manda o Qt recalcular o estilo do widget agora.

    Use direto quando o que mudou foi o `objectName` (seletor `#id`), que não
    passa por `aplicar_propriedade` — `caixa_view` troca o nome do valor de
    ajuste entre positivo e negativo, `kpi_card` entre os tons do KPI.
    """
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def aplicar_propriedade(widget: QWidget, nome: str, valor: object) -> None:
    """Define a propriedade e força o QSS a reavaliar o widget na hora.

    Use sempre que a propriedade puder mudar **depois** de a tela existir. Para
    widget que nasce já com o valor final, o `setProperty` sozinho basta — o
    primeiro `polish` ainda não aconteceu.
    """
    widget.setProperty(nome, valor)
    repolir(widget)
