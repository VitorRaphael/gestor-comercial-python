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


def test_imprimir_fechamento_fica_desabilitado_com_o_caixa_aberto(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    """O relatório traz o saldo esperado e as diferenças: com o turno aberto,
    imprimi-lo entregaria ao operador o número que ele deveria contar."""
    tela = CaixaView(caixas_service, impressao)

    assert tela._botao_imprimir.isEnabled() is False


def test_imprimir_fechamento_nao_imprime_com_o_caixa_aberto_nem_por_codigo(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    tela = CaixaView(caixas_service, impressao)
    chamados: list[int] = []
    impressao.imprimir_fechamento_caixa = chamados.append

    tela._imprimir_fechamento()

    assert chamados == []


def test_imprimir_fechamento_habilita_depois_do_fechamento(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    """Fechado, o botão volta: é a reimpressão do último turno."""
    tela = CaixaView(caixas_service, impressao)
    caixas_service.fechar(caixa_aberto.id, Decimal("100.00"), Decimal("0"))
    tela.atualizar()

    assert tela._botao_imprimir.isEnabled() is True


def test_imprimir_fechamento_desabilita_de_novo_ao_abrir_outro_turno(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    tela = CaixaView(caixas_service, impressao)
    caixas_service.fechar(caixa_aberto.id, Decimal("100.00"), Decimal("0"))
    tela.atualizar()
    caixas_service.abrir(Decimal("50.00"))
    tela.atualizar()

    assert tela._botao_imprimir.isEnabled() is False


def test_reiniciar_o_app_com_o_caixa_fechado_mantem_a_reimpressao(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    """Uma tela nova (o app reiniciado) nunca viu o turno aberto: o último
    fechamento tem que vir do banco, e não da memória da sessão."""
    caixas_service.fechar(caixa_aberto.id, Decimal("100.00"), Decimal("0"))

    tela = CaixaView(caixas_service, impressao)

    assert tela._botao_imprimir.isEnabled() is True
    assert tela._ultimo_caixa_id == caixa_aberto.id


def test_reimpressao_aponta_para_o_fechamento_mais_recente(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    caixas_service.fechar(caixa_aberto.id, Decimal("100.00"), Decimal("0"))
    segundo = caixas_service.abrir(Decimal("50.00"))
    caixas_service.fechar(segundo.id, Decimal("50.00"), Decimal("0"))

    tela = CaixaView(caixas_service, impressao)
    chamados: list[int] = []
    impressao.imprimir_fechamento_caixa = chamados.append
    tela._botao_imprimir.click()

    assert chamados == [segundo.id]


def test_sem_nenhum_fechamento_no_banco_nao_ha_o_que_reimprimir(
    qapp, caixas_service, impressao, gerente
):
    tela = CaixaView(caixas_service, impressao)

    assert tela._botao_imprimir.isEnabled() is False
