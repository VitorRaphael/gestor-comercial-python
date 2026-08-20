import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gestor_comercial.domain import *  # noqa: F401,F403 - registra os mappers
from gestor_comercial.repository.base import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session
