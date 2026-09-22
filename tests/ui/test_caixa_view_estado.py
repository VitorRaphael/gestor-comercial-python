"""CaixaView: nada do turno fechado fica na tela, e a tabela de movimentos não corta.

Pega dois defeitos vistos na tela de Caixa: depois de fechar, os cartões
seguiam mostrando o saldo e os ajustes do turno encerrado; e a coluna "Tipo"
encolhia até cortar a borda do badge de "REFORÇO".
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QHeaderView

from gestor_comercial.domain.enums import TipoMovimento
from gestor_comercial.ui.views.caixa_view import CaixaView


def _textos_do_resumo(tela: CaixaView) -> list[str]:
    return (
        [tela._label_saldo.text(), tela._label_recebido.text()]
        + [valor.text() for valor, _barra in tela._barras_forma.values()]
        + [label.text() for label in tela._labels_ajuste.values()]
    )


def test_fechar_o_caixa_zera_metricas_e_esvazia_tabelas(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    tela = CaixaView(caixas_service, impressao)
    caixas_service.registrar_movimento(TipoMovimento.REFORCO, Decimal("50.00"), "Troco")
    caixas_service.registrar_movimento(TipoMovimento.SANGRIA, Decimal("30.00"), "Cofre")
    tela.atualizar()
    assert tela._tabela.rowCount() == 2
    assert tela._label_saldo.text() != "R$ 0,00"

    caixas_service.fechar(caixa_aberto.id, Decimal("120.00"), Decimal("0"))
    tela.atualizar()

    assert set(_textos_do_resumo(tela)) == {"R$ 0,00"}
    assert tela._label_comandas.text() == "0"
    assert all(barra.value() == 0 for _valor, barra in tela._barras_forma.values())
    assert tela._tabela.rowCount() == 0
    assert tela._secao_cancelamentos._tabela_detalhado.rowCount() == 0
    assert not tela._botao_abrir.isHidden()
    # O histórico continua: é contexto, não dado do turno.
    assert tela._layout_fechamentos.count() > 0


def test_colunas_de_movimentos_tem_politica_explicita(qapp, caixas_service, impressao):
    cabecalho = CaixaView(caixas_service, impressao)._tabela.horizontalHeader()
    modo = QHeaderView.ResizeMode
    assert cabecalho.sectionResizeMode(0) == modo.ResizeToContents
    assert cabecalho.sectionResizeMode(1) == modo.Fixed
    assert cabecalho.sectionResizeMode(2) == modo.Stretch
    assert cabecalho.sectionResizeMode(3) == modo.ResizeToContents


def test_badge_cabe_na_coluna_tipo(qapp, caixas_service, impressao, gerente, caixa_aberto):
    tela = CaixaView(caixas_service, impressao)
    for tipo in (TipoMovimento.REFORCO, TipoMovimento.SANGRIA, TipoMovimento.DESPESA):
        caixas_service.registrar_movimento(tipo, Decimal("10.00"), "x")
    tela.resize(1366, 738)
    tela.show()
    tela.atualizar()
    qapp.processEvents()

    largura = tela._tabela.columnWidth(1)
    for linha in range(tela._tabela.rowCount()):
        celula = tela._tabela.cellWidget(linha, 1)
        assert celula.sizeHint().width() <= largura, f"badge da linha {linha} não cabe"
    tela.close()


def test_turno_aberto_mostra_so_o_fundo_de_troco_e_mascara_recebimentos(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    """Fechamento cego: com o turno aberto, o card mostra só a abertura (que o
    próprio operador digitou) e os totais por forma não aparecem — nem o valor,
    nem a barra, que entregaria a proporção."""
    tela = CaixaView(caixas_service, impressao)
    caixas_service.registrar_movimento(TipoMovimento.REFORCO, Decimal("50.00"), "Troco")
    tela.atualizar()

    assert tela._label_saldo.text() == "R$ 100,00"
    assert tela._label_recebido.text() == "R$ ***"
    assert {valor.text() for valor, _barra in tela._barras_forma.values()} == {"R$ ***"}
    assert all(barra.isHidden() for _valor, barra in tela._barras_forma.values())
