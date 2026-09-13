"""Pipeline de compressão de foto de produto (ver `services/imagem_service.py`):
enquadra num quadrado exato de 120x120 (recorte central), mantém o arquivo final
dentro do teto de tamanho (~25KB) e recusa o que não é PNG/JPG/WEBP com uma
frase só — sem depender de Pillow, só QImage."""

import logging

import pytest

QtGui = pytest.importorskip("PySide6.QtGui")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gestor_comercial.core.resilience import NOME_LOGGER  # noqa: E402
from gestor_comercial.services import imagem_service  # noqa: E402
from gestor_comercial.services.imagem_service import MENSAGEM_FORMATO_INVALIDO  # noqa: E402

AZUL = QColor(20, 60, 230)
VERMELHO = QColor(230, 20, 20)


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


# ---------------------------------------------------------------------------
# Enquadramento: quadrado exato, do centro, sem fundo preto (2026-09-13)
# ---------------------------------------------------------------------------


def _faixas(largura: int, altura: int, caminho, formato: str = "PNG") -> str:
    """Quadrado AZUL no centro e VERMELHO no que sobra dos dois lados.

    É a foto que denuncia de onde o recorte saiu: se a miniatura tiver
    vermelho, ela pegou a sobra (ou foi achatada inteira, sem corte)."""
    imagem = QImage(largura, altura, QImage.Format.Format_RGB32)
    imagem.fill(VERMELHO)
    lado = min(largura, altura)
    pintor = QPainter(imagem)
    pintor.fillRect((largura - lado) // 2, (altura - lado) // 2, lado, lado, AZUL)
    pintor.end()
    assert imagem.save(str(caminho), formato)
    return str(caminho)


def _perto(cor: QColor, alvo: QColor, tolerancia: int = 40) -> bool:
    return all(
        abs(a - b) <= tolerancia
        for a, b in zip((cor.red(), cor.green(), cor.blue()), (alvo.red(), alvo.green(), alvo.blue()))
    )


@pytest.mark.parametrize(
    ("largura", "altura"),
    # As proporções que estavam no banco real: deitada 16:9, em pé 9:16, 3:2,
    # quase quadrada — e uma menor que a miniatura, que tem que crescer.
    [(1280, 720), (720, 1280), (900, 600), (117, 120), (50, 30)],
    ids=["deitada", "em_pe", "3x2", "quase_quadrada", "pequena"],
)
def test_a_miniatura_sai_quadrada_e_do_centro(monkeypatch, tmp_path, largura, altura):
    """O defeito da tela: a miniatura guardava a proporção da foto (120x67), e o
    quadrado reservado na linha não a continha. Agora ela é exatamente 120x120,
    e os quatro cantos são do quadrado central — nenhum pedaço da sobra."""
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    origem = _faixas(largura, altura, tmp_path / "origem.png")

    salvo = QImage(str(tmp_path / imagem_service.processar_imagem_produto(origem)))

    lado = imagem_service.TAMANHO_MAXIMO_PX
    assert (salvo.width(), salvo.height()) == (lado, lado)
    for x, y in ((2, 2), (lado - 3, 2), (2, lado - 3), (lado - 3, lado - 3)):
        cor = salvo.pixelColor(x, y)
        assert _perto(cor, AZUL), f"canto ({x},{y}) saiu {cor.name()}: o recorte pegou a sobra da foto"


def test_png_transparente_nao_vira_quadrado_preto(monkeypatch, tmp_path):
    """JPEG não tem alfa, e o Qt salva a cor que estava por baixo do
    transparente — (0, 0, 0) num PNG recortado. O copo de suco sem fundo
    virava um copo num quadrado preto."""
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    imagem = QImage(300, 300, QImage.Format.Format_ARGB32)
    imagem.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagem)
    pintor.fillRect(120, 120, 60, 60, QColor("orange"))
    pintor.end()
    origem = tmp_path / "copo.png"
    assert imagem.save(str(origem), "PNG")
    assert QImage(str(origem)).pixelColor(0, 0).getRgb() == (0, 0, 0, 0), "premissa: transparente é preto por baixo"

    salvo = QImage(str(tmp_path / imagem_service.processar_imagem_produto(str(origem))))

    assert _perto(salvo.pixelColor(2, 2), QColor("white"), tolerancia=12), salvo.pixelColor(2, 2).name()


@pytest.mark.parametrize("formato", ["PNG", "JPG", "WEBP"])
def test_os_tres_formatos_homologados_passam(monkeypatch, tmp_path, formato):
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    origem = _faixas(640, 480, tmp_path / f"foto.{formato.lower()}", formato)

    nome = imagem_service.processar_imagem_produto(origem)

    assert QImage(str(tmp_path / nome)).width() == imagem_service.TAMANHO_MAXIMO_PX


def test_a_extensao_e_conferida_sem_diferenciar_maiusculas(monkeypatch, tmp_path):
    """Câmera e WhatsApp gravam `FOTO.JPG` — o seletor do Windows mostra, então
    a conferência não pode recusar."""
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path)
    origem = _faixas(640, 480, tmp_path / "FOTO.JPG", "JPG")

    assert imagem_service.processar_imagem_produto(origem).endswith(".jpg")


@pytest.mark.parametrize("extensao", [".avif", ".heic", ".bmp", ".svg"])
def test_extensao_fora_da_lista_e_recusada_mesmo_se_o_qt_souber_ler(monkeypatch, tmp_path, extensao):
    """O filtro do seletor não é barreira: no Windows dá para digitar `*.*` ou
    colar um caminho. A conferência é do service. O `.bmp` aqui é um BMP de
    verdade, que o Qt lê — e é recusado mesmo assim, porque a lista é a lista."""
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path / "thumbs")
    (tmp_path / "thumbs").mkdir()
    origem = tmp_path / f"foto{extensao}"
    if extensao == ".bmp":
        _faixas(64, 64, origem, "BMP")
    else:
        origem.write_bytes(b"\x00\x00\x00\x1cftypavif" + b"\x00" * 64)

    with pytest.raises(ValueError) as erro:
        imagem_service.processar_imagem_produto(str(origem))

    assert str(erro.value) == MENSAGEM_FORMATO_INVALIDO
    assert list((tmp_path / "thumbs").iterdir()) == [], "a recusa deixou arquivo na pasta de miniaturas"


class _Registro(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.linhas: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.linhas.append(record)


@pytest.fixture
def log_do_app():
    """O logger do app não propaga para o root (`configurar_log`), então o
    `caplog` do pytest não o vê: o registro é pendurado nele direto."""
    registro = _Registro()
    logger = logging.getLogger(NOME_LOGGER)
    logger.addHandler(registro)
    try:
        yield registro
    finally:
        logger.removeHandler(registro)


def test_avif_renomeado_para_jpg_da_a_mesma_frase_e_deixa_o_motivo_no_log(
    monkeypatch, tmp_path, log_do_app
):
    """O caso que a extensão não pega: o navegador baixa `.avif` e alguém
    renomeia para `.jpg`. Passa pela lista, e quem recusa é a leitura — com a
    mesma frase para a tela, e o motivo técnico e o caminho no log."""
    monkeypatch.setattr(imagem_service, "pasta_thumbnails", lambda: tmp_path / "thumbs")
    (tmp_path / "thumbs").mkdir()
    disfarcado = tmp_path / "limonada.jpg"
    disfarcado.write_bytes(b"\x00\x00\x00\x1cftypavif" + b"\x00" * 64)

    with pytest.raises(ValueError) as erro:
        imagem_service.processar_imagem_produto(str(disfarcado))

    assert str(erro.value) == MENSAGEM_FORMATO_INVALIDO
    assert list((tmp_path / "thumbs").iterdir()) == []
    linhas = [r for r in log_do_app.linhas if str(disfarcado) in r.getMessage()]
    assert linhas, "a recusa não deixou rastro no log do app"
    assert linhas[0].exc_info is not None, "o log não guardou o motivo técnico da leitura"


def test_o_filtro_do_seletor_e_a_lista_homologada_na_grafia_do_qt():
    """Separado por ESPAÇO: o Qt lê o que está entre parênteses como a lista de
    padrões, e `*.png,` com vírgula seria um padrão que não casa com nada."""
    assert imagem_service.FILTRO_DO_SELETOR == "Imagens suportadas (*.png *.jpg *.jpeg *.webp)"


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
