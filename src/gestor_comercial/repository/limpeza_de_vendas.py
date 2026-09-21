"""Tira de um banco todo o movimento de venda e deixa o cadastro como estava.

Existe para a hora de entregar o programa. O Vitor testa na tela (abre caixa,
lança comanda, recebe, fecha), e o banco que vai para o food truck tem que
nascer com o cardápio e sem nenhuma daquelas vendas — senão o pai dele abre o
programa com um caixa aberto e um faturamento que não aconteceu. O build já
RECUSA uma semente assim (`repository/preparo_da_semente.py`), de propósito sem
apagar nada; este módulo é a outra metade: a decisão de apagar, tomada por quem
roda `tools/limpar_vendas.py`.

## O que sai

As tabelas de `TABELAS_DE_MOVIMENTO` — a MESMA lista que a semente recusa, para
as duas pontas não divergirem —, apagadas das folhas para a raiz (pagamento
antes da comanda, comanda antes do caixa), com as chaves estrangeiras ligadas:
se um dia uma tabela de cadastro passar a apontar para uma venda, o `DELETE`
falha e a transação inteira volta, em vez de deixar referência quebrada.

E dois valores que só existem por causa dessas linhas: o saldo devedor de
consumo interno de cada funcionário, e mesa marcada como ocupada.

## O que fica

Cardápio (categorias, subcategorias, produtos, combos e as fotos em disco),
mesas, funcionários, logins, as senhas da loja, impressoras e preferências. Não
existe cadastro de cliente no programa.

## Contadores

Nenhuma tabela do schema usa `AUTOINCREMENT`: o id de uma chave `INTEGER
PRIMARY KEY` é o maior existente + 1, então tabela vazia volta a numerar do 1 —
a primeira comanda real é a nº 1, o primeiro caixa é o nº 1. Se uma migration
futura ligar `AUTOINCREMENT`, a linha da tabela em `sqlite_sequence` sai junto
e o efeito é o mesmo. O "1º Fechamento do dia" é contado dos caixas fechados no
dia (`CaixaService.fechar`) e zera com eles.

## Programa aberto

Apagar vendas por baixo do programa aberto deixaria a tela mostrando um caixa
que não existe mais, e a próxima gravação dele bateria numa chave estrangeira.
O teste é o próprio SQLite: sair do modo WAL exige que nenhuma outra conexão
esteja aberta. Se não sair, a limpeza é recusada antes de apagar qualquer coisa.

## Cópia antes

Antes de apagar, uma cópia consolidada (a API de backup lê o `-wal` junto) vai
para o lado do banco, com data e hora no nome. Se a limpeza pegou o banco
errado, é só renomear a cópia de volta.

Só `sqlite3`, como o preparo da semente: roda sem o programa, sem SQLAlchemy.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gestor_comercial.repository.preparo_da_semente import TABELAS_DE_MOVIMENTO


class LimpezaRecusada(Exception):
    """O banco não pode ser limpo agora; a mensagem diz por quê. Nada foi apagado."""


@dataclass(frozen=True, slots=True)
class RelatorioDaLimpeza:
    banco: Path
    copia_de_seguranca: Path
    apagadas: dict[str, int]
    funcionarios_com_saldo_zerado: int
    mesas_liberadas: int


def contar_movimento(banco: Path) -> dict[str, int]:
    """Linhas de venda por tabela, sem alterar nada (conexão somente leitura)."""
    if not banco.is_file():
        raise LimpezaRecusada(f"Banco não encontrado: {banco}")
    with closing(sqlite3.connect(f"{banco.resolve().as_uri()}?mode=ro", uri=True)) as conexao:
        existentes = _tabelas(conexao)
        return {
            tabela: conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]
            for tabela in TABELAS_DE_MOVIMENTO
            if tabela in existentes
        }


def limpar_vendas(banco: Path, *, agora: datetime | None = None) -> RelatorioDaLimpeza:
    """Apaga o movimento de venda de `banco`, depois de guardar uma cópia ao lado."""
    contar_movimento(banco)  # banco inexistente é recusado antes de qualquer escrita
    carimbo = (agora or datetime.now()).strftime("%Y%m%d-%H%M%S")
    copia = banco.with_name(f"{banco.name}.antes-da-limpeza-{carimbo}")

    with closing(sqlite3.connect(banco, isolation_level=None, timeout=1)) as conexao:
        estava_em_wal = _exigir_uso_exclusivo(conexao)
        try:
            with closing(sqlite3.connect(copia)) as destino:
                conexao.backup(destino)

            conexao.execute("PRAGMA foreign_keys=ON")
            conexao.execute("BEGIN IMMEDIATE")
            try:
                existentes = _tabelas(conexao)
                apagadas = {}
                for tabela in reversed(TABELAS_DE_MOVIMENTO):
                    if tabela in existentes:
                        apagadas[tabela] = conexao.execute(f'DELETE FROM "{tabela}"').rowcount
                if "sqlite_sequence" in existentes:
                    marcas = ", ".join("?" for _ in TABELAS_DE_MOVIMENTO)
                    conexao.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({marcas})", TABELAS_DE_MOVIMENTO)
                zerados = conexao.execute(
                    "UPDATE funcionarios SET saldo_devedor = 0 WHERE saldo_devedor <> 0"
                ).rowcount
                liberadas = conexao.execute("UPDATE mesas SET status = 'LIVRE' WHERE status <> 'LIVRE'").rowcount
                orfaos = conexao.execute("PRAGMA foreign_key_check").fetchall()
                if orfaos:
                    raise LimpezaRecusada(f"O banco ficaria com {len(orfaos)} referência(s) quebrada(s): {orfaos[:5]}")
                conexao.execute("COMMIT")
            except BaseException:
                conexao.execute("ROLLBACK")
                raise

            conexao.execute("VACUUM")
            integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
            if integridade != "ok":
                raise LimpezaRecusada(f"O banco ficou corrompido depois da limpeza: {integridade}. Cópia em {copia}")
        finally:
            if estava_em_wal:
                conexao.execute("PRAGMA journal_mode=WAL")

    return RelatorioDaLimpeza(
        banco=banco,
        copia_de_seguranca=copia,
        apagadas=apagadas,
        funcionarios_com_saldo_zerado=zerados,
        mesas_liberadas=liberadas,
    )


def _exigir_uso_exclusivo(conexao: sqlite3.Connection) -> bool:
    """Recusa o banco que outro processo tem aberto. Devolve se ele estava em WAL.

    Sair do WAL só acontece sem nenhuma outra conexão aberta — é o jeito do
    próprio SQLite dizer que o programa está fechado. O modo volta no fim.
    """
    modo = conexao.execute("PRAGMA journal_mode").fetchone()[0].lower()
    if modo != "wal":
        return False
    try:
        novo = conexao.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()
    except sqlite3.OperationalError:
        novo = modo
    if novo != "delete":
        raise LimpezaRecusada(
            "O banco está em uso — o programa parece estar aberto. Feche-o e rode de novo. Nada foi apagado."
        )
    return True


def _tabelas(conexao: sqlite3.Connection) -> set[str]:
    return {nome for (nome,) in conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
