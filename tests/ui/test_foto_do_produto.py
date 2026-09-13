"""A foto do produto na tela: do seletor de arquivos à linha do Cardápio.

O relato (2026-09-13), com captura do bloco "Sucos e Vitaminas": as fotos
saíam cada uma de um tamanho, e a Limonada Suíça e o SucoAcerola eram pintados
POR CIMA do próprio nome. Medido no banco real, 18 das 35 miniaturas em disco
não eram quadradas (120x67, 67x120, 93x120...) — e o cache só as ESCALAVA
(`KeepAspectRatioByExpanding`), sem cortar. A 36px, a 120x67 virava 64x36, e os
28px de sobra caíam no começo do nome.

Junto, a porta de entrada: um `.avif` chegava ao leitor e voltava como
QMessageBox com "Não foi possível abrir 'C:/...' como imagem.".

As travas deste arquivo, uma por altura:

1. o cache devolve o lado EXATO, para foto deitada, em pé e ilegível;
2. a linha do Cardápio não deixa a foto sair da caixa — nem com o cache
   consertado, nem se um dia ele voltar a devolver pixmap maior;
3. o cadastro recusa formato fora da lista numa linha discreta, sem modal, sem
   tocar no que já foi digitado e sem perder a foto que já estava.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

import gestor_comercial.ui.views.cardapio_view as modulo_da_tela
import gestor_comercial.ui.widgets.cardapio_cartoes as modulo_dos_cartoes
from gestor_comercial.services import imagem_service
from gestor_comercial.services.imagem_service import FILTRO_DO_SELETOR, MENSAGEM_FORMATO_INVALIDO
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import thumbnail_cache
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    PAPEL_LINHA,
    DelegadoProdutos,
    FotoProduto,
    ItemDaLista,
    TipoDeItem,
)
from gestor_comercial.ui.widgets.thumbnail_cache import FORMATO_CARTAO, FORMATO_CIRCULO, obter_pixmap

MAGENTA = QColor(255, 0, 255)


@pytest.fixture(autouse=True)
def pasta_de_fotos(qapp, monkeypatch, tmp_path):
    """Miniaturas numa pasta do teste, e o cache zerado nas duas pontas."""
    pasta = tmp_path / "thumbnails"
    pasta.mkdir()
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: pasta)

    def _zerar() -> None:
        thumbnail_cache.limpar()
        thumbnail_cache._tema_do_cache = None

    _zerar()
    try:
        yield pasta
    finally:
        ThemeController.instancia().alternar_para(False)
        _zerar()


def _miniatura_em_disco(pasta, nome: str, largura: int, altura: int, cor: QColor = MAGENTA) -> str:
    """Uma miniatura como as ANTIGAS do banco real: JPEG com a proporção da foto."""
    imagem = QImage(largura, altura, QImage.Format.Format_RGB32)
    imagem.fill(cor)
    assert imagem.save(str(pasta / nome), "JPG", 90)
    return nome


def _eh_magenta(cor: QColor) -> bool:
    return cor.alpha() > 0 and cor.red() > 180 and cor.green() < 90 and cor.blue() > 180


# ---------------------------------------------------------------------------
# 1. O cache: lado exato
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("largura", "altura"),
    # As proporções que estavam em disco no banco real.
    [(120, 67), (67, 120), (93, 120), (120, 62), (120, 120)],
)
@pytest.mark.parametrize("formato", [FORMATO_CARTAO, FORMATO_CIRCULO])
@pytest.mark.parametrize("lado", [28, 32, 36, 40, 80])
def test_a_miniatura_antiga_em_disco_sai_com_o_lado_exato(pasta_de_fotos, largura, altura, formato, lado):
    """Os cinco lados que o app pede (ranking, comanda, Cardápio, lançamento e
    prévia do cadastro), nos dois recortes. Conserta as miniaturas que JÁ estão
    em disco sem regravar nenhuma."""
    nome = _miniatura_em_disco(pasta_de_fotos, "antiga.jpg", largura, altura)

    pixmap = obter_pixmap(nome, lado, "Limonada Suíça", formato=formato)

    assert (pixmap.width(), pixmap.height()) == (lado, lado)


def test_a_foto_em_cartao_tem_cantos_arredondados_e_o_centro_e_a_foto(pasta_de_fotos):
    """O canto do quadrado fica transparente (o raio de 8px), e o miolo é a
    foto — a prova de que o cartão não virou placeholder por engano."""
    nome = _miniatura_em_disco(pasta_de_fotos, "suco.jpg", 120, 67)

    imagem = obter_pixmap(nome, 36, "Suco de Abacaxi").toImage()

    assert imagem.pixelColor(0, 0).alpha() == 0, "o canto da foto saiu quadrado"
    assert _eh_magenta(imagem.pixelColor(18, 18)), imagem.pixelColor(18, 18).name()


def test_foto_ilegivel_em_disco_cai_no_placeholder_sem_estourar(pasta_de_fotos):
    (pasta_de_fotos / "corrompida.jpg").write_bytes(b"isto nao e um jpeg")

    com_arquivo_ruim = obter_pixmap("corrompida.jpg", 36, "SucoAcerola").toImage()
    thumbnail_cache.limpar()
    sem_foto = obter_pixmap(None, 36, "SucoAcerola").toImage()

    assert com_arquivo_ruim == sem_foto


def test_o_placeholder_tem_a_mesma_silhueta_da_foto(pasta_de_fotos):
    """Com e sem foto na mesma lista: o canto transparente e a borda caem nos
    mesmos pixels, senão a coluna de miniaturas sai serrilhada."""
    nome = _miniatura_em_disco(pasta_de_fotos, "foto.jpg", 120, 120)

    foto = obter_pixmap(nome, 36, "Suco de Laranja").toImage()
    placeholder = obter_pixmap(None, 36, "Suco de Laranja").toImage()

    for x, y in ((0, 0), (1, 1), (2, 2), (35, 0), (0, 35), (35, 35)):
        assert foto.pixelColor(x, y).alpha() == placeholder.pixelColor(x, y).alpha(), (x, y)


# ---------------------------------------------------------------------------
# 2. A linha do Cardápio: a foto não sai da caixa
# ---------------------------------------------------------------------------


def _pintar_linha(imagem_path: str | None, largura: int = 760) -> tuple[QImage, QRect]:
    produto = FotoProduto(
        produto_id=1,
        nome="Limonada Suíça",
        preco_texto="R$ 12,00",
        custo_texto="R$ 4,00",
        margem=66.0,
        ativo=True,
        selos=(),
        imagem_path=imagem_path,
        busca="limonada suica",
    )
    modelo = QStandardItemModel()
    item = QStandardItem()
    item.setData(ItemDaLista(TipoDeItem.PRODUTO, produto=produto, abre=True, fecha=True), PAPEL_LINHA)
    modelo.appendRow(item)

    delegado = DelegadoProdutos()
    linha = QRect(0, 0, largura, DelegadoProdutos.ALTURA_PRODUTO_PX)
    opcao = QStyleOptionViewItem()
    opcao.rect = linha
    opcao.font = QFont()
    opcao.state = QStyle.StateFlag.State_Enabled

    imagem = QImage(linha.size(), QImage.Format.Format_ARGB32)
    imagem.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagem)
    delegado.paint(pintor, opcao, modelo.index(0, 0))
    pintor.end()
    return imagem, delegado.colunas(linha, opcao.font).miniatura.toRect()


def _colunas_com_magenta(imagem: QImage) -> set[int]:
    return {
        x for x in range(imagem.width()) for y in range(imagem.height()) if _eh_magenta(imagem.pixelColor(x, y))
    }


def _conferir_que_a_foto_ficou_na_caixa(imagem: QImage, caixa: QRect) -> None:
    colunas = _colunas_com_magenta(imagem)
    # Duas asserções: sem a primeira, um `paint` que estourasse (o
    # `nao_deixa_escapar` engole) passaria verde sem ter pintado foto nenhuma.
    assert colunas, "a foto não foi pintada na linha"
    fora = sorted(x for x in colunas if x < caixa.left() or x > caixa.right())
    assert not fora, f"a foto saiu da caixa ({caixa.left()}..{caixa.right()}) até x={max(fora)}, em cima do nome"


def test_a_foto_deitada_nao_invade_o_nome_do_produto(pasta_de_fotos):
    """A captura do relato, em pixel: miniatura 120x67 numa linha do Cardápio."""
    nome = _miniatura_em_disco(pasta_de_fotos, "limonada.jpg", 120, 67)

    imagem, caixa = _pintar_linha(nome)

    _conferir_que_a_foto_ficou_na_caixa(imagem, caixa)


def test_a_linha_corta_na_caixa_mesmo_se_o_pixmap_vier_maior(monkeypatch):
    """A segunda trava, sozinha: o cache é trocado por um que devolve o pixmap
    do defeito antigo (64x36), e a linha tem que cortar do mesmo jeito."""
    largo = QPixmap(64, 36)
    largo.fill(MAGENTA)
    monkeypatch.setattr(modulo_dos_cartoes, "obter_pixmap", lambda *args, **kwargs: largo)

    imagem, caixa = _pintar_linha("qualquer.jpg")

    _conferir_que_a_foto_ficou_na_caixa(imagem, caixa)


def test_o_nome_comeca_no_mesmo_x_com_e_sem_foto(pasta_de_fotos):
    """O alinhamento vertical do nome não depende de haver foto ao lado."""
    delegado = DelegadoProdutos()
    linha = QRect(0, 0, 760, DelegadoProdutos.ALTURA_PRODUTO_PX)

    colunas = delegado.colunas(linha, QFont())

    assert colunas.miniatura.width() == colunas.miniatura.height() == DelegadoProdutos.LADO_MINIATURA_PX
    assert colunas.nome.left() >= colunas.miniatura.right() + 12.0


# ---------------------------------------------------------------------------
# 3. O cadastro: recusa discreta, nada digitado se perde
# ---------------------------------------------------------------------------


@pytest.fixture
def cadastro(qapp, monkeypatch):
    def _proibido(*_args, **_kwargs):
        raise AssertionError("a foto recusada abriu um QMessageBox por cima do cadastro")

    monkeypatch.setattr(modulo_da_tela.QMessageBox, "warning", _proibido)
    dialogo = modulo_da_tela._ProdutoDialog(
        "Editar produto",
        [],
        nome_inicial="Limonada Suíça",
        preco_inicial=Decimal("12.00"),
        custo_inicial=Decimal("4.00"),
        descricao_inicial="Gelada",
        imagem_path_inicial="foto-que-ja-estava.jpg",
    )
    yield dialogo
    dialogo.deleteLater()


def _seletor_devolve(monkeypatch, caminho: str) -> list[str]:
    filtros: list[str] = []

    def _falso(_pai, _titulo, _pasta, filtro):
        filtros.append(filtro)
        return caminho, filtro

    monkeypatch.setattr(modulo_da_tela.QFileDialog, "getOpenFileName", _falso)
    return filtros


def _campos(dialogo) -> tuple[str, str, str, str]:
    return (
        dialogo._campo_nome.text(),
        dialogo._campo_preco.text(),
        dialogo._campo_custo.text(),
        dialogo._campo_descricao.text(),
    )


def test_o_seletor_so_oferece_os_formatos_homologados(monkeypatch, cadastro):
    filtros = _seletor_devolve(monkeypatch, "")

    cadastro._escolher_imagem()

    assert filtros == [FILTRO_DO_SELETOR]


def test_avif_e_recusado_numa_linha_sem_perder_o_que_foi_digitado(monkeypatch, tmp_path, cadastro):
    avif = tmp_path / "suco.avif"
    avif.write_bytes(b"\x00\x00\x00\x1cftypavif" + b"\x00" * 64)
    _seletor_devolve(monkeypatch, str(avif))
    antes = _campos(cadastro)

    cadastro._escolher_imagem()

    assert not cadastro._erro_imagem.isHidden(), "a recusa não apareceu na tela"
    assert cadastro._erro_imagem.text() == MENSAGEM_FORMATO_INVALIDO
    assert _campos(cadastro) == antes
    assert cadastro._imagem_path_processada == "foto-que-ja-estava.jpg", "a recusa jogou fora a foto que estava"
    assert cadastro._imagem_path_para_remover is None, "a recusa marcou a foto que estava para ser apagada"


def test_escolher_uma_foto_valida_depois_apaga_o_aviso(monkeypatch, tmp_path, pasta_de_fotos, cadastro):
    avif = tmp_path / "suco.avif"
    avif.write_bytes(b"\x00")
    _seletor_devolve(monkeypatch, str(avif))
    cadastro._escolher_imagem()
    assert not cadastro._erro_imagem.isHidden()

    png = tmp_path / "suco.png"
    foto = QImage(300, 200, QImage.Format.Format_RGB32)
    foto.fill(MAGENTA)
    assert foto.save(str(png), "PNG")
    _seletor_devolve(monkeypatch, str(png))
    cadastro._escolher_imagem()

    assert cadastro._erro_imagem.isHidden()
    assert (pasta_de_fotos / cadastro._imagem_path_processada).is_file()
    assert cadastro._imagem_path_para_remover == "foto-que-ja-estava.jpg"
