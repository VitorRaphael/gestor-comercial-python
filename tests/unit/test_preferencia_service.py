"""O tema escolhido sobrevive ao fechamento do programa — ver `PreferenciaService`.

O defeito relatado: Modo Claro escolhido em Configurações, programa fechado e
reaberto, e o tema de volta no Escuro. Não havia gravação nenhuma. Estes testes
ficam no service (sem Qt); a aplicação do tema no boot mora em
`tests/ui/test_tema_persistente.py`.
"""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import gestor_comercial.domain  # noqa: F401 - registra os mappers
from gestor_comercial.domain.preferencia import Preferencia
from gestor_comercial.repository.base import Base
from gestor_comercial.repository.preferencia_repository import TEMA
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.preferencia_service import PreferenciaService


def test_sem_escolha_gravada_nao_ha_tema(uow):
    """`None`, e não `False`: é o que deixa o boot distinguir "nunca escolheu"
    de "escolheu o escuro" — e cair no padrão só no primeiro caso."""
    assert PreferenciaService(uow).tema_claro_gravado() is None


def test_o_tema_gravado_e_lido_de_volta(uow):
    preferencias = PreferenciaService(uow)

    preferencias.gravar_tema(True)
    assert preferencias.tema_claro_gravado() is True

    preferencias.gravar_tema(False)
    assert preferencias.tema_claro_gravado() is False


def test_trocar_o_tema_regrava_a_mesma_linha(uow, session):
    preferencias = PreferenciaService(uow)

    for claro in (True, False, True, False):
        preferencias.gravar_tema(claro)

    linhas = session.scalar(
        select(func.count()).select_from(Preferencia).where(Preferencia.chave == TEMA)
    )
    assert linhas == 1


def test_o_tema_sobrevive_a_fechar_e_reabrir_o_banco(tmp_path):
    """O defeito, reproduzido do jeito que o Vitor o viu: grava numa conexão,
    fecha tudo, abre outra conexão com o mesmo arquivo — como o programa faz
    entre um dia e outro."""
    url = f"sqlite:///{tmp_path / 'gestor.db'}"
    motor = create_engine(url)
    Base.metadata.create_all(motor)
    with sessionmaker(bind=motor)() as sessao:
        PreferenciaService(UnitOfWork(session=sessao)).gravar_tema(True)
    motor.dispose()

    motor_reaberto = create_engine(url)
    with sessionmaker(bind=motor_reaberto)() as sessao:
        assert PreferenciaService(UnitOfWork(session=sessao)).tema_claro_gravado() is True
    motor_reaberto.dispose()


def test_valor_estranho_no_banco_cai_no_padrao(uow):
    """Só existe por edição manual do banco — e não pode derrubar o boot."""
    uow.preferencias.definir(TEMA, "concreto")
    uow.commit()

    assert PreferenciaService(uow).tema_claro_gravado() is None


def test_falha_ao_gravar_nao_estoura_nem_deixa_nada_pendente(uow, session, monkeypatch):
    """O tema já mudou na tela quando a gravação roda: um erro de disco vira
    registro no log, nunca exceção no clique — e a Session sai limpa, senão o
    próximo commit de qualquer outra tela gravaria a preferência pela metade."""

    def commit_que_falha() -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(uow, "commit", commit_que_falha)

    PreferenciaService(uow).gravar_tema(True)

    assert not session.new and not session.dirty
    monkeypatch.undo()
    assert PreferenciaService(uow).tema_claro_gravado() is None
