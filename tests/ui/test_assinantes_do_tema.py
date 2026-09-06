"""Quem escuta a troca de tema é um método ligado, não uma `lambda`. Ver §3.14.

O `ThemeController` é singleton e vive o processo inteiro. Quem se inscreve nele
com `lambda` cria uma conexão **sem objeto receptor**: o Qt não tem em quem
olhar para saber que a tela morreu, então a conexão nunca é desfeita e a tela
fica presa ao controlador para sempre.

Hoje isso não cresce — as telas também vivem o processo inteiro —, e é por isso
que o §3.14 classificou o achado como armadilha latente, não vazamento ativo.
O que estes testes trancam é a hora em que a armadilha fecha: no dia em que
alguém recriar a tela de Login ou a de Configurações, uma por acesso.

## Por que a prova é indireta

O caminho óbvio seria descartar a tela, alternar o tema e esperar um estouro. Ele
não funciona, e vale registrar para ninguém tentar de novo: o `lambda` **de fato**
chama `setChecked` num widget cujo lado C++ já morreu, mas o PySide imprime esse
`RuntimeError` no console e devolve o `emit` como se nada tivesse acontecido. Um
teste escrito assim passa dos dois jeitos e não prova nada.

Então a prova é dividida, como no §3.3: um **teste de premissa**, que mede a
diferença entre as duas formas de conexão num par de objetos de mentira, e um
**teste de adoção**, que varre o código e exige que as telas usem a forma certa.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

import gestor_comercial.ui as pacote_ui
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView
from gestor_comercial.ui.views.login_view import LoginView

RAIZ_UI = Path(pacote_ui.__file__).parent


@pytest.fixture
def tema(qapp):
    """Devolve o controlador e garante que o tema volte ao escuro no fim.

    O controlador é singleton: sem esta limpeza, um teste que acende o modo
    claro deixaria todos os seguintes rodando com outra paleta.
    """
    controlador = ThemeController.instancia()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


# ---------------------------------------------------------------------------
# Premissa: é isto que separa as duas formas de conexão
# ---------------------------------------------------------------------------


class _Fonte(QObject):
    """Um singleton de mentira, no lugar do `ThemeController`."""

    mudou = Signal(dict)


class _TelaDeMentira(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.avisos = 0

    def _ao_mudar_tema(self, _tokens: dict) -> None:
        self.avisos += 1


def test_premissa_a_lambda_continua_sendo_chamada_depois_de_a_tela_morrer(qapp, assentar):
    """Sem objeto receptor, o Qt não tem como saber que a tela acabou."""
    fonte = _Fonte()
    tela = _TelaDeMentira()
    avisos: list[int] = []
    fonte.mudou.connect(lambda _tokens: avisos.append(1))

    tela.deleteLater()
    del tela
    assentar()
    fonte.mudou.emit({})

    assert avisos == [1], "a conexão por lambda deveria ter sobrevivido — premissa do §3.14"


def test_premissa_o_metodo_ligado_e_desconectado_junto_com_a_tela(qapp, assentar):
    """A outra metade: com `self` do outro lado, o Qt desfaz sozinho."""
    fonte = _Fonte()
    tela = _TelaDeMentira()
    fonte.mudou.connect(tela._ao_mudar_tema)
    sobrevivente = tela  # só para conseguir ler o contador depois

    tela.deleteLater()
    del tela
    assentar()
    fonte.mudou.emit({})

    assert sobrevivente.avisos == 0, "a tela descartada continuou recebendo a troca de tema"


# ---------------------------------------------------------------------------
# Adoção: as telas de verdade usam a forma certa
# ---------------------------------------------------------------------------


def _assinaturas_do_tema() -> list[tuple[str, ast.Call]]:
    """Todo `<algo>.mudou.connect(...)` da camada de UI, com onde ele está."""
    achados: list[tuple[str, ast.Call]] = []
    for caminho in sorted(RAIZ_UI.rglob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        relativo = caminho.relative_to(RAIZ_UI).as_posix()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                continue
            if no.func.attr != "connect":
                continue
            alvo = no.func.value
            if isinstance(alvo, ast.Attribute) and alvo.attr == "mudou":
                achados.append((f"{relativo}:{no.lineno}", no))
    return achados


def test_ninguem_assina_a_troca_de_tema_com_lambda():
    """O que precisa passar é um método ligado (`self.alguma_coisa`) — é o
    `self` que dá ao Qt um objeto para vigiar."""
    infratores = [
        onde
        for onde, chamada in _assinaturas_do_tema()
        if not (
            len(chamada.args) == 1
            and isinstance(chamada.args[0], ast.Attribute)
            and isinstance(chamada.args[0].value, ast.Name)
            and chamada.args[0].value.id == "self"
        )
    ]
    assert not infratores, (
        "assinantes de ThemeController.mudou sem objeto receptor:\n  " + "\n  ".join(infratores)
    )


def test_os_dois_assinantes_do_tema_continuam_mapeados():
    """§3.14 mapeou dois: `login_view` e `configuracoes_view`. Um terceiro
    aparecendo aqui é um lugar a mais para a armadilha fechar — entra de
    propósito, não por acidente."""
    arquivos = sorted({onde.split(":")[0] for onde, _ in _assinaturas_do_tema()})
    assert arquivos == ["views/configuracoes_view.py", "views/login_view.py"], arquivos


# ---------------------------------------------------------------------------
# Comportamento: o que o usuário vê continua igual
# ---------------------------------------------------------------------------


def test_a_pilula_espelha_o_tema_sem_entrar_em_laco(qapp, tema, auth):
    """A realimentação declarada no §3.14, exercida de ponta a ponta:
    `mudou` → `setChecked` → `toggled` → `alternar_para`.

    Se a guarda `if claro == self._claro: return` do `ThemeController` sumir,
    este teste não falha por asserção: ele estoura por recursão — que é
    exatamente o travamento que a guarda existe para impedir.
    """
    tela = ConfiguracoesView(auth)
    assert not tela._botao_tema_claro.isChecked()

    tema.alternar_para(True)

    assert tela._botao_tema_claro.isChecked(), "a pílula não acompanhou a troca de tema"
    assert tema.claro


def test_o_login_repinta_quando_outra_tela_troca_o_tema(qapp, tema, auth):
    """O motivo de a `LoginView` se inscrever: o logo isométrico é desenhado com
    `QPainter` e não pega o QSS global, então precisa ser avisado na mão."""
    tela = LoginView(auth)
    aplicados: list[dict] = []
    tela._aplicar_tema = aplicados.append  # type: ignore[method-assign]

    tema.alternar_para(True)

    assert aplicados, "o login não foi avisado da troca de tema"
