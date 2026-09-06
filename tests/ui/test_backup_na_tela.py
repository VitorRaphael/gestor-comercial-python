"""O botão "Gerar cópia agora" da tela de Configurações.

A rotina de backup em si é coberta por `tests/integration/test_backup.py`. Aqui
o que se prova é o caminho da tela: o clique realmente grava o arquivo, e o
rótulo mostra onde ele foi parar — porque um botão de backup que parece ter
funcionado sem ter funcionado é pior do que não ter botão nenhum.

Roda em banco de ARQUIVO (fixture própria), não no banco de memória do resto da
suíte de UI: sem arquivo não há o que copiar.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from gestor_comercial.repository import backup
from gestor_comercial.repository.base import Base, get_engine
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView


@pytest.fixture
def auth_em_arquivo(tmp_path):
    caminho = tmp_path / "dados" / "gestor_comercial.db"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(caminho)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as sessao:
        yield AuthService(UnitOfWork(session=sessao))
    engine.dispose()


def test_botao_gera_a_copia_e_mostra_onde(qapp, auth_em_arquivo):
    tela = ConfiguracoesView(auth_em_arquivo)
    pasta = backup.pasta_backups(auth_em_arquivo.uow.session)
    assert list(pasta.glob("*.db")) == []

    tela._botao_backup.click()

    gravados = list(pasta.glob(f"{backup.PREFIXO_BACKUP}*.db"))
    assert len(gravados) == 1
    assert tela._valor_backup.text() == str(gravados[0])
    assert tela._label_erro.text() == ""


def test_falha_ao_gerar_a_copia_aparece_na_tela(qapp, auth_em_arquivo, monkeypatch):
    """Silêncio aqui faria o dono achar que tem backup quando não tem."""
    tela = ConfiguracoesView(auth_em_arquivo)

    def _estourar(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(backup, "fazer_backup", _estourar)

    tela._botao_backup.click()

    assert "disco cheio" in tela._label_erro.text()
    assert tela._valor_backup.text() == "—"


def test_banco_de_memoria_avisa_em_vez_de_fingir(qapp, auth):
    """Na suíte (e em qualquer banco sem arquivo) o botão não pode mentir."""
    tela = ConfiguracoesView(auth)

    tela._botao_backup.click()

    assert "não tem arquivo em disco" in tela._label_erro.text()
    assert tela._valor_backup.text() == "—"
