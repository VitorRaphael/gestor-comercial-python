from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gestor_comercial.domain import *  # noqa: F401,F403 - registra os mappers
from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.repository.base import Base
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService

PIN_GERENTE = "111111"
PIN_ATENDENTE = "222222"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


@pytest.fixture
def uow(session):
    return UnitOfWork(session=session)


@pytest.fixture
def auth(uow):
    return AuthService(uow)


@pytest.fixture
def gerente(uow, auth):
    """Gerente já cadastrado e logado — o estado normal do app em operação."""
    funcionario = auth.criar_funcionario("Gerente", PIN_GERENTE, PerfilFuncionario.GERENTE)
    auth.login(PIN_GERENTE)
    return funcionario


@pytest.fixture
def atendente(uow, auth, gerente):
    return auth.criar_funcionario("Atendente", PIN_ATENDENTE, PerfilFuncionario.ATENDENTE)


@pytest.fixture
def mesa(uow):
    return uow.mesas.salvar(Mesa(numero=1))


@pytest.fixture
def categoria(uow):
    return uow.categorias.salvar(Categoria(nome="Lanches"))


@pytest.fixture
def produto(uow, categoria):
    return uow.produtos.salvar(
        Produto(nome="X-Burger", preco=Decimal("10.00"), categoria_id=categoria.id)
    )


@pytest.fixture
def caixa_aberto(uow):
    return uow.caixas.salvar(
        Caixa(valor_abertura=Decimal("100.00"), aberto_em=datetime(2026, 8, 20, 8, 0))
    )
