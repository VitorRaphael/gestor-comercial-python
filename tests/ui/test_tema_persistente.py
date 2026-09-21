"""O tema volta como foi deixado — `ThemeController.restaurar` e a gravação na troca.

O defeito: o `ThemeController` guardava o tema só em memória, e todo boot
começava no Escuro. Agora o boot lê a preferência ANTES de montar a janela
(`main.py`) e cada troca grava na hora. Os testes com controlador próprio não
tocam no singleton, que vive a suíte inteira: um armazém esquecido nele faria
os testes seguintes gravarem num banco que já foi fechado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import gestor_comercial.domain  # noqa: F401 - registra os mappers
from gestor_comercial import main as modulo_main
from gestor_comercial.repository.base import Base
from gestor_comercial.repository.preferencia_repository import TEMA
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.preferencia_service import PreferenciaService
from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.qss_app import construir_qss_app
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView


class _Armazem:
    """Armazém de mentira: devolve o que mandarem e anota cada gravação."""

    def __init__(self, gravado: bool | None) -> None:
        self.gravado = gravado
        self.gravacoes: list[bool] = []

    def tema_claro_gravado(self) -> bool | None:
        return self.gravado

    def gravar_tema(self, claro: bool) -> None:
        self.gravacoes.append(claro)


@pytest.fixture
def controlador(qapp):
    """Um `ThemeController` só deste teste — e o QSS do app devolvido ao do
    singleton no fim, porque `setStyleSheet` é global."""
    proprio = ThemeController()
    yield proprio
    qapp.setStyleSheet(construir_qss_app(ThemeController.instancia().tokens_atuais))


def test_o_boot_aplica_o_tema_gravado(qapp, controlador):
    controlador.aplicar_inicial()

    controlador.restaurar(_Armazem(gravado=True))

    assert controlador.claro
    assert controlador.tokens_atuais is tokens.TEMA_CLARO
    assert qapp.styleSheet() == construir_qss_app(tokens.TEMA_CLARO)


def test_o_boot_sem_escolha_gravada_fica_no_padrao(qapp, controlador):
    controlador.aplicar_inicial()

    controlador.restaurar(_Armazem(gravado=None))

    assert not controlador.claro
    assert qapp.styleSheet() == construir_qss_app(tokens.TEMA_ESCURO)


def test_restaurar_nao_grava_de_volta_nem_avisa_ninguem(controlador):
    """No boot nenhuma tela existe ainda: não há quem avisar, e regravar o que
    acabou de ser lido seria uma escrita em disco a cada abertura do programa."""
    armazem = _Armazem(gravado=True)
    avisos: list[dict] = []
    controlador.mudou.connect(avisos.append)

    controlador.restaurar(armazem)

    assert armazem.gravacoes == []
    assert avisos == []


def test_cada_troca_de_tema_grava_na_hora(controlador):
    armazem = _Armazem(gravado=None)
    controlador.restaurar(armazem)

    controlador.alternar_para(True)
    controlador.alternar_para(False)

    assert armazem.gravacoes == [True, False]


def test_escolher_o_tema_que_ja_esta_valendo_nao_grava(controlador):
    armazem = _Armazem(gravado=None)
    controlador.restaurar(armazem)

    controlador.alternar_para(False)

    assert armazem.gravacoes == []


def test_a_gravacao_vem_antes_do_aviso_as_telas(controlador):
    """Uma tela que estoure ao repintar não pode custar a preferência."""
    ordem: list[str] = []

    class _Anotador(_Armazem):
        def gravar_tema(self, claro: bool) -> None:
            ordem.append("gravou")

    controlador.restaurar(_Anotador(gravado=None))
    controlador.mudou.connect(lambda _tokens: ordem.append("avisou"))

    controlador.alternar_para(True)

    assert ordem == ["gravou", "avisou"]


def test_fechar_e_reabrir_o_app_volta_no_tema_escolhido(qapp, controlador, tmp_path):
    """O fluxo inteiro do defeito, com banco em arquivo e dois "boots": no
    primeiro o operador escolhe o claro; o segundo nasce com controlador e
    conexão novos — nada em memória atravessa de um para o outro."""
    url = f"sqlite:///{tmp_path / 'gestor.db'}"
    motor = create_engine(url)
    Base.metadata.create_all(motor)
    with sessionmaker(bind=motor)() as sessao:
        controlador.restaurar(PreferenciaService(UnitOfWork(session=sessao)))
        controlador.alternar_para(True)
    motor.dispose()

    segundo_boot = ThemeController()
    segundo_boot.aplicar_inicial()
    motor_reaberto = create_engine(url)
    with sessionmaker(bind=motor_reaberto)() as sessao:
        segundo_boot.restaurar(PreferenciaService(UnitOfWork(session=sessao)))
    motor_reaberto.dispose()

    assert segundo_boot.claro
    assert qapp.styleSheet() == construir_qss_app(tokens.TEMA_CLARO)


@pytest.fixture
def tema_gravando(qapp, uow):
    """O singleton com o armazém de verdade ligado, como `main.py` deixa —
    desligado de novo no fim, junto com o tema de volta ao escuro."""
    singleton = ThemeController.instancia()
    singleton.restaurar(PreferenciaService(uow))
    try:
        yield singleton
    finally:
        singleton._armazem = None
        singleton.alternar_para(False)


def test_o_botao_de_configuracoes_troca_e_grava(qapp, tema_gravando, auth, uow):
    """O caminho do operador: a pílula de Configurações não sabe que existe
    banco, e mesmo assim o clique fica gravado."""
    tela = ConfiguracoesView(auth)

    tela._botao_tema_claro.click()

    assert tema_gravando.claro
    assert uow.preferencias.obter(TEMA) == "claro"
    tela.deleteLater()


def test_o_boot_restaura_o_tema_antes_de_montar_a_janela():
    """A ordem é o que faz as telas nascerem na paleta certa: restaurar depois
    da `MainWindow` pintaria tudo no escuro e repoliria a janela inteira."""
    fonte = Path(modulo_main.__file__).read_text(encoding="utf-8")

    restaurar = fonte.index("ThemeController.instancia().restaurar(")
    janela = fonte.index("janela = MainWindow(")

    assert restaurar < janela
