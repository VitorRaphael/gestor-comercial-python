"""Pipeline de compressão de foto de produto (ver `services/imagem_service.py`):
redimensiona para caber em 120x120 e mantém o arquivo final dentro do teto de
tamanho (~25KB), sem depender de Pillow — só QImage."""

import pytest

QtGui = pytest.importorskip("PySide6.QtGui")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gestor_comercial.services import imagem_service  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _app():
    # QImage.save(..., "JPG") em algumas plataformas precisa de QApplication
    # viva (plugins de imagem carregados via QGuiApplication) — testes de UI
    # do projeto já assumem isso (ver conftest.py), replicado aqui pra rodar
    # este arquivo isolado também.
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def imagem_grande_colorida(tmp_path):
    """PNG 800x600 com ruído (bloco a bloco) — sem ruído, JPEG de cor sólida
    comprime bem além da meta mesmo em 120x120, e o teste de teto de tamanho
    não exercitaria a lógica de redução de qualidade de verdade."""
    imagem = QImage(800, 600, QImage.Format.Format_RGB32)
    for y in range(0, 600, 10):
        for x in range(0, 800, 10):
            cor = QColor((x * 7) % 256, (y * 13) % 256, (x + y) % 256)
            for dy in range(10):
                for dx in range(10):
                    imagem.setPixelColor(x + dx, y + dy, cor)
    caminho = tmp_path / "original.png"
    assert imagem.save(str(caminho), "PNG")
    return str(caminho)


def test_processar_imagem_redimensiona_para_caber_em_120px(monkeypatch, tmp_path, imagem_grande_colorida):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)

    nome_arquivo = imagem_service.processar_imagem_produto(imagem_grande_colorida)

    caminho_salvo = tmp_path / nome_arquivo
    assert caminho_salvo.is_file()
    assert nome_arquivo.endswith(".jpg")

    resultado = QImage(str(caminho_salvo))
    assert not resultado.isNull()
    assert resultado.width() <= imagem_service.TAMANHO_MAXIMO_PX
    assert resultado.height() <= imagem_service.TAMANHO_MAXIMO_PX


def test_processar_imagem_respeita_teto_de_tamanho_reduzindo_qualidade(
    monkeypatch, tmp_path, imagem_grande_colorida
):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)

    nome_arquivo = imagem_service.processar_imagem_produto(imagem_grande_colorida)

    caminho_salvo = tmp_path / nome_arquivo
    # Mesmo sem bater exatamente na meta (a imagem sintética de ruído é um
    # caso difícil pra JPEG), o pipeline não pode devolver um arquivo gigante:
    # tolerância de 2x o teto cobre o "piso razoável" documentado no service.
    assert caminho_salvo.stat().st_size <= imagem_service.TAMANHO_MAXIMO_BYTES * 2


def test_processar_imagem_invalida_levanta_value_error(tmp_path):
    arquivo_invalido = tmp_path / "nao_e_imagem.txt"
    arquivo_invalido.write_text("isto não é uma imagem")

    with pytest.raises(ValueError):
        imagem_service.processar_imagem_produto(str(arquivo_invalido))


def test_resolver_caminho_thumbnail_sem_imagem_path_retorna_none():
    assert imagem_service.resolver_caminho_thumbnail(None) is None
    assert imagem_service.resolver_caminho_thumbnail("") is None


def test_resolver_caminho_thumbnail_arquivo_inexistente_retorna_none(monkeypatch, tmp_path):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    assert imagem_service.resolver_caminho_thumbnail("nao-existe.jpg") is None


def test_resolver_caminho_thumbnail_arquivo_existente(monkeypatch, tmp_path):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    arquivo = tmp_path / "existe.jpg"
    arquivo.write_bytes(b"conteudo")

    resolvido = imagem_service.resolver_caminho_thumbnail("existe.jpg")

    assert resolvido == arquivo


def test_remover_thumbnail_apaga_arquivo_existente(monkeypatch, tmp_path):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    arquivo = tmp_path / "para_apagar.jpg"
    arquivo.write_bytes(b"conteudo")

    imagem_service.remover_thumbnail("para_apagar.jpg")

    assert not arquivo.exists()


def test_remover_thumbnail_silenciosa_se_nao_existir(monkeypatch, tmp_path):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    # Não deve levantar exceção mesmo sem o arquivo existir.
    imagem_service.remover_thumbnail("nunca-existiu.jpg")
