"""Item 5 do TODO (Fase 5): 'checar integridade do SQLite' após queda de energia.

Simula o cenário derrubando um processo real com `SIGKILL`/`TerminateProcess`
no meio de uma escrita — o mais perto que dá de uma queda de energia sem
literalmente desligar a máquina. O SQLite guarda o estado anterior num journal
enquanto a transação não é commitada; ao reabrir o arquivo numa conexão nova,
ele detecta o journal "quente" e desfaz sozinho a escrita incompleta. É essa
recuperação automática que estes testes provam, não alguma lógica nossa.

**O que o app precisa fazer para isso continuar valendo:** não commitar cedo
demais (ver `UnitOfWork.commit`) e **não baixar o `synchronous`**. Desde a
Fase 2 da Remasterização o `journal_mode` é `WAL` e não mais o `delete` padrão
(§8) — a recuperação é a mesma, agora a partir do arquivo `-wal`, e estes dois
testes rodam sob WAL justamente para provar isso. O que **não** pode mudar é o
`synchronous`: todo guia de WAL sugere baixá-lo para `NORMAL`, e `NORMAL`
protege contra o app morrer mas **não** contra a energia cair no meio do
commit — que é exatamente o cenário destes testes e o do food truck. Ver
`repository/base.py`.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

_RAIZ_SRC = str(Path(__file__).resolve().parents[2] / "src")

# Escreve uma Mesa e trava antes do commit — a "queda de energia" acontece
# com a escrita só no journal, nunca efetivada.
_SCRIPT_SEM_COMMIT = """
import sys
sys.path.insert(0, {raiz_src!r})
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from gestor_comercial.domain import *  # noqa: F401,F403 - registra os mappers
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.repository.base import Base, get_engine

engine = get_engine(Path({db_path!r}))
Base.metadata.create_all(engine)
session = sessionmaker(bind=engine)()
session.add(Mesa(numero=99))
session.flush()  # escreve no arquivo/journal, mas não commita
print("PRONTO", flush=True)
import time
time.sleep(30)
"""

# Mesmo fluxo, mas commita antes de travar — a escrita já é durável e deve
# sobreviver à queda.
_SCRIPT_COM_COMMIT = _SCRIPT_SEM_COMMIT.replace(
    "session.flush()  # escreve no arquivo/journal, mas não commita",
    "session.commit()",
)


def _matar_processo_no_meio_da_escrita(db_path: Path, script: str) -> None:
    codigo = script.format(raiz_src=_RAIZ_SRC, db_path=str(db_path))
    processo = subprocess.Popen(
        [sys.executable, "-c", codigo],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        linha = processo.stdout.readline()
        assert linha.strip() == "PRONTO", f"processo filho não chegou a escrever: {linha!r}"
    finally:
        # kill() manda TerminateProcess no Windows: sem handler, sem
        # cleanup, sem flush de aplicação — o processo simplesmente para de
        # existir. É a aproximação mais realista de queda de energia que dá
        # pra fazer sem desligar a máquina de verdade.
        processo.kill()
        processo.wait(timeout=10)


def _abrir_com_retentativa(db_path: Path) -> sqlite3.Connection:
    """Reabre o banco depois da queda, esperando o SO soltar o handle do morto.

    A retentativa precisa envolver uma **leitura de verdade**, e não só o
    `connect()`: o `sqlite3.connect` é preguiçoso e não toca no arquivo, então
    ele passa mesmo com o Windows ainda segurando o handle do processo
    derrubado — e o erro reaparece no primeiro `execute`, como
    `disk I/O error`, fora do laço. Com a suíte grande (e a máquina ocupada), o
    SO demora mais para soltar e o teste piscava vermelho por causa do
    mecanismo da retentativa, não do SQLite.
    """
    ultimo_erro = None
    for _ in range(20):
        conexao = sqlite3.connect(str(db_path))
        try:
            conexao.execute("SELECT 1").fetchone()
            return conexao
        except sqlite3.OperationalError as erro:
            ultimo_erro = erro
            conexao.close()
            time.sleep(0.1)
    raise ultimo_erro


def test_escrita_sem_commit_e_desfeita_apos_queda(tmp_path):
    db_path = tmp_path / "queda_sem_commit.db"

    _matar_processo_no_meio_da_escrita(db_path, _SCRIPT_SEM_COMMIT)

    conexao = _abrir_com_retentativa(db_path)
    try:
        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
        assert integridade == "ok"

        total = conexao.execute("SELECT COUNT(*) FROM mesas WHERE numero = 99").fetchone()[0]
        assert total == 0, "escrita sem commit sobreviveu à queda — não devia"
    finally:
        conexao.close()


def test_escrita_com_commit_sobrevive_a_queda(tmp_path):
    db_path = tmp_path / "queda_com_commit.db"

    _matar_processo_no_meio_da_escrita(db_path, _SCRIPT_COM_COMMIT)

    conexao = _abrir_com_retentativa(db_path)
    try:
        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
        assert integridade == "ok"

        total = conexao.execute("SELECT COUNT(*) FROM mesas WHERE numero = 99").fetchone()[0]
        assert total == 1, "escrita commitada se perdeu na queda"
    finally:
        conexao.close()
