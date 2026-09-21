"""A esteira do cabeçalho da mesa: Atendimento → Produção → Conferência → Pagamento.

§9.27. Quem decide em que etapa a conta está é o service
(`PainelDaComanda.etapa`); a esteira só pinta. Toda etapa antes da atual já foi
feita (visto verde), a atual acende no âmbar da marca com o próprio glifo, e as
seguintes ficam apagadas.

Montada uma vez, com a tela: são quatro marcas, quatro rótulos e três setas, e
trocar de etapa é trocar uma propriedade e pedir repintura — nada é criado de
novo. A marca é pintada à mão, e não um `QLabel` com emoji, pelo motivo de
sempre dos glifos (§9.4): o emoji sai colorido, chapado e fora do tema.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.comanda_service import EtapaDaComanda
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ARQUIVO_TEXTO,
    GLIFO_CIFRAO,
    GLIFO_DOCUMENTO_VISTO,
    GLIFO_PANELA,
    GLIFO_SETA_DIREITA,
    GLIFO_VISTO,
    GlifoSolto,
    desenhar_glifo,
)
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade

# As quatro etapas, na ordem da esteira: rótulo e glifo de cada uma.
ETAPAS = (
    (EtapaDaComanda.ATENDIMENTO, "Atendimento", GLIFO_ARQUIVO_TEXTO),
    (EtapaDaComanda.PRODUCAO, "Produção", GLIFO_PANELA),
    (EtapaDaComanda.CONFERENCIA, "Conferência", GLIFO_DOCUMENTO_VISTO),
    (EtapaDaComanda.PAGAMENTO, "Pagamento", GLIFO_CIFRAO),
)


class EstadoDaEtapa(Enum):
    FEITA = "feita"
    ATUAL = "atual"
    A_CAMINHO = "a_caminho"


def estado_da_etapa(etapa: EtapaDaComanda, atual: EtapaDaComanda | None) -> EstadoDaEtapa:
    """A regra da esteira inteira: antes da atual é feita, depois é a caminho.

    Comanda cancelada (`atual` None) não anda: tudo a caminho.
    """
    if atual is None or etapa > atual:
        return EstadoDaEtapa.A_CAMINHO
    return EstadoDaEtapa.ATUAL if etapa == atual else EstadoDaEtapa.FEITA


class _MarcaDaEtapa(QWidget):
    """O círculo com o glifo da etapa, pintado nos tokens do estado."""

    LADO_PX = 26

    def __init__(self, glifo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glifo = glifo
        self._estado = EstadoDaEtapa.A_CAMINHO
        self.setObjectName("mesaDetMarcaEtapa")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def estado(self) -> EstadoDaEtapa:
        return self._estado

    def definir(self, estado: EstadoDaEtapa) -> None:
        if estado is self._estado:
            return
        self._estado = estado
        self.update()

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        tokens = ThemeController.instancia().tokens_atuais
        if self._estado is EstadoDaEtapa.ATUAL:
            fundo, borda, tinta = "mesa_detalhe_etapa_atual_bg", "mesa_detalhe_etapa_atual", "mesa_detalhe_etapa_atual"
        elif self._estado is EstadoDaEtapa.FEITA:
            fundo, borda, tinta = "mesa_detalhe_etapa_bg", "mesa_detalhe_etapa_borda", "mesa_detalhe_etapa_feita"
        else:
            fundo, borda, tinta = "mesa_detalhe_etapa_bg", "mesa_detalhe_etapa_borda", "mesa_detalhe_etapa_texto"
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(QPen(cor_do_token(tokens[borda]), 1.0))
        pintor.setBrush(cor_do_token(tokens[fundo]))
        pintor.drawEllipse(area)
        lado = area.width() * 0.5
        alvo = QRectF(area.center().x() - lado / 2.0, area.center().y() - lado / 2.0, lado, lado)
        glifo = GLIFO_VISTO if self._estado is EstadoDaEtapa.FEITA else self._glifo
        desenhar_glifo(pintor, glifo, alvo, cor_do_token(tokens[tinta]), 2.0)
        pintor.end()


class EsteiraDeStatus(QWidget):
    """As quatro etapas lado a lado, com a seta entre uma e outra."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mesaDetEsteira")
        self._marcas: dict[EtapaDaComanda, _MarcaDaEtapa] = {}
        self._rotulos: dict[EtapaDaComanda, QLabel] = {}

        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)
        for posicao, (etapa, rotulo, glifo) in enumerate(ETAPAS):
            if posicao:
                linha.addSpacing(2)
                linha.addWidget(
                    GlifoSolto(GLIFO_SETA_DIREITA, 12, "mesa_detalhe_etapa_seta"),
                    0,
                    Qt.AlignmentFlag.AlignVCenter,
                )
                linha.addSpacing(2)
            marca = _MarcaDaEtapa(glifo)
            linha.addWidget(marca, 0, Qt.AlignmentFlag.AlignVCenter)
            texto = QLabel(rotulo)
            texto.setObjectName("mesaDetEtapaRotulo")
            texto.setProperty("estado", EstadoDaEtapa.A_CAMINHO.value)
            linha.addWidget(texto, 0, Qt.AlignmentFlag.AlignVCenter)
            self._marcas[etapa] = marca
            self._rotulos[etapa] = texto

    def mostrar(self, atual: EtapaDaComanda | None) -> None:
        for etapa, _rotulo, _glifo in ETAPAS:
            estado = estado_da_etapa(etapa, atual)
            self._marcas[etapa].definir(estado)
            texto = self._rotulos[etapa]
            if texto.property("estado") != estado.value:
                aplicar_propriedade(texto, "estado", estado.value)

    def estado(self, etapa: EtapaDaComanda) -> EstadoDaEtapa:
        """O estado pintado agora — o que o teste confere."""
        return self._marcas[etapa].estado
