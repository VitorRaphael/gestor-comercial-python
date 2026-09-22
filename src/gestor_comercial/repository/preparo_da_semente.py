"""Monta, na máquina do Vitor, a semente que o `.exe` leva embutida.

Roda no build (`packaging/preparar_semente.py`, chamado pelo `app.spec`), nunca
no food truck. A outra ponta — copiar a semente para a pasta de dados no
primeiro boot — é `core/banco_semente.py`, e o leiaute da pasta mora lá.

## Por que não é um `copy` do `.db`

O banco de trabalho roda em `journal_mode=WAL` (§8). As últimas alterações não
estão no `gestor_comercial.db`: estão no `-wal` ao lado, até alguém fechar o
programa pelo caminho normal e o checkpoint empurrá-las para dentro. Medido no
dia em que este módulo nasceu: 400 KB de `-wal` pendente, com o programa
fechado. Copiar só o `.db` teria embutido um cardápio de algumas edições atrás,
sem erro nenhum. A cópia aqui usa a API de backup do SQLite, que lê o banco
como uma conexão lê — com o `-wal` aplicado —, a partir de uma conexão
**somente leitura**: o build não consegue alterar o banco do Vitor nem se
quiser.

## O que a semente recusa

A semente é cadastro, não movimento. Se o banco de origem tiver caixa, comanda,
pagamento ou qualquer outra linha de venda (um teste feito na tela antes do
build), o build para com a contagem de cada tabela. Apagar essas linhas aqui
seria decidir sozinho o destino de dados de venda; embuti-las seria entregar ao
pai do Vitor um caixa com vendas que não aconteceram — e, com um turno de teste
deixado aberto, um programa que já nasce com caixa aberto.

Também para se um produto apontar para uma foto que não está em disco: a
promessa do `.exe` é o cardápio com as fotos, e uma foto faltando aqui é uma
foto faltando lá. Fotos que nenhum produto usa (sobras de trocas de foto) ficam
de fora.

Qualquer recusa apaga a semente pela metade: um build seguinte não pode
empacotar o que sobrou de uma tentativa que falhou.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gestor_comercial.core.banco_semente import ARQUIVO_DO_BANCO_SEMENTE, PASTA_DAS_FOTOS_DA_SEMENTE
from gestor_comercial.core.caminhos import SUBPASTA_DAS_FOTOS

TABELAS_DE_MOVIMENTO = (
    "caixas",
    "comandas",
    "itens_comanda",
    "pagamentos",
    "consumo_sessao_assinaturas",
    "movimentos_caixa",
    "quitacoes_consumo",
    "fila_impressao_pendente",
)


class SementeRecusada(Exception):
    """O banco de origem não serve de semente; a mensagem diz por quê."""


@dataclass(frozen=True, slots=True)
class RelatorioDaSemente:
    banco: Path
    revisao: str
    bytes_do_banco: int
    categorias: int
    subcategorias: int
    produtos: int
    componentes_de_combo: int
    mesas: int
    fotos: int
    fotos_sem_produto_ignoradas: int


def preparar_semente(
    banco_de_origem: Path,
    destino: Path,
    *,
    migrar: Callable[[Path], None] | None = None,
) -> RelatorioDaSemente:
    """Grava `destino/banco_seed.db` e `destino/thumbnails/` a partir do banco de trabalho.

    `migrar` recebe o caminho da CÓPIA e a leva até a última migration — quem
    injeta é o script de build, que é quem conhece o Alembic. Assim a semente
    sai na mesma revisão do código que vai junto com ela.
    """
    if not banco_de_origem.is_file():
        raise SementeRecusada(f"Banco de origem não encontrado: {banco_de_origem}")

    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    try:
        banco = destino / ARQUIVO_DO_BANCO_SEMENTE
        _copiar_consolidado(banco_de_origem, banco)
        if migrar is not None:
            migrar(banco)
        _compactar_e_conferir(banco)

        with closing(sqlite3.connect(banco)) as conexao:
            _exigir_sem_movimento(conexao)
            fotos = _fotos_referenciadas(conexao)
            contagens = _contagens(conexao)
            revisao = conexao.execute("SELECT version_num FROM alembic_version").fetchone()[0]

        copiadas, ignoradas = _copiar_fotos(
            fotos, banco_de_origem.parent / SUBPASTA_DAS_FOTOS, destino / PASTA_DAS_FOTOS_DA_SEMENTE
        )
        return RelatorioDaSemente(
            banco=banco,
            revisao=revisao,
            bytes_do_banco=banco.stat().st_size,
            fotos=copiadas,
            fotos_sem_produto_ignoradas=ignoradas,
            **contagens,
        )
    except BaseException:
        shutil.rmtree(destino, ignore_errors=True)
        raise


def _copiar_consolidado(origem: Path, destino: Path) -> None:
    with closing(sqlite3.connect(f"{origem.resolve().as_uri()}?mode=ro", uri=True)) as leitura:
        with closing(sqlite3.connect(destino)) as escrita:
            leitura.backup(escrita)


def _compactar_e_conferir(banco: Path) -> None:
    """Deixa a semente num arquivo só e confere que ela está íntegra.

    `journal_mode=DELETE` porque a semente viaja sozinha, sem `-wal` ao lado — o
    boot religa o WAL na primeira conexão (`repository/base.py`). O `VACUUM`
    devolve as páginas livres que as exclusões do cardápio deixaram.
    """
    with closing(sqlite3.connect(banco, isolation_level=None)) as conexao:
        conexao.execute("PRAGMA journal_mode=DELETE")
        conexao.execute("VACUUM")
        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
        if integridade != "ok":
            raise SementeRecusada(f"O banco de origem está corrompido: {integridade}")
        orfaos = conexao.execute("PRAGMA foreign_key_check").fetchall()
        if orfaos:
            raise SementeRecusada(f"O banco de origem tem {len(orfaos)} referência(s) quebrada(s): {orfaos[:5]}")


def _tabelas(conexao: sqlite3.Connection) -> set[str]:
    return {nome for (nome,) in conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _exigir_sem_movimento(conexao: sqlite3.Connection) -> None:
    existentes = _tabelas(conexao)
    com_linhas = {}
    for tabela in TABELAS_DE_MOVIMENTO:
        if tabela in existentes:
            quantidade = conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]
            if quantidade:
                com_linhas[tabela] = quantidade
    if com_linhas:
        detalhe = ", ".join(f"{tabela}: {quantidade}" for tabela, quantidade in com_linhas.items())
        raise SementeRecusada(
            "O banco de origem tem movimento de venda, e a semente é só cadastro "
            f"({detalhe}). Nada foi apagado do banco de origem."
        )


def _fotos_referenciadas(conexao: sqlite3.Connection) -> list[str]:
    nomes = sorted(
        {
            nome
            for (nome,) in conexao.execute(
                "SELECT imagem_path FROM produtos WHERE imagem_path IS NOT NULL AND imagem_path <> ''"
            )
        }
    )
    estranhos = [nome for nome in nomes if Path(nome).name != nome]
    if estranhos:
        raise SementeRecusada(f"Produto com caminho de foto fora do padrão (esperado só o nome): {estranhos[:5]}")
    return nomes


def _contagens(conexao: sqlite3.Connection) -> dict[str, int]:
    def contar(sql: str) -> int:
        return conexao.execute(sql).fetchone()[0]

    return {
        "categorias": contar("SELECT COUNT(*) FROM categorias WHERE arquivado = 0"),
        "subcategorias": contar("SELECT COUNT(*) FROM subcategorias"),
        "produtos": contar("SELECT COUNT(*) FROM produtos WHERE arquivado = 0"),
        "componentes_de_combo": contar("SELECT COUNT(*) FROM combo_itens"),
        "mesas": contar("SELECT COUNT(*) FROM mesas"),
    }


def _copiar_fotos(nomes: list[str], origem: Path, destino: Path) -> tuple[int, int]:
    faltando = [nome for nome in nomes if not (origem / nome).is_file()]
    if faltando:
        raise SementeRecusada(
            f"{len(faltando)} foto(s) de produto não estão em {origem}: {', '.join(faltando[:5])}"
        )
    destino.mkdir(parents=True, exist_ok=True)
    for nome in nomes:
        shutil.copyfile(origem / nome, destino / nome)
    em_disco = {caminho.name for caminho in origem.iterdir() if caminho.is_file()} if origem.is_dir() else set()
    return len(nomes), len(em_disco - set(nomes))
