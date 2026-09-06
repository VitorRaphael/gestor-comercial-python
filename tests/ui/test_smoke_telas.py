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

from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.cardapio_view import CardapioView
from gestor_comercial.ui.views.mesas_view import MesasView

# A fixture `todas_as_telas` mora em `conftest.py`: o teste de vazamento das
# telas varre a mesma lista, e ter uma fonte só é o que garante que tela nova
# entra nas duas redes de uma vez.


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
