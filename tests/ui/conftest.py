"""Rede de segurança da camada `ui/` — ver `REMASTERIZACAO-V1.md` §6, Fase 0.

Até esta pasta existir, os 621 testes do projeto cobriam services, repository e
hardware, e **nenhum** instanciava um widget: quase metade do código (~8.000
linhas em `ui/`) não tinha teste nenhum. A Remasterização mexe justamente nessa
metade, então ela precisa de rede antes de qualquer refatoração de tela.

Roda sem servidor gráfico e **sem dependência nova** (nada de `pytest-qt`): o
próprio Qt tem a plataforma `offscreen`, que renderiza num buffer de memória.
Por isso a variável de ambiente é definida aqui em cima, ANTES de qualquer
import de PySide6 — depois que o Qt escolhe a plataforma, não dá mais pra
trocar.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.pagamento_service import PagamentoService


@pytest.fixture(scope="session")
def qapp():
    """A única `QApplication` do processo de teste.

    Escopo de sessão porque o Qt não aceita duas — e `QApplication.instance()`
    cobre o caso de outro teste já ter criado a dele.
    """
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def cardapio(uow, auth):
    return CardapioService(uow, auth)


@pytest.fixture
def caixas_service(uow, auth):
    return CaixaService(uow, auth)


@pytest.fixture
def pagamentos(uow, auth, comandas, funcionarios):
    return PagamentoService(uow, auth, comandas, funcionarios)


@pytest.fixture
def impressao(uow, auth):
    return ImpressaoService(uow, auth)
