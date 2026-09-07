"""Testes de caos: o escudo sob fogo real do Qt (`Mitigação de Falhas.md` §4).

Os testes de `tests/unit/test_resiliencia.py` chamam o `sys.excepthook` na mão.
Estes não: eles quebram um widget de verdade e deixam o **Qt** decidir o que
fazer com a exceção. É a diferença entre provar que a peça funciona e provar que
ela está ligada no lugar certo — os dois caminhos do Qt são diferentes, e um
deles não passa pelo excepthook (C6).
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPushButton, QWidget

from gestor_comercial.core import resilience


@pytest.fixture
def escudo(tmp_path, escudo_isolado, qapp):
    """Escudo instalado com modal falso e log em `tmp_path`.

    Devolve `(caminho_do_log, lista_de_modais_mostrados)`.
    """
    destino = tmp_path / "logs" / "gestor.log"
    modais: list = []
    resilience.instalar_escudo(destino, mostrar_modal=modais.append)
    return destino, modais


def _texto_do_log(caminho) -> str:
    return caminho.read_text(encoding="utf-8") if caminho.exists() else ""


# ----------------------------------------------------------------------
# C1 — o cenário do roteiro: 1/0 dentro de um clique
# ----------------------------------------------------------------------


def test_c1_divisao_por_zero_no_clique_nao_derruba_o_app(escudo, qapp):
    """O clique quebra, o app continua de pé, e sobra registro do que houve."""
    caminho, modais = escudo
    botao = QPushButton("Enviar Pedido")
    botao.clicked.connect(lambda: 1 / 0)

    botao.click()

    assert qapp.instance() is not None, "o app tem que continuar vivo"
    assert "ZeroDivisionError" in _texto_do_log(caminho)
    assert len(modais) == 1, "o operador precisa saber que o clique morreu"

    botao.deleteLater()


def test_c1_o_app_continua_respondendo_depois_do_erro(escudo, qapp):
    """Sobreviver não basta: o clique SEGUINTE tem que funcionar.

    É o que separa "não fechou" de "não travou" — no balcão, um PDV vivo mas
    surdo é a mesma coisa que um PDV fechado.
    """
    _caminho, _modais = escudo
    quebrado = QPushButton()
    quebrado.clicked.connect(lambda: 1 / 0)
    saudavel = QPushButton()
    cliques: list[int] = []
    saudavel.clicked.connect(lambda: cliques.append(1))

    quebrado.click()
    saudavel.click()

    assert cliques == [1]

    quebrado.deleteLater()
    saudavel.deleteLater()


# ----------------------------------------------------------------------
# C4 — o repique: o mesmo defeito disparando sem parar
# ----------------------------------------------------------------------


def test_c4_defeito_repetido_gera_um_modal_e_todos_os_registros(escudo, qapp):
    """Um slot de atualização que estoura dispara a cada tick do timer.

    Sem anti-repique o operador levaria 200 modais empilhados e o PDV ficaria
    inutilizável — o escudo virando o travamento que veio evitar. O LOG, esse,
    registra todas: é ele que diz ao Vitor que foram 200 e não 1.
    """
    caminho, modais = escudo
    botao = QPushButton()
    botao.clicked.connect(lambda: 1 / 0)

    for _ in range(200):
        botao.click()

    assert len(modais) == 1, "anti-repique deixou passar mais de um aviso"
    assert _texto_do_log(caminho).count("ZeroDivisionError") == 200

    botao.deleteLater()


def test_c4_defeitos_distintos_avisam_cada_um(escudo, qapp):
    """O anti-repique é por assinatura: dois problemas juntos, dois avisos."""
    caminho, modais = escudo
    um = QPushButton()
    um.clicked.connect(lambda: 1 / 0)
    outro = QPushButton()
    outro.clicked.connect(lambda: {}["chave que não existe"])

    um.click()
    outro.click()

    assert len(modais) == 2
    conteudo = _texto_do_log(caminho)
    assert "ZeroDivisionError" in conteudo and "KeyError" in conteudo

    um.deleteLater()
    outro.deleteLater()


# ----------------------------------------------------------------------
# C6 — o caminho que o excepthook NÃO cobre
# ----------------------------------------------------------------------


def test_c6_override_virtual_blindado_nao_deixa_a_excecao_chegar_ao_qt(escudo, qapp):
    """O caminho que **mata o processo** — e a única peça que o evita.

    Medido nesta máquina (`Mitigação de Falhas.md` §1.6): sem o decorador, uma
    exceção que escapa de `paintEvent` faz o PySide6 imprimir `Error calling
    Python override`, chamar o excepthook e, **na segunda ocorrência, abortar o
    processo** (exit 1). Nenhum `sys.excepthook` salva: o `abort()` é do C++,
    depois de o hook já ter retornado. Esse é o "o programa sumiu da tela" de
    verdade.

    `nao_deixa_escapar` mata a exceção do lado Python, então o Qt nunca fica
    sabendo. Aqui a prova é repintar 50 vezes — o dobro do necessário para o
    abort — e o processo continuar de pé com tudo registrado.
    """
    caminho, modais = escudo

    class Quebrado(QWidget):
        @resilience.nao_deixa_escapar()
        def paintEvent(self, evento):  # noqa: N802 - assinatura do Qt
            raise RuntimeError("estouro dentro do paintEvent")

    widget = Quebrado()
    widget.resize(80, 80)
    widget.show()
    for _ in range(50):
        widget.repaint()
        qapp.processEvents()
    sys.stderr.flush()

    conteudo = _texto_do_log(caminho)
    assert "Erro contido em Quebrado.paintEvent" in conteudo
    assert "RuntimeError: estouro dentro do paintEvent" in conteudo
    assert modais == [], (
        "repintura não pode virar modal: dispara por quadro e o aviso viria "
        "antes de o operador ter chance de ler"
    )

    widget.hide()
    widget.deleteLater()


def test_c6_o_decorador_devolve_o_valor_seguro_de_cada_assinatura(escudo):
    """`None` num `sizeHint` trocaria o abort por um `TypeError` na conversão."""
    from PySide6.QtCore import QSize

    class Widget:
        @resilience.nao_deixa_escapar(retorno=QSize(0, 0))
        def sizeHint(self):  # noqa: N802
            raise RuntimeError("boom")

        @resilience.nao_deixa_escapar(retorno=False)
        def eventFilter(self, obj, evento):  # noqa: N802
            raise RuntimeError("boom")

    assert Widget().sizeHint() == QSize(0, 0)
    assert Widget().eventFilter(None, None) is False


def test_todo_override_virtual_esta_blindado():
    """Nenhum override do Qt em `ui/` pode existir sem `@nao_deixa_escapar`.

    Trava no espírito do `test_adocao_dos_utilitarios.py`: o decorador não pode
    depender de alguém lembrar dele na próxima tela. Um override esquecido não é
    detalhe de estilo — é o PDV podendo fechar sozinho no balcão.

    A definição de "override do Qt" é o marcador que o próprio projeto já usava
    antes desta etapa: `# noqa: N802 (override Qt)`.
    """
    import ast
    from pathlib import Path

    import gestor_comercial

    raiz = Path(gestor_comercial.__file__).parent / "ui"
    desprotegidos: list[str] = []

    for arquivo in sorted(raiz.rglob("*.py")):
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        arvore = ast.parse("\n".join(linhas))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.FunctionDef):
                continue
            assinatura = linhas[no.lineno - 1]
            if "override Qt" not in assinatura:
                continue
            blindado = any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Name)
                and d.func.id == "nao_deixa_escapar"
                for d in no.decorator_list
            )
            if not blindado:
                desprotegidos.append(f"{arquivo.name}:{no.lineno} {no.name}")

    assert not desprotegidos, (
        "override(s) do Qt sem `@nao_deixa_escapar` — uma exceção aqui aborta o "
        "processo na 2ª ocorrência (ver `core/resilience.py`):\n  "
        + "\n  ".join(desprotegidos)
    )


# ----------------------------------------------------------------------
# C5 — o único caminho que mata o processo de verdade
# ----------------------------------------------------------------------


def test_c5_estouro_fora_do_laco_de_eventos_e_o_unico_fatal(escudo, qapp):
    """Fora do `app.exec()` não há laço para continuar: o processo acabaria.

    É o caso que `main.py` cerca com `try/except` — a terceira peça. Aqui a
    prova é que o escudo registra mesmo sem laço de eventos rodando, que é a
    condição do boot.
    """
    caminho, modais = escudo

    try:
        raise RuntimeError("falha ao montar as views")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    assert "falha ao montar as views" in _texto_do_log(caminho)
    assert len(modais) == 1


def test_main_cerca_o_boot_e_o_teardown():
    """`main()` não pode ter caminho de saída sem rede.

    Trava a terceira peça no lugar: se alguém tirar o `try` que envolve o
    `UnitOfWork`, um estouro ao montar os services volta a fechar a janela sem
    dizer nada.
    """
    import ast
    from pathlib import Path

    import gestor_comercial

    fonte = (Path(gestor_comercial.__file__).parent / "main.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    funcao = next(
        no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == "main"
    )

    assert any(
        isinstance(no, ast.With)
        for tentativa in funcao.body
        if isinstance(tentativa, ast.Try)
        for no in tentativa.body
    ), "o `with UnitOfWork()` de main() saiu de dentro do try — ver Fase 2"

    assert "instalar_escudo" in fonte, "o escudo saiu do boot"
