"""O cartão único de confirmação de exclusão do Cardápio. §9.18.

Pedido do Vitor, com três mockups: trocar as caixas de mensagem do sistema da
exclusão de categoria, subcategoria e produto por um cartão no desenho do app —
e, escrito acima de tudo, **não fazer três classes**.

O que esta suíte cobra:

1. **os dois eixos** — a entidade decide o glifo, o rótulo, o título e a
   palavra do botão; o nível de proteção decide a tarja, o tom do aviso e o que
   o botão faz. Nenhum dos dois vaza para o outro;
2. **os construtores nomeados** — é neles que a contagem vira nível, com as
   frases exatas das três imagens;
3. **o botão** — confirma num clique, pede a Senha Master antes (e volta ao
   cartão se ela não passar), ou nem liga;
4. **o teclado** — Enter aciona o botão se ele estiver ligado, Esc cancela;
5. **o desenho** — o rodapé cabe no cartão com a fonte da marca, nos dois temas
   e em todas as variantes, e o nome comprido quebra linha em vez de sumir;
6. **o ciclo de vida** — o escurecedor sai com o cartão, as ligações saem
   nominalmente, e trinta aberturas não deixam nada para trás.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

import gestor_comercial
from gestor_comercial.services.cardapio_service import VinculosDoProduto
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ALERTA,
    GLIFO_CAIXA,
    GLIFO_ETIQUETA,
    GLIFO_PASTA,
    GlifoSolto,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.confirmacao_exclusao_dialog import (
    ENTIDADES,
    NIVEIS,
    Aviso,
    ConfirmacaoExclusaoDialog,
    EntidadeDoCardapio,
    Protecao,
)
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog

SEM_VINCULO = VinculosDoProduto(vendido=False, combos_que_o_contem=0, componentes=0)


class _Barreira:
    """A Senha Master de mentira: conta as chamadas e responde o que mandarem."""

    def __init__(self, resposta: bool = True) -> None:
        self.resposta = resposta
        self.cartoes: list[QWidget] = []

    def __call__(self, cartao: QWidget) -> bool:
        self.cartoes.append(cartao)
        return self.resposta


@pytest.fixture
def criar(qapp):
    """Monta cartões sem `exec()` e os descarta no fim do teste."""
    criados: list[ConfirmacaoExclusaoDialog] = []

    def _criar(fabrica, *args, **kwargs) -> ConfirmacaoExclusaoDialog:
        modal = fabrica(*args, **kwargs)
        criados.append(modal)
        return modal

    yield _criar
    for modal in criados:
        modal.deleteLater()


def _leitura(modal: ConfirmacaoExclusaoDialog) -> dict:
    return {
        "secao": modal._secao.text(),
        "titulo": modal._titulo.text(),
        "nome": modal._nome.text(),
        "aviso": modal._aviso_titulo.text(),
        "texto": modal._aviso_texto.text(),
        "botao": modal._botao_confirmar.text(),
        "ligado": modal._botao_confirmar.isEnabled(),
    }


def _rotulo(modal: ConfirmacaoExclusaoDialog, nome_do_objeto: str) -> str:
    return next(r.text() for r in modal.findChildren(QLabel) if r.objectName() == nome_do_objeto)


def _tom(modal: ConfirmacaoExclusaoDialog) -> str:
    aviso = next(w for w in modal.findChildren(QWidget) if w.objectName() == "exclusaoDialogAviso")
    return aviso.property("tom")


def _glifo_de(modal: ConfirmacaoExclusaoDialog, nome_do_quadro: str) -> str:
    quadro = next(w for w in modal.findChildren(QWidget) if w.objectName() == nome_do_quadro)
    return quadro.findChild(GlifoSolto)._glifo


def _tecla(modal: ConfirmacaoExclusaoDialog, tecla: Qt.Key) -> None:
    modal.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


# ---------------------------------------------------------------------------
# 1. As três imagens, frase por frase
# ---------------------------------------------------------------------------


def test_foto_1_a_categoria_com_produtos(criar):
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Acompanhamentos", 5, 0, _Barreira())

    assert _leitura(modal) == {
        "secao": "EXCLUSÃO PROTEGIDA",
        "titulo": "Excluir categoria",
        "nome": "Acompanhamentos",
        "aviso": "Esta categoria contém 5 produtos.",
        "texto": (
            "Para excluí-la, será necessário confirmar a Senha Master. Os produtos com "
            "vendas registradas serão arquivados e o histórico permanecerá intacto."
        ),
        "botao": "Excluir com Senha Master",
        "ligado": True,
    }
    assert _rotulo(modal, "exclusaoDialogRotulo") == "CATEGORIA SELECIONADA"
    assert (modal.protecao, _tom(modal)) == (Protecao.SENHA_MASTER, "protegido")


def test_foto_2_o_produto_sem_historico(criar):
    modal = criar(ConfirmacaoExclusaoDialog.para_produto, "Arroz", SEM_VINCULO, _Barreira())

    assert _leitura(modal) == {
        "secao": "AÇÃO PERMANENTE",
        "titulo": "Excluir produto",
        "nome": "Arroz",
        "aviso": "Deseja excluir este produto permanentemente?",
        "texto": "Esta ação não pode ser desfeita.",
        "botao": "Excluir produto",
        "ligado": True,
    }
    # "SELECIONADO", e não o "SELECIONADA" que a imagem trouxe da de categoria.
    assert _rotulo(modal, "exclusaoDialogRotulo") == "PRODUTO SELECIONADO"
    assert (modal.protecao, _tom(modal)) == (Protecao.SIMPLES, "perigo")


def test_foto_3_a_subcategoria_bloqueada(criar):
    modal = criar(
        ConfirmacaoExclusaoDialog.para_subcategoria, "Guarnições", 3, _Barreira(), cascata=False
    )

    assert _leitura(modal) == {
        "secao": "CONFIRMAR EXCLUSÃO",
        "titulo": "Excluir subcategoria",
        "nome": "Guarnições",
        "aviso": "Esta subcategoria contém 3 produtos.",
        "texto": "Mova ou exclua os produtos antes de continuar.",
        "botao": "Excluir subcategoria",
        "ligado": False,
    }
    assert _rotulo(modal, "exclusaoDialogRotulo") == "SUBCATEGORIA SELECIONADA"
    assert (modal.protecao, _tom(modal)) == (Protecao.BLOQUEADA, "perigo")


# ---------------------------------------------------------------------------
# 2. A contagem vira nível — nos construtores, e só neles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("produtos", "subcategorias", "protecao", "aviso"),
    [
        (0, 0, Protecao.SIMPLES, "Deseja excluir esta categoria?"),
        (1, 0, Protecao.SENHA_MASTER, "Esta categoria contém 1 produto."),
        # Só subdivisão, sem produto nenhum: ainda é Senha Master (§9.14).
        (0, 2, Protecao.SENHA_MASTER, "Esta categoria contém 2 subcategorias."),
        (3, 1, Protecao.SENHA_MASTER, "Esta categoria contém 3 produtos e 1 subcategoria."),
    ],
)
def test_categoria_o_nivel_sai_da_contagem(criar, produtos, subcategorias, protecao, aviso):
    modal = criar(
        ConfirmacaoExclusaoDialog.para_categoria, "Lanches", produtos, subcategorias, _Barreira()
    )

    assert (modal.protecao, modal._aviso_titulo.text()) == (protecao, aviso)


@pytest.mark.parametrize(
    ("produtos", "cascata", "protecao"),
    [
        (0, True, Protecao.SIMPLES),
        # Vazia é vazia qualquer que seja a regra: bloquear não tem o que bloquear.
        (0, False, Protecao.SIMPLES),
        (1, True, Protecao.SENHA_MASTER),
        (1, False, Protecao.BLOQUEADA),
    ],
)
def test_subcategoria_o_nivel_sai_da_contagem_e_da_regra(criar, produtos, cascata, protecao):
    modal = criar(
        ConfirmacaoExclusaoDialog.para_subcategoria, "Podrão", produtos, _Barreira(), cascata=cascata
    )

    assert modal.protecao is protecao


def test_a_regra_padrao_da_subcategoria_e_a_do_paragrafo_9_13(criar):
    """A decisão do Vitor, reafirmada no §9.18: sem dizer nada, a subdivisão
    cheia vai para a Senha Master, e não para o bloqueio da Foto 3."""
    modal = criar(ConfirmacaoExclusaoDialog.para_subcategoria, "Podrão", 2, _Barreira())

    assert modal.protecao is Protecao.SENHA_MASTER
    assert modal._aviso_titulo.text() == "Esta subcategoria contém 2 produtos."
    assert modal._aviso_texto.text() == criar(
        ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 2, 0, _Barreira()
    )._aviso_texto.text(), "as duas cascatas dizem a mesma regra com a mesma frase"


@pytest.mark.parametrize(
    ("vinculos", "titulo"),
    [
        (VinculosDoProduto(True, 0, 0), "Este produto tem vendas registradas."),
        (VinculosDoProduto(False, 1, 0), "Este produto faz parte de 1 combo."),
        (VinculosDoProduto(False, 3, 0), "Este produto faz parte de 3 combos."),
        (VinculosDoProduto(False, 0, 2), "Este produto é um combo com 2 componentes."),
        # A venda é o vínculo mais pesado e fica no título; o combo vai para a descrição.
        (VinculosDoProduto(True, 2, 0), "Este produto tem vendas registradas."),
        (VinculosDoProduto(False, 1, 4), "Este produto faz parte de 1 combo."),
    ],
)
def test_produto_com_qualquer_vinculo_pede_a_senha_master(criar, vinculos, titulo):
    modal = criar(ConfirmacaoExclusaoDialog.para_produto, "X Tudo", vinculos, _Barreira())

    assert modal.protecao is Protecao.SENHA_MASTER
    assert modal._aviso_titulo.text() == titulo
    assert modal._secao.text() == "EXCLUSÃO PROTEGIDA"
    assert modal._botao_confirmar.text() == "Excluir com Senha Master"


def test_a_descricao_do_produto_diz_tudo_o_que_vai_acontecer(criar):
    """Quem digita a Senha Master precisa saber, antes, que um combo que
    ninguém mandou excluir vai perder um componente."""
    vendido_em_combo = criar(
        ConfirmacaoExclusaoDialog.para_produto, "Batata", VinculosDoProduto(True, 2, 0), _Barreira()
    )
    combo = criar(
        ConfirmacaoExclusaoDialog.para_produto,
        "Combo Pastel",
        VinculosDoProduto(False, 0, 3),
        _Barreira(),
    )
    so_vendido = criar(
        ConfirmacaoExclusaoDialog.para_produto, "X Egg", VinculosDoProduto(True, 0, 0), _Barreira()
    )

    assert vendido_em_combo._aviso_texto.text() == (
        "Para excluí-lo, será necessário confirmar a Senha Master. "
        "Ele sai da composição de 2 combos. "
        "Ele será arquivado: sai do cardápio e dos novos pedidos, e os relatórios e "
        "cupons passados continuam intactos."
    )
    assert "A composição dele é desfeita, e os componentes continuam no cardápio." in (
        combo._aviso_texto.text()
    )
    assert "combo" not in so_vendido._aviso_texto.text()


# ---------------------------------------------------------------------------
# 3. Os dois eixos não se misturam
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entidade", "glifo"),
    [
        (EntidadeDoCardapio.CATEGORIA, GLIFO_PASTA),
        (EntidadeDoCardapio.SUBCATEGORIA, GLIFO_ETIQUETA),
        (EntidadeDoCardapio.PRODUTO, GLIFO_CAIXA),
    ],
)
@pytest.mark.parametrize("protecao", list(Protecao))
def test_a_entidade_decide_as_palavras_e_o_nivel_decide_o_resto(criar, entidade, glifo, protecao):
    """As nove combinações, montadas pelo `__init__`: nenhuma palavra da
    entidade muda com o nível, e nenhuma decisão do nível muda com a entidade."""
    modal = criar(
        ConfirmacaoExclusaoDialog,
        entidade,
        "Qualquer",
        protecao,
        Aviso("Título", "Texto"),
        autorizar=_Barreira(),
    )
    papel, nivel = ENTIDADES[entidade], NIVEIS[protecao]

    assert _glifo_de(modal, "exclusaoDialogItemIcone") == glifo
    assert modal._titulo.text() == modal.windowTitle() == papel.titulo
    assert _rotulo(modal, "exclusaoDialogRotulo") == papel.rotulo
    assert modal._secao.text() == nivel.secao
    assert _tom(modal) == nivel.tom
    assert modal._botao_confirmar.text() == (nivel.botao or papel.botao)
    assert modal._botao_confirmar.isEnabled() is nivel.liberado


def test_o_cabecalho_e_sempre_a_lixeira(criar):
    for protecao in Protecao:
        modal = criar(
            ConfirmacaoExclusaoDialog,
            EntidadeDoCardapio.PRODUTO,
            "X",
            protecao,
            Aviso("a", "b"),
            autorizar=_Barreira(),
        )
        assert _glifo_de(modal, "exclusaoDialogBadge") == "lixeira"


@pytest.mark.parametrize(
    ("protecao", "token"),
    [
        (Protecao.SIMPLES, "exclusao_perigo_glifo"),
        (Protecao.SENHA_MASTER, "exclusao_protegida_glifo"),
        (Protecao.BLOQUEADA, "exclusao_perigo_glifo"),
    ],
)
def test_o_alerta_desenhado_acompanha_o_tom(criar, protecao, token):
    modal = criar(
        ConfirmacaoExclusaoDialog,
        EntidadeDoCardapio.CATEGORIA,
        "X",
        protecao,
        Aviso("a", "b"),
        autorizar=_Barreira(),
    )
    alerta = next(g for g in modal.findChildren(GlifoSolto) if g._glifo == GLIFO_ALERTA)

    assert alerta._token == token


def test_a_exclusao_protegida_sem_barreira_nem_chega_a_existir(qapp):
    """Um cartão que promete a Senha Master e confirma sem ela é o pior defeito
    que esta tela pode ter — e ele só apareceria na hora de apagar algo."""
    with pytest.raises(ValueError, match="barreira de credencial"):
        ConfirmacaoExclusaoDialog(
            EntidadeDoCardapio.CATEGORIA, "Lanches", Protecao.SENHA_MASTER, Aviso("a", "b")
        )


# ---------------------------------------------------------------------------
# 4. O botão
# ---------------------------------------------------------------------------


def test_a_confirmacao_simples_fecha_aceita_sem_pedir_credencial(criar):
    barreira = _Barreira()
    modal = criar(ConfirmacaoExclusaoDialog.para_produto, "Arroz", SEM_VINCULO, barreira)

    modal._botao_confirmar.click()

    assert modal.result() == QDialog.DialogCode.Accepted
    assert barreira.cartoes == []


def test_a_senha_master_e_pedida_com_o_cartao_como_parent(criar):
    barreira = _Barreira(resposta=True)
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 2, 0, barreira)

    modal._botao_confirmar.click()

    assert barreira.cartoes == [modal]
    assert modal.result() == QDialog.DialogCode.Accepted


def test_a_senha_recusada_mantem_o_cartao_aberto_para_tentar_de_novo(criar):
    barreira = _Barreira(resposta=False)
    modal = criar(ConfirmacaoExclusaoDialog.para_subcategoria, "Podrão", 2, barreira)
    modal.show()

    modal._botao_confirmar.click()
    assert modal.isVisible() is True
    assert modal.result() != QDialog.DialogCode.Accepted

    barreira.resposta = True
    modal._botao_confirmar.click()

    assert len(barreira.cartoes) == 2
    assert modal.result() == QDialog.DialogCode.Accepted


def test_o_bloqueado_nao_confirma_nem_chamado_direto(criar):
    """O `setEnabled(False)` protege o clique; a conferência dentro de
    `_confirmar` protege o Enter e qualquer outro caminho que chegue lá."""
    modal = criar(
        ConfirmacaoExclusaoDialog.para_subcategoria, "Guarnições", 3, _Barreira(), cascata=False
    )

    modal._confirmar()

    assert modal.result() != QDialog.DialogCode.Accepted


def test_o_pin_de_verdade_abre_por_cima_do_cartao(qapp, auth, assentar):
    """O escurecedor do PIN cobre o CARTÃO (a janela translúcida de trás, com
    os cantos de 16px) e sai com ele; o cartão continua aberto e sem escurecedor
    próprio pendurado depois que o PIN fecha."""
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    visto_durante: list[int] = []

    def barreira(cartao: QWidget) -> bool:
        pin = PinPadDialog.para_exclusao(auth, "a categoria 'Lanches'", cartao)

        def olhar_e_fechar() -> None:
            visto_durante.append(len(cartao.findChildren(Backdrop)))
            pin.reject()

        QTimer.singleShot(0, olhar_e_fechar)
        resultado = pin.exec()
        pin.deleteLater()
        return resultado == QDialog.DialogCode.Accepted

    modal = ConfirmacaoExclusaoDialog.para_categoria("Lanches", 2, 0, barreira, janela)
    modal.show()
    qapp.processEvents()

    modal._botao_confirmar.click()
    assentar()

    assert visto_durante == [1]
    assert modal.findChildren(Backdrop) == []
    assert modal.isVisible() is True
    assert len(janela.findChildren(Backdrop)) == 1, "o escurecedor do próprio cartão continua"
    modal.reject()
    modal.deleteLater()
    assentar()
    assert janela.findChildren(Backdrop) == []


# ---------------------------------------------------------------------------
# 5. Teclado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tecla", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_aciona_a_exclusao_simples(criar, tecla):
    modal = criar(ConfirmacaoExclusaoDialog.para_produto, "Arroz", SEM_VINCULO, _Barreira())

    _tecla(modal, tecla)

    assert modal.result() == QDialog.DialogCode.Accepted


def test_enter_na_protegida_pede_a_senha_antes(criar):
    barreira = _Barreira(resposta=False)
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 1, 0, barreira)

    _tecla(modal, Qt.Key.Key_Return)

    assert barreira.cartoes == [modal]
    assert modal.result() != QDialog.DialogCode.Accepted


def test_enter_no_bloqueado_nao_faz_nada(criar):
    barreira = _Barreira()
    modal = criar(
        ConfirmacaoExclusaoDialog.para_subcategoria, "Guarnições", 3, barreira, cascata=False
    )

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() != QDialog.DialogCode.Accepted
    assert barreira.cartoes == []


@pytest.mark.parametrize("protecao", list(Protecao))
def test_esc_cancela_em_qualquer_nivel(criar, protecao):
    barreira = _Barreira()
    modal = criar(
        ConfirmacaoExclusaoDialog,
        EntidadeDoCardapio.PRODUTO,
        "X",
        protecao,
        Aviso("a", "b"),
        autorizar=barreira,
    )

    _tecla(modal, Qt.Key.Key_Escape)

    assert modal.result() == QDialog.DialogCode.Rejected
    assert barreira.cartoes == []


@pytest.mark.parametrize("nome_do_botao", ["_botao_fechar", "_botao_cancelar"])
def test_o_x_e_o_cancelar_rejeitam(criar, nome_do_botao):
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 1, 0, _Barreira())

    getattr(modal, nome_do_botao).click()

    assert modal.result() == QDialog.DialogCode.Rejected


def test_os_botoes_nao_roubam_o_teclado(criar):
    """Com o foco num botão, o Enter dispararia AQUELE botão — o Cancelar, se
    fosse o último tocado (§9.4). Quem lê o teclado é o diálogo."""
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 1, 0, _Barreira())

    for botao in modal.findChildren(QPushButton):
        assert botao.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert botao.autoDefault() is False
    assert modal.focusPolicy() == Qt.FocusPolicy.StrongFocus


# ---------------------------------------------------------------------------
# 6. O desenho
# ---------------------------------------------------------------------------


@pytest.fixture(params=[False, True], ids=["escuro", "claro"])
def com_fonte_e_tema(qapp, request):
    """A fonte da marca e o QSS, antes de medir — as duas metades importam.

    Sem a fonte, o `offscreen` mede quase nada e o aperto não acontece (a
    armadilha do §9.5); sem o QSS, os tamanhos de letra não são os do app.
    Roda nos dois temas porque o QSS é montado de novo a cada troca, e um token
    que faltasse num dos dois estouraria só ali.
    """
    caminho = (
        Path(gestor_comercial.__file__).resolve().parents[2]
        / "resources"
        / "fonts"
        / "ArchivoBlack-Regular.ttf"
    )
    if not caminho.exists():  # pragma: no cover - só num checkout incompleto
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    assert identificador != -1, "o Qt recusou a fonte da marca"
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    controlador.alternar_para(request.param)
    try:
        yield
    finally:
        controlador.alternar_para(False)
        QFontDatabase.removeApplicationFont(identificador)


_VARIANTES = {
    "categoria_protegida": lambda b, p: ConfirmacaoExclusaoDialog.para_categoria(
        "Acompanhamentos", 5, 2, b, p
    ),
    "categoria_vazia": lambda b, p: ConfirmacaoExclusaoDialog.para_categoria("Sobremesas", 0, 0, b, p),
    "subcategoria_protegida": lambda b, p: ConfirmacaoExclusaoDialog.para_subcategoria(
        "Guarnições", 3, b, p
    ),
    "subcategoria_bloqueada": lambda b, p: ConfirmacaoExclusaoDialog.para_subcategoria(
        "Guarnições", 3, b, p, cascata=False
    ),
    "produto_simples": lambda b, p: ConfirmacaoExclusaoDialog.para_produto("Arroz", SEM_VINCULO, b, p),
    "produto_com_tudo": lambda b, p: ConfirmacaoExclusaoDialog.para_produto(
        "Cachorro Quente Linguiça Especial com Bacon, Cheddar e Batata Palha",
        VinculosDoProduto(True, 2, 3),
        b,
        p,
    ),
}


@pytest.mark.parametrize("variante", list(_VARIANTES))
def test_nada_do_cartao_e_espremido(qapp, com_fonte_e_tema, variante):
    """Nenhum rótulo nem botão desenhado menor do que pede, e o cartão inteiro
    abaixo dos 728px úteis de um monitor de 768px.

    Mede `width() < sizeHint().width()` nos que não quebram linha, que é o que o
    layout decide: quando a soma não cabe, o Qt espreme a peça e o corte
    aparece. Nos que quebram linha a medida é a altura: `heightForWidth` na
    largura que eles têm, contra a altura que receberam.
    """
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = _VARIANTES[variante](_Barreira(), janela)
    modal.show()
    qapp.processEvents()

    espremidos = {}
    for peca in modal.findChildren(QWidget):
        if not isinstance(peca, (QLabel, QPushButton)):
            continue
        if isinstance(peca, QLabel) and peca.wordWrap():
            if peca.height() < peca.heightForWidth(peca.width()):
                espremidos[peca.objectName()] = ("altura", peca.height(), peca.heightForWidth(peca.width()))
        elif peca.width() < peca.sizeHint().width():
            espremidos[peca.objectName()] = ("largura", peca.width(), peca.sizeHint().width())
    altura, largura = modal.height(), modal.width()

    modal.reject()
    modal.deleteLater()
    assert not espremidos, f"peças espremidas (eixo, tem, pede): {espremidos}"
    assert largura == ConfirmacaoExclusaoDialog.LARGURA_CARTAO_PX
    assert altura <= 728


def test_o_nome_comprido_quebra_linha_e_nao_perde_letra(criar):
    """É o nome do que vai ser apagado: reticências numa confirmação destrutiva
    pedem para o gerente confirmar o que ele não leu inteiro."""
    nome = "Cachorro Quente Linguiça Especial com Bacon, Cheddar e Batata Palha"
    modal = criar(ConfirmacaoExclusaoDialog.para_produto, nome, SEM_VINCULO, _Barreira())

    assert modal._nome.text() == nome
    assert modal._nome.wordWrap() is True
    assert modal._aviso_titulo.wordWrap() is modal._aviso_texto.wordWrap() is True


# ---------------------------------------------------------------------------
# 7. Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


def _uma_de_cada(pai: QWidget) -> list[ConfirmacaoExclusaoDialog]:
    return [fabrica(_Barreira(), pai) for fabrica in _VARIANTES.values()]


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    """O escurecedor é filho da JANELA: sem soltá-lo, uma tarde de exclusões
    deixaria retângulos pretos invisíveis pendurados no `MainWindow`."""
    janela = QWidget()
    janela.show()

    for modal in _uma_de_cada(janela):
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar):
    """O caminho real do app: aberto com `exec()` e fechado pelo gesto."""
    pai = QWidget()

    for volta in range(30):
        modal = list(_VARIANTES.values())[volta % len(_VARIANTES)](_Barreira(), pai)
        QTimer.singleShot(0, modal.reject if volta % 2 else modal._botao_cancelar.click)
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(ConfirmacaoExclusaoDialog) == []
    assert pai.findChildren(QWidget) == []


def test_fechar_desliga_os_tres_sinais(criar):
    """O `unbind` do pedido: depois de fechado, nem o botão vermelho chama a
    barreira, nem o Cancelar mexe no resultado."""
    barreira = _Barreira()
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 1, 0, barreira)
    modal.reject()
    modal.setResult(QDialog.DialogCode.Accepted)

    modal._botao_confirmar.click()
    modal._botao_cancelar.click()
    modal._botao_fechar.click()

    assert barreira.cartoes == []
    assert modal.result() == QDialog.DialogCode.Accepted
    assert modal._backdrop is None


def test_soltar_os_recursos_duas_vezes_e_silencioso(criar):
    """A trava `_limpo`, medida pelo AVISO (§9.12): nesta versão do PySide6 o
    segundo `disconnect` devolve `False` e imprime `RuntimeWarning` em vez de
    estourar."""
    modal = criar(ConfirmacaoExclusaoDialog.para_categoria, "Lanches", 1, 0, _Barreira())
    modal.reject()

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        modal._soltar_recursos()

    assert [str(a.message) for a in avisos] == []
    assert modal.result() == QDialog.DialogCode.Rejected
