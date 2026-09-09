"""O modal "Nova subcategoria": contexto, conferência do nome e limpeza. §9.9.

É o sétimo modal em cartão do app e o primeiro que cadastra uma coisa que não
existia antes — até o §9.8 "criar uma subcategoria" era digitar a palavra dentro
do cadastro de um produto.

Os testes abaixo cobrem as três coisas que fariam a tela não servir:

1. **o contexto é a tela** — o cartão diz em qual categoria a subdivisão vai
   nascer E qual é a impressora dela, porque essa é a pergunta que uma tela de
   subdivisão levanta ("isso muda onde meu pedido sai?"). A resposta é não, e a
   tela precisa dizê-la;
2. **o nome repetido é barrado antes do erro** — a conferência roda na tecla e
   desliga o botão, em vez de deixar salvar para receber "já existe" de volta;
3. **nada sobra na memória** — o RNF do Celeron, com o escurecedor que é filho
   da JANELA e não do diálogo.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QWidget

from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.subcategoria_dialog import (
    LIMITE_NOME,
    DadosSubcategoria,
    SubcategoriaDialog,
)


@pytest.fixture
def abrir(qapp):
    """Monta o cartão sem `exec()` — e o descarta no fim do teste."""
    criados: list[SubcategoriaDialog] = []

    # `existentes=None` e não `existentes=[]` como padrão, e o `if is None` em
    # vez de `or`: com `or`, passar uma lista VAZIA cairia no padrão — e o teste
    # da categoria sem subdivisão testaria o caso oposto do que diz.
    def _abrir(categoria="Lanches", impressora="Cozinha", existentes=None, nome_inicial="", pai=None):
        if existentes is None:
            existentes = ["Podrão", "Artesanal"]
        modal = SubcategoriaDialog(
            categoria, impressora, existentes, pai, nome_inicial=nome_inicial
        )
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


def _rotulo(modal: SubcategoriaDialog, nome_do_objeto: str) -> str:
    return next(
        r.text() for r in modal.findChildren(QLabel) if r.objectName() == nome_do_objeto
    )


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


def test_o_cartao_diz_a_categoria_e_a_impressora(abrir):
    """A regra de ouro do §9.8 dita em voz alta: a bobina é da CATEGORIA, e
    continua sendo depois desta tela."""
    modal = abrir()

    assert _rotulo(modal, "subDialogDestino") == "LANCHES · COZINHA"


def test_categoria_sem_impressora_diz_isso_em_vez_de_ficar_em_branco(abrir):
    modal = abrir(impressora=None)

    assert _rotulo(modal, "subDialogDestino") == "LANCHES · SEM IMPRESSORA"


def test_as_subdivisoes_que_ja_existem_aparecem_apagadas(abrir):
    """Elas informam, não acionam: clicar numa delas só poderia levar a "já
    existe", e um controle cuja única resposta é um erro é pior que nenhum."""
    modal = abrir(existentes=["Podrão", "Artesanal"])

    pills = [r for r in modal.findChildren(QLabel) if r.objectName() == "subDialogPill"]

    assert [p.text() for p in pills] == ["PODRÃO", "ARTESANAL"]
    assert all(isinstance(p, QLabel) for p in pills), "as pílulas viraram botões clicáveis"


def test_categoria_sem_subdivisao_nao_mostra_a_faixa(abrir):
    modal = abrir(existentes=[])

    assert modal._faixa.isVisibleTo(modal) is False


# ---------------------------------------------------------------------------
# O nome
# ---------------------------------------------------------------------------


def test_o_botao_nasce_desligado_com_o_campo_vazio(abrir):
    modal = abrir()

    assert modal._botao_confirmar.isEnabled() is False
    assert _rotulo(modal, "subDialogAviso").startswith("DÊ UM NOME")


def test_digitar_um_nome_novo_liga_o_botao(abrir):
    modal = abrir()

    modal._campo_nome.setText("Prensado")

    assert modal._botao_confirmar.isEnabled() is True
    assert _rotulo(modal, "subDialogAviso") == "PRONTO PARA CRIAR"
    assert modal.resultado() == DadosSubcategoria(nome="Prensado")


def test_o_nome_repetido_desliga_o_botao_antes_de_salvar(abrir):
    modal = abrir(existentes=["Podrão"])

    modal._campo_nome.setText("Podrão")

    assert modal._botao_confirmar.isEnabled() is False
    assert "JÁ EXISTE" in _rotulo(modal, "subDialogAviso")


@pytest.mark.parametrize("quase", ["podrao", "PODRÃO", "  podrão  "])
def test_o_nome_quase_igual_tambem_e_barrado(abrir, quase):
    """A mesma comparação do service (acento, caixa e espaço repetido
    ignorados): avisar aqui evita a ida e volta de digitar, salvar e receber o
    erro."""
    modal = abrir(existentes=["Podrão"])

    modal._campo_nome.setText(quase)

    assert modal._botao_confirmar.isEnabled() is False


def test_editar_aceita_o_proprio_nome(abrir):
    """Renomear "Podrão" para "Podrão" (sem mexer) não pode acusar duplicidade."""
    modal = abrir(existentes=["Podrão", "Artesanal"], nome_inicial="Podrão")

    assert modal._botao_confirmar.isEnabled() is True
    assert modal.resultado() == DadosSubcategoria(nome="Podrão")


def test_editar_ainda_barra_o_nome_da_outra(abrir):
    modal = abrir(existentes=["Podrão", "Artesanal"], nome_inicial="Podrão")

    modal._campo_nome.setText("artesanal")

    assert modal._botao_confirmar.isEnabled() is False


def test_o_resultado_vem_aparado(abrir):
    modal = abrir()

    modal._campo_nome.setText("  Lanche   Prensado  ")

    assert modal.resultado() == DadosSubcategoria(nome="Lanche Prensado")


def test_o_contador_acompanha_a_digitacao(abrir):
    modal = abrir()

    modal._campo_nome.setText("Prensado")

    assert _rotulo(modal, "subDialogContador") == f"8/{LIMITE_NOME}"
    assert modal._campo_nome.maxLength() == LIMITE_NOME


def test_o_erro_do_service_aparece_sem_fechar_nem_perder_o_texto(abrir):
    """O modal é reaberto no `while` da view quando o service recusa: o gerente
    corrige sem redigitar."""
    modal = abrir()
    modal._campo_nome.setText("Prensado")

    modal.mostrar_erro_servico("Já existe a subcategoria 'Prensado' nesta categoria.")

    assert modal._campo_nome.text() == "Prensado"
    assert "JÁ EXISTE" in _rotulo(modal, "subDialogAviso")


# ---------------------------------------------------------------------------
# Teclado
# ---------------------------------------------------------------------------


def _tecla(modal: SubcategoriaDialog, tecla: Qt.Key) -> None:
    modal.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


def test_enter_cria_quando_ha_o_que_criar(qapp, abrir):
    modal = abrir()
    modal._campo_nome.setText("Prensado")

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() == QDialog.DialogCode.Accepted


def test_enter_com_nome_repetido_nao_faz_nada(qapp, abrir):
    """Sem isto, o Enter passaria por cima do botão desligado — e o gerente
    receberia o erro do service num modal que ele achava que estava travado."""
    modal = abrir(existentes=["Podrão"])
    modal._campo_nome.setText("Podrão")

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() != QDialog.DialogCode.Accepted


def test_esc_fecha_o_modal(qapp, abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Escape)

    assert modal.result() == QDialog.DialogCode.Rejected


# ---------------------------------------------------------------------------
# Ciclo de vida
# ---------------------------------------------------------------------------


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    """O escurecedor é filho da JANELA, não do diálogo: sem soltá-lo, uma tarde
    de idas e voltas ao cadastro deixaria uma pilha de retângulos pretos
    invisíveis pendurada no `MainWindow`, que vive o processo inteiro."""
    janela = QWidget()
    janela.show()

    for _ in range(5):
        modal = SubcategoriaDialog("Lanches", "Cozinha", ["Podrão"], janela)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar):
    """O caminho real do app: aberto com `exec()` e fechado pelo botão."""
    pai = QWidget()

    for _ in range(30):
        modal = SubcategoriaDialog("Lanches", "Cozinha", ["Podrão"], pai)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(SubcategoriaDialog) == []


def test_fechar_remove_o_filtro_de_eventos_e_solta_as_pilulas(qapp, abrir):
    modal = abrir()

    modal.reject()

    assert modal._pills == []
    assert modal._backdrop is None
