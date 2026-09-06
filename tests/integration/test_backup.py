"""Backup do banco e consolidação do WAL — `REMASTERIZACAO-V1.md` §8 (2026-09-06).

Ligar `journal_mode=WAL` trouxe a concorrência entre leitura e escrita que o
App Mobile do Atendente vai exigir, e de quebra 3x em cada lançamento de item.
O preço é que **o banco deixa de ser um arquivo só**: as transações recentes
ficam num `-wal` ao lado. Para um dono não-técnico com um pendrive, isso é uma
armadilha silenciosa — copiar o `.db` com o app aberto leva um banco sem as
últimas vendas, e ninguém descobre até precisar do backup.

Estes testes travam a proteção contra isso. O mais importante de todos é
`test_backup_leva_a_venda_que_ainda_esta_no_wal`: é ele que prova que o
`VACUUM INTO` enxerga o que uma cópia de arquivo perderia.

Rodam em banco de ARQUIVO de verdade (`tmp_path`), não no banco de memória do
resto da suíte — WAL só existe quando existe arquivo.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from gestor_comercial.domain import *  # noqa: F401,F403 - registra os mappers
from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.enums import PerfilUsuario, StatusCaixa
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.repository import backup
from gestor_comercial.repository.base import Base, get_engine
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.loja_config_service import SENHA_MASTER_PADRAO


@pytest.fixture
def banco_em_arquivo(tmp_path):
    """Um banco SQLite de verdade, em disco — onde o WAL existe."""
    caminho = tmp_path / "dados" / "gestor_comercial.db"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(caminho)
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    with fabrica() as sessao:
        yield sessao
    engine.dispose()


def _arquivo_wal(sessao) -> Path:
    return Path(str(backup.caminho_do_banco(sessao)) + "-wal")


def _mesas_no_arquivo(caminho: Path) -> list[int]:
    """Lê um `.db` por fora, com o sqlite3 cru — como quem abriu o backup depois."""
    conexao = sqlite3.connect(str(caminho))
    try:
        return [linha[0] for linha in conexao.execute("SELECT numero FROM mesas ORDER BY numero")]
    finally:
        conexao.close()


# ----------------------------------------------------------------------
# Os PRAGMAs que sustentam tudo isto
# ----------------------------------------------------------------------


def test_banco_em_arquivo_nasce_em_wal_com_fk_ligada(banco_em_arquivo):
    assert banco_em_arquivo.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    assert banco_em_arquivo.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_synchronous_continua_full(banco_em_arquivo):
    """A armadilha do WAL: todo guia manda baixar `synchronous` para NORMAL.

    NORMAL protege contra o app morrer, mas **não** contra a energia cair no
    meio do commit — que é o cenário do food truck e o que
    `test_resiliencia_queda_energia.py` prova. 2 é FULL, o padrão do SQLite.
    """
    assert banco_em_arquivo.execute(text("PRAGMA synchronous")).scalar() == 2


# ----------------------------------------------------------------------
# VACUUM INTO
# ----------------------------------------------------------------------


def test_backup_leva_a_venda_que_ainda_esta_no_wal(banco_em_arquivo):
    """O motivo de o backup ser `VACUUM INTO` e não cópia de arquivo.

    O roteiro é o do balcão: o banco já vem de dias anteriores (consolidado no
    `.db`), e a venda de agora é commitada mas ainda não passou por checkpoint —
    está só no `-wal`. Copiar o `.db` nesse instante, que é o que o dono faria
    com o pendrive e o app aberto, traz o banco de ontem. O `VACUUM INTO` tem
    que trazer a venda de hoje junto.
    """
    banco_em_arquivo.add(Mesa(numero=1))  # o "banco de ontem"
    banco_em_arquivo.commit()
    backup.consolidar_wal(banco_em_arquivo)

    banco_em_arquivo.add(Mesa(numero=42))  # a venda de agora
    banco_em_arquivo.commit()
    assert _arquivo_wal(banco_em_arquivo).stat().st_size > 0, (
        "a venda já saiu do WAL sozinha — o teste não estaria provando nada"
    )

    copia_ingenua = Path(str(banco_em_arquivo.get_bind().url.database) + ".copia")
    copia_ingenua.write_bytes(backup.caminho_do_banco(banco_em_arquivo).read_bytes())
    destino = backup.fazer_backup(origem=banco_em_arquivo)

    assert _mesas_no_arquivo(copia_ingenua) == [1], (
        "a cópia crua do .db pegou a venda — o WAL não estava sendo exercitado"
    )
    assert _mesas_no_arquivo(destino) == [1, 42]


def test_backup_e_um_arquivo_unico_e_integro(banco_em_arquivo):
    """Sem `-wal` nem `-shm` do lado: é isso que torna o pendrive seguro."""
    banco_em_arquivo.add_all([Mesa(numero=n) for n in (1, 2, 3)])
    banco_em_arquivo.commit()

    destino = backup.fazer_backup(origem=banco_em_arquivo)

    assert destino.exists()
    assert not Path(str(destino) + "-wal").exists()
    assert not Path(str(destino) + "-shm").exists()
    conexao = sqlite3.connect(str(destino))
    try:
        assert conexao.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conexao.close()
    assert _mesas_no_arquivo(destino) == [1, 2, 3]


def test_backup_nunca_sobrescreve_backup(banco_em_arquivo, tmp_path):
    destino = tmp_path / "ja_existe.db"
    destino.write_bytes(b"backup anterior que nao pode sumir")

    with pytest.raises(Exception):
        backup.fazer_backup(destino=destino, origem=banco_em_arquivo)

    assert destino.read_bytes() == b"backup anterior que nao pode sumir"


def test_backup_vai_para_a_pasta_ao_lado_do_banco(banco_em_arquivo):
    destino = backup.fazer_backup(origem=banco_em_arquivo)

    assert destino.parent == backup.caminho_do_banco(banco_em_arquivo).parent / "backups"
    assert destino.name.startswith(backup.PREFIXO_BACKUP)


def test_banco_de_memoria_nao_escreve_backup_nenhum(uow):
    """A suíte roda em memória: nada aqui pode encostar na pasta de dados real."""
    assert backup.caminho_do_banco(uow.session) is None
    assert backup.pasta_backups(uow.session) is None
    assert backup.fazer_backup(origem=uow.session) is None
    assert backup.consolidar_wal(uow.session) is False
    assert backup.limpar_backups_antigos(origem=uow.session) == []


# ----------------------------------------------------------------------
# Checkpoint
# ----------------------------------------------------------------------


def test_consolidar_wal_esvazia_o_arquivo_auxiliar(banco_em_arquivo):
    """Depois disto, o `.db` sozinho já está completo — é o que roda ao fechar o app."""
    banco_em_arquivo.add(Mesa(numero=7))
    banco_em_arquivo.commit()
    assert _arquivo_wal(banco_em_arquivo).stat().st_size > 0

    assert backup.consolidar_wal(banco_em_arquivo) is True

    assert _arquivo_wal(banco_em_arquivo).stat().st_size == 0
    assert 7 in _mesas_no_arquivo(backup.caminho_do_banco(banco_em_arquivo))


# ----------------------------------------------------------------------
# Rotação
# ----------------------------------------------------------------------


def test_limpar_backups_guarda_os_mais_recentes(banco_em_arquivo):
    pasta = backup.pasta_backups(banco_em_arquivo)
    for dia in range(1, 6):
        (pasta / f"{backup.PREFIXO_BACKUP}2026090{dia}_120000.db").write_bytes(b"x")

    apagados = backup.limpar_backups_antigos(manter=2, origem=banco_em_arquivo)

    restantes = sorted(p.name for p in pasta.glob("*.db"))
    assert len(apagados) == 3
    assert restantes == [
        f"{backup.PREFIXO_BACKUP}20260904_120000.db",
        f"{backup.PREFIXO_BACKUP}20260905_120000.db",
    ]


def test_limpar_backups_nao_toca_em_arquivo_que_nao_e_dele(banco_em_arquivo):
    """Um `.db` que o Vitor guardou ali à mão não é lixo automático."""
    pasta = backup.pasta_backups(banco_em_arquivo)
    (pasta / f"{backup.PREFIXO_BACKUP}20260901_120000.db").write_bytes(b"x")
    (pasta / f"{backup.PREFIXO_BACKUP}20260902_120000.db").write_bytes(b"x")
    meu = pasta / "antes-de-mexer-no-cardapio.db"
    meu.write_bytes(b"guardado a mao")

    backup.limpar_backups_antigos(manter=1, origem=banco_em_arquivo)

    assert meu.exists()


# ----------------------------------------------------------------------
# O gancho no fechamento de caixa
# ----------------------------------------------------------------------


@pytest.fixture
def caixas_em_arquivo(banco_em_arquivo):
    """Serviços em cima do banco de arquivo, com gerente logado e caixa aberto."""
    uow = UnitOfWork(session=banco_em_arquivo)
    auth = AuthService(uow)
    gerente = auth.criar_usuario("Gerente", PerfilUsuario.GERENTE)
    auth.login_como(gerente.id, SENHA_MASTER_PADRAO)
    caixa = uow.caixas.salvar(
        Caixa(
            status=StatusCaixa.ABERTO,
            valor_abertura=Decimal("100.00"),
            aberto_em=datetime(2026, 9, 6, 17, 0),
            aberto_por_id=gerente.id,
        )
    )
    uow.commit()
    return CaixaService(uow, auth), caixa


def test_fechar_o_caixa_guarda_um_backup(caixas_em_arquivo, banco_em_arquivo):
    """O fechamento é o marco do dia: é dali que o histórico passa a valer."""
    caixas, caixa = caixas_em_arquivo
    pasta = backup.pasta_backups(banco_em_arquivo)
    assert list(pasta.glob("*.db")) == []

    caixas.fechar(caixa.id, Decimal("100.00"), Decimal("0.00"))

    gravados = list(pasta.glob(f"{backup.PREFIXO_BACKUP}*.db"))
    assert len(gravados) == 1
    conexao = sqlite3.connect(str(gravados[0]))
    try:
        fechados = conexao.execute(
            "SELECT COUNT(*) FROM caixas WHERE status = 'FECHADO'"
        ).fetchone()[0]
    finally:
        conexao.close()
    assert fechados == 1, "o backup saiu antes do fechamento entrar nele"


def test_backup_que_falha_nao_derruba_o_fechamento(caixas_em_arquivo, monkeypatch):
    """Disco cheio ou pendrive removido não pode desfazer uma gaveta já contada."""
    caixas, caixa = caixas_em_arquivo

    def _estourar(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(backup, "fazer_backup", _estourar)

    fechado = caixas.fechar(caixa.id, Decimal("100.00"), Decimal("0.00"))

    assert fechado.status is StatusCaixa.FECHADO
    assert fechado.numero_sequencial_dia == 1
