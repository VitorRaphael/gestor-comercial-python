"""Assinatura manuscrita do consumo interno: captura, Gestão de Consumo e detalhe.

O caminho do caixa (assinatura no lugar do PIN) é coberto em
`test_pagamento_view.py`; aqui ficam as peças novas isoladas.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from gestor_comercial.domain.enums import FormaPagamento
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.assinatura import ler_assinatura
from gestor_comercial.ui.views import gestao_consumo_view
from gestor_comercial.ui.views.funcionarios_view import FuncionariosView
from gestor_comercial.ui.views.gestao_consumo_view import GestaoConsumoView
from gestor_comercial.ui.widgets.modal_assinatura_manuscrita import ModalAssinaturaManuscrita
from gestor_comercial.ui.widgets.modal_detalhes_retirada import ModalDetalhesRetirada
from gestor_comercial.ui.widgets.signature_pad import COR_PAPEL, desenhar_assinatura
from tests.conftest import PIN_GERENTE

ASSINATURA = '{"v":1,"w":400,"h":150,"tracos":[[[20,100],[80,40],[140,110],[200,60],[260,100]]]}'


@pytest.fixture
def garcom(funcionarios, gerente):
    return funcionarios.criar("Lucas Prado", "Garçom")


@pytest.fixture
def com_duas_retiradas(uow, comandas, pagamentos, gerente, caixa_aberto, categoria, garcom):
    produto = uow.produtos.salvar(Produto(nome="Refri", preco=Decimal("3.50"), categoria_id=categoria.id))
    for quantidade in (1, 2):
        comanda = comandas.abrir_balcao()
        comandas.lancar_item(comanda.id, produto.id, quantidade)
        comandas.fechar_para_conferencia(comanda.id)
        pagamentos.registrar(
            comanda.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("3.50") * quantidade,
            funcionario_consumo_id=garcom.id,
            traco_assinatura=ASSINATURA,
        )
    return garcom


# --- SignaturePadWidget / ModalAssinaturaManuscrita -------------------------


def test_confirmar_so_habilita_com_traco_e_limpar_desabilita(qapp):
    modal = ModalAssinaturaManuscrita("Lucas Prado", 3, Decimal("7.00"))
    modal.resize(600, 460)
    modal.show()
    pad = modal.pad
    assert modal.botao_confirmar.isEnabled() is False
    assert "3 itens" in modal._label_resumo.text() and "R$ 7,00" in modal._label_resumo.text()

    QTest.mousePress(pad, Qt.MouseButton.LeftButton, pos=QPoint(20, 60))
    QTest.mouseMove(pad, QPoint(80, 90))
    QTest.mouseMove(pad, QPoint(140, 50))
    QTest.mouseRelease(pad, Qt.MouseButton.LeftButton, pos=QPoint(140, 50))
    assert modal.botao_confirmar.isEnabled() is True

    modal.botao_limpar.click()
    assert modal.botao_confirmar.isEnabled() is False
    assert pad.tem_traco is False
    modal.close()


def test_confirmar_serializa_o_traco_desenhado(qapp):
    modal = ModalAssinaturaManuscrita("Lucas Prado", 1, Decimal("3.50"))
    modal.show()
    pad = modal.pad
    QTest.mousePress(pad, Qt.MouseButton.LeftButton, pos=QPoint(30, 40))
    QTest.mouseMove(pad, QPoint(90, 80))
    QTest.mouseRelease(pad, Qt.MouseButton.LeftButton, pos=QPoint(90, 80))

    modal.botao_confirmar.click()

    assinatura = ler_assinatura(modal.traco_json)
    assert assinatura.tracos[0][0] == (30, 40)
    assert (assinatura.largura, assinatura.altura) == (pad.width(), pad.height())


def test_redesenho_pinta_tinta_escalada_no_quadro(qapp):
    """O mesmo traço redesenhado num quadro 2x maior cai nos pontos escalados."""
    assinatura = ler_assinatura(ASSINATURA)
    imagem = QImage(800, 300, QImage.Format.Format_RGB32)
    imagem.fill(COR_PAPEL)
    pintor = QPainter(imagem)
    desenhar_assinatura(pintor, QRectF(0, 0, 800, 300), assinatura.tracos, 400, 150)
    pintor.end()

    # (260, 100) é o fim do traço — no quadro 2x, (520, 200).
    assert QColor(imagem.pixel(520, 200)) != COR_PAPEL
    assert QColor(imagem.pixel(700, 20)) == COR_PAPEL


# --- Funcionários → Gestão de Consumo -------------------------------------


def test_o_botao_da_barra_virou_ver_consumo(qapp, funcionarios, pagamentos, auth, gerente):
    tela = FuncionariosView(funcionarios, pagamentos, auth)
    textos = [b.text() for b in tela.findChildren(QPushButton)]
    assert "Ver consumo" in textos
    assert "Dar baixa no consumo" not in textos


# --- Gestão de Consumo ----------------------------------------------------


def test_gestao_lista_as_retiradas_e_nao_tem_mais_o_confirmar_e_assinar(
    qapp, pagamentos, auth, com_duas_retiradas
):
    tela = GestaoConsumoView(com_duas_retiradas.id, "Lucas Prado", pagamentos, auth)

    assert len(tela.cartoes) == 2
    assert all(c.sessao.ativa for c in tela.cartoes)
    textos = [b.text() for b in tela.findChildren(QPushButton)]
    assert not any("Confirmar e Assinar" in t for t in textos)
    assert tela.botao_baixa.text().endswith("Dar baixa no consumo")
    assert tela.botao_baixa.isEnabled()


def test_dois_cliques_no_cartao_abrem_o_detalhe_com_itens_e_assinatura(
    qapp, pagamentos, auth, com_duas_retiradas
):
    tela = GestaoConsumoView(com_duas_retiradas.id, "Lucas Prado", pagamentos, auth)
    abertos = []
    with patch.object(gestao_consumo_view, "executar_modal", side_effect=lambda m: abertos.append(m)):
        QTest.mouseDClick(tela.cartoes[0], Qt.MouseButton.LeftButton)

    (modal,) = abertos
    assert isinstance(modal, ModalDetalhesRetirada)
    # A mais nova primeiro: 2 x R$ 3,50.
    assert modal.label_total.text() == "R$ 7,00"
    assert len(modal.linhas_itens) == 1
    assert modal.quadro_assinatura.assinatura == ler_assinatura(ASSINATURA)


def test_dar_baixa_arquiva_tudo_e_o_historico_mantem_a_assinatura(
    qapp, pagamentos, auth, com_duas_retiradas
):
    tela = GestaoConsumoView(com_duas_retiradas.id, "Lucas Prado", pagamentos, auth)

    with patch.object(tela, "_pedir_pin", return_value=PIN_GERENTE):
        tela.botao_baixa.click()

    assert tela.label_erro.text() == ""
    assert pagamentos.calcular_saldo_devedor(com_duas_retiradas.id) == Decimal("0.00")
    assert [c.sessao.ativa for c in tela.cartoes] == [False, False]
    assert all(c.sessao.traco_json for c in tela.cartoes)
    assert tela.botao_baixa.isEnabled() is False
