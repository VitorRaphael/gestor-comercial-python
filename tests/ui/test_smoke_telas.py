"""Toda tela monta sem estourar, e volta a montar depois de um `atualizar()`.

É o teste mais barato que existe e mesmo assim pega o erro mais comum de
refatoração de UI: um import trocado de lugar, um atributo renomeado, uma
assinatura de service alterada — coisas que hoje só apareceriam quando o pai do
Vitor clicasse no botão no meio do movimento.

Não valida aparência. Valida que a tela existe, monta e sobrevive a um ciclo de
recarga com o banco vazio (que é o pior caso: nenhuma mesa, nenhum produto,
nenhum caixa aberto).
"""

from __future__ import annotations

import pytest

from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.cardapio_view import CardapioView
from gestor_comercial.ui.views.comanda_view import ComandaView
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView
from gestor_comercial.ui.views.dashboard_mensal_view import DashboardMensalView
from gestor_comercial.ui.views.estoque_view import EstoqueView
from gestor_comercial.ui.views.funcionarios_view import FuncionariosView
from gestor_comercial.ui.views.historico_caixa_view import HistoricoCaixaView
from gestor_comercial.ui.views.impressoras_view import ImpressorasView
from gestor_comercial.ui.views.loja_hub_view import LojaHubView
from gestor_comercial.ui.views.login_view import LoginView
from gestor_comercial.ui.views.mesas_view import MesasView
from gestor_comercial.ui.views.relatorios_view import RelatoriosView


@pytest.fixture
def todas_as_telas(
    qapp, auth, comandas, cardapio, caixas_service, pagamentos, impressao, funcionarios
):
    """Uma instância de cada tela do app, montada com os services reais.

    Devolve dicionário `nome -> widget` para o erro de um teste dizer QUAL tela
    quebrou, em vez de só apontar o índice de um parametrize.
    """
    return {
        "Login": LoginView(auth),
        "Mesas": MesasView(comandas),
        "Comanda": ComandaView(comandas, cardapio, impressao, funcionarios),
        "Caixa": CaixaView(caixas_service, impressao),
        "Histórico de Caixa": HistoricoCaixaView(caixas_service, auth, impressao, funcionarios),
        "Dashboard Mensal": DashboardMensalView(caixas_service, funcionarios),
        "Relatórios": RelatoriosView(caixas_service, auth, impressao, funcionarios),
        "Cardápio": CardapioView(cardapio),
        "Funcionários": FuncionariosView(funcionarios, pagamentos, auth, caixas_service),
        "Impressoras": ImpressorasView(cardapio, impressao),
        "Configurações": ConfiguracoesView(auth),
        "Central de Loja": LojaHubView(),
        "Estoque": EstoqueView(),
    }


def test_todas_as_telas_montam(todas_as_telas):
    for nome, tela in todas_as_telas.items():
        assert tela is not None, f"{nome} não montou"


def test_todas_as_telas_sobrevivem_a_um_atualizar(todas_as_telas):
    """`atualizar()` é o que a `MainWindow` chama a cada navegação.

    Com o banco vazio — sem mesa, sem produto, sem caixa aberto — nenhuma tela
    pode estourar. Telas sem `atualizar()` (Login, Central de Loja, Estoque)
    são puladas de propósito: não têm dado pra recarregar.
    """
    for nome, tela in todas_as_telas.items():
        atualizar = getattr(tela, "atualizar", None)
        if atualizar is None:
            continue
        atualizar()  # não pode levantar
        assert tela is not None, f"{nome} não sobreviveu ao atualizar()"


def test_telas_com_dado_real_montam(
    qapp, comandas, cardapio, caixas_service, impressao, funcionarios, gerente, mesa, produto, caixa_aberto
):
    """O caminho oposto do teste acima: com caixa aberto, mesa e produto no
    banco, as telas que dependem desse estado precisam recarregar sem erro."""
    mesas_view = MesasView(comandas)
    mesas_view.carregar_mesas()

    caixa_view = CaixaView(caixas_service, impressao)
    caixa_view.atualizar()

    cardapio_view = CardapioView(cardapio)
    cardapio_view.atualizar()

    assert mesas_view is not None
