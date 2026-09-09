"""O modal "Novo funcionário": identidade, grade de cargos, situação e limpeza.

Esta tela não é a mais usada do turno (essa é a de lançar item), mas é a que
decide **quem existe no sistema** — e o cargo que sai daqui vai para o banco,
aparece na comanda como quem atendeu e é o que o painel de detalhe usa para
dizer se a pessoa tem acesso total ao PDV. Os testes cobrem, nessa ordem:

1. **o dado certo sai** — nome, cargo, telefone e situação, do jeito que a view
   vai entregar ao `FuncionarioService`. O caso mais fácil de errar em silêncio
   é o cargo: são cinco cards, e clicar num deles não pode deixar dois marcados
   nem gravar o rótulo do card em vez do valor do enum;
2. **o que a tela promete bate com o que o sistema faz** — o rodapé diz
   "CAIXA · ACESSO LIBERADO", e é a MESMA lista que o painel de detalhe lê para
   escrever "ACESSO: Total". Enquanto forem duas listas, uma pode mudar sozinha;
3. **a máscara de telefone não estraga cadastro antigo** — `telefone` é texto
   livre e sempre foi, e abrir o modal para trocar o cargo de alguém não pode
   remontar um recado gravado ali como se fosse número;
4. **nada sobra na memória** — o RNF do Celeron. Trinta aberturas não podem
   deixar diálogo preso à view nem escurecedor pendurado na janela.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.domain.enums import CargoFuncionario
from gestor_comercial.ui.views.funcionarios_view import FuncionariosView
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.funcionario_dialog import (
    CARGOS,
    CARGOS_COM_ACESSO_TOTAL,
    FuncionarioDialog,
    formatar_telefone,
    iniciais,
    resumo_de_acesso,
)


@pytest.fixture
def abrir(qapp):
    """Monta o modal sem `exec()` — e o descarta no fim do teste."""
    criados: list[FuncionarioDialog] = []

    def _abrir(funcionario=None, pai=None):
        modal = FuncionarioDialog(funcionario, pai)
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


def _clicar_cargo(modal: FuncionarioDialog, cargo: str) -> None:
    """Clica no card como o operador clica — pelo sinal, não pelo estado."""
    modal._cards[cargo].clicado.emit()


def _tecla(modal: FuncionarioDialog, tecla: Qt.Key) -> None:
    modal.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


# ---------------------------------------------------------------------------
# Iniciais e avatar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Ana Beatriz Souza", "AS"),
        ("Ana Beatriz", "AB"),
        ("Pedro", "P"),
        ("  joana   silva  ", "JS"),
        ("", "—"),
        ("   ", "—"),
    ],
)
def test_as_iniciais_saem_da_primeira_e_da_ultima_palavra(nome, esperado):
    """Primeira + última, e não as duas primeiras: é o monograma de sempre
    (nome e sobrenome), e é o mesmo que a linha da lista já mostrava antes de
    existir modal nenhum. Se os dois divergirem, o cadastro que a pessoa acabou
    de conferir aparece com outra sigla na linha de baixo."""
    assert iniciais(nome) == esperado


def test_o_avatar_acompanha_a_digitacao(abrir):
    modal = abrir()
    assert modal._avatar.text() == "—"

    modal._campo_nome.setText("Ana Beatriz Souza")

    assert modal._avatar.text() == "AS"


def test_o_avatar_ja_nasce_certo_na_edicao(abrir, funcionarios, gerente):
    """`textChanged`, e não `textEdited`: quem escreve no campo aqui é o código,
    e com `textEdited` o avatar abriria em branco na edição."""
    pessoa = funcionarios.criar("Ana Beatriz Souza", "Caixa")

    modal = abrir(pessoa)

    assert modal._avatar.text() == "AS"


# ---------------------------------------------------------------------------
# Cargo
# ---------------------------------------------------------------------------


def test_a_grade_tem_os_cinco_cargos_do_enum():
    """A grade sai de `CargoFuncionario`, não de uma lista paralela: cargo novo
    no enum sem card aqui viraria uma opção que o service aceita e a tela não
    oferece."""
    assert [cargo.valor for cargo in CARGOS] == [cargo.value for cargo in CargoFuncionario]


def test_clicar_num_card_marca_so_ele(abrir):
    modal = abrir()
    _clicar_cargo(modal, "Garçom")
    _clicar_cargo(modal, "Cozinha")

    marcados = [valor for valor, card in modal._cards.items() if card.property("selecionado")]

    assert marcados == ["Cozinha"]


def test_o_cargo_escolhido_e_o_valor_que_vai_pro_banco(abrir):
    """O card mostra "Garçom" e é isso que `FuncionarioService._validar_cargo`
    espera — não um índice, não o rótulo em caixa alta do rodapé."""
    modal = abrir()
    modal._campo_nome.setText("Pedro")
    _clicar_cargo(modal, "Garçom")

    assert modal.resultado().cargo == CargoFuncionario.GARCOM.value


def test_sem_clicar_em_cargo_nenhum_o_cadastro_sai_sem_cargo(abrir):
    """`criar(nome, None)` é caminho legítimo do service (cadastro sem função
    definida). O modal não pode inventar um cargo padrão."""
    modal = abrir()
    modal._campo_nome.setText("Pedro")

    assert modal.resultado().cargo is None


def test_a_edicao_abre_com_o_cargo_ja_marcado(abrir, funcionarios, gerente):
    pessoa = funcionarios.criar("Joana", "Cozinha")

    modal = abrir(pessoa)

    assert modal._cards["Cozinha"].property("selecionado") is True


def test_cargo_desconhecido_nao_marca_card_nenhum(abrir, funcionarios, gerente):
    """Cadastro gravado antes de uma opção mudar de nome (foi o caso de
    "Atendente" → "Entregador", migração `a7f3c2e5d918`). A tela não pode
    marcar um card qualquer nem afirmar um acesso que não sabe."""
    pessoa = funcionarios.criar("Joana", "Cozinha")
    pessoa.cargo = "Atendente"

    modal = abrir(pessoa)

    assert not any(card.property("selecionado") for card in modal._cards.values())
    assert modal._label_resumo.text() == "SELECIONE UM CARGO"


# ---------------------------------------------------------------------------
# Resumo de acesso — a mesma verdade do painel de detalhe
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cargo", "esperado"),
    [
        ("Gerente", "GERENTE · ACESSO TOTAL"),
        ("Caixa", "CAIXA · ACESSO LIBERADO"),
        ("Garçom", "GARÇOM · APENAS PEDIDOS"),
        ("Cozinha", "COZINHA · APENAS PREPARO"),
        ("Entregador", "ENTREGADOR · APENAS ENTREGAS"),
        (None, "SELECIONE UM CARGO"),
    ],
)
def test_o_rodape_resume_o_acesso_do_cargo_marcado(abrir, cargo, esperado):
    modal = abrir()
    if cargo is not None:
        _clicar_cargo(modal, cargo)

    assert modal._label_resumo.text() == esperado


def test_o_acesso_total_do_rodape_e_o_mesmo_do_painel_de_detalhe():
    """§3.14: "ACESSO" é derivado do cargo, não gravado. O rodapé do modal e a
    linha ACESSO do detalhe leem a MESMA lista — enquanto eram duas, "Gerente e
    Caixa" precisava estar certo em dois arquivos ao mesmo tempo."""
    assert CARGOS_COM_ACESSO_TOTAL == {"Gerente", "Caixa"}
    for cargo in CARGOS:
        total_no_rodape = "TOTAL" in resumo_de_acesso(cargo.valor) or "LIBERADO" in resumo_de_acesso(
            cargo.valor
        )
        assert total_no_rodape == (cargo.valor in CARGOS_COM_ACESSO_TOTAL), cargo.valor


# ---------------------------------------------------------------------------
# Telefone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("", ""),
        ("1", "(1"),
        ("11", "(11"),
        ("119", "(11) 9"),
        ("119000", "(11) 9000"),
        ("1190000", "(11) 9000-0"),
        ("1132345678", "(11) 3234-5678"),
        ("11900000000", "(11) 90000-0000"),
        ("(11) 90000-0000", "(11) 90000-0000"),
    ],
)
def test_a_mascara_de_telefone_monta_enquanto_se_digita(digitado, esperado):
    assert formatar_telefone(digitado) == esperado


@pytest.mark.parametrize(
    "guardado",
    ["falar com a Ana", "ramal 12 / recado", "119000000001234"],
)
def test_a_mascara_nao_mexe_no_que_nao_e_telefone(guardado):
    """`Funcionario.telefone` é `String` livre e sempre foi. Abrir o modal para
    trocar o cargo de alguém não pode remontar um recado como se fosse número —
    o dado seria reescrito por um caminho que ninguém pediu."""
    assert formatar_telefone(guardado) == guardado


def test_o_campo_de_telefone_formata_a_digitacao(abrir):
    modal = abrir()

    modal._campo_telefone.setText("11987654321")
    modal._ao_digitar_telefone("11987654321")

    assert modal._campo_telefone.text() == "(11) 98765-4321"


def test_telefone_vazio_vira_none(abrir):
    """`None`, e não `""`: é o que `FuncionarioService._limpar_texto` grava, e o
    painel de detalhe conta com isso para mostrar o travessão."""
    modal = abrir()
    modal._campo_nome.setText("Pedro")

    assert modal.resultado().telefone is None


# ---------------------------------------------------------------------------
# Situação
# ---------------------------------------------------------------------------


def test_o_cadastro_novo_abre_como_ativo(abrir):
    modal = abrir()

    assert modal.resultado().ativo is True
    assert modal._pills[True].property("marcada") is True
    assert modal._pills[False].property("marcada") is False


def test_clicar_em_inativo_troca_a_situacao(abrir):
    modal = abrir()
    modal._campo_nome.setText("Pedro")

    modal._pills[False].click()

    assert modal.resultado().ativo is False
    assert modal._pills[True].property("marcada") is False


def test_a_edicao_abre_com_a_situacao_real(abrir, funcionarios, gerente):
    pessoa = funcionarios.criar("Joana", "Cozinha")
    funcionarios.desativar(pessoa.id)

    modal = abrir(pessoa)

    assert modal.resultado().ativo is False
    assert modal._pills[False].property("marcada") is True


# ---------------------------------------------------------------------------
# Confirmar, cancelar e teclado
# ---------------------------------------------------------------------------


def test_sem_nome_o_botao_de_cadastrar_fica_desligado(abrir):
    """`FuncionarioService._validar_nome` recusa nome vazio. Deixar o botão
    aceso só faria o operador levar o erro de volta na tela de trás."""
    modal = abrir()
    assert modal._botao_confirmar.isEnabled() is False

    modal._campo_nome.setText("  ")
    assert modal._botao_confirmar.isEnabled() is False

    modal._campo_nome.setText("Pedro")
    assert modal._botao_confirmar.isEnabled() is True


def test_enter_cadastra(qapp, abrir):
    modal = abrir()
    modal._campo_nome.setText("Pedro")
    _clicar_cargo(modal, "Garçom")

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Return))

    assert modal.exec() == QDialog.DialogCode.Accepted
    assert modal.resultado().nome == "Pedro"


def test_enter_sem_nome_nao_cadastra(qapp, abrir):
    """O Enter passa pelo mesmo portão do botão: sem nome, não fecha. Sem isto o
    teclado seria um caminho paralelo por onde o cadastro vazio escaparia."""
    modal = abrir()

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Return))
    QTimer.singleShot(30, modal.reject)

    assert modal.exec() == QDialog.DialogCode.Rejected


def test_esc_fecha_o_modal(qapp, abrir):
    modal = abrir()

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Escape))

    assert modal.exec() == QDialog.DialogCode.Rejected


def test_o_nome_sai_sem_espaco_sobrando(abrir):
    modal = abrir()
    modal._campo_nome.setText("  Ana Beatriz  ")

    assert modal.resultado().nome == "Ana Beatriz"


def test_a_edicao_troca_o_titulo_e_o_botao(abrir, funcionarios, gerente):
    """Mesma classe para cadastrar e editar, como o modal antigo já fazia — o
    que muda é o rótulo, e "Cadastrar" numa edição é o tipo de coisa que faz o
    operador achar que criou uma segunda pessoa."""
    pessoa = funcionarios.criar("Joana", "Cozinha")

    assert abrir()._botao_confirmar.text() == "Cadastrar"
    assert abrir().windowTitle() == "Novo funcionário"
    assert abrir(pessoa)._botao_confirmar.text() == "Salvar"
    assert abrir(pessoa).windowTitle() == "Editar funcionário"


# ---------------------------------------------------------------------------
# Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


def test_fechar_solta_as_tabelas_de_widget(qapp, abrir):
    modal = abrir()
    assert modal._cards and modal._pills

    modal.reject()

    assert modal._cards == {}
    assert modal._pills == {}


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    """O escurecedor é filho da JANELA, não do diálogo: `deleteLater()` do
    diálogo não o levaria junto. Dez idas e voltas ao cadastro deixariam dez
    retângulos pretos invisíveis pendurados no `MainWindow`, que vive o processo
    inteiro."""
    pai = QWidget()
    pai.show()

    for _ in range(10):
        modal = FuncionarioDialog(parent=pai)
        modal.show()
        qapp.processEvents()
        modal.reject()
        modal.deleteLater()
    assentar()

    assert pai.window().findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(
    qapp, assentar, funcionarios, pagamentos, auth, caixas_service
):
    """O caminho real: a view de Funcionários como parent, `exec()` de verdade e
    fechamento pelo botão. Se alguém trocar `executar_modal()` por um `.exec()`
    cru em `_criar`/`_editar_id`, é aqui que aparece."""
    view = FuncionariosView(funcionarios, pagamentos, auth, caixas_service)

    for _ in range(30):
        modal = FuncionarioDialog(parent=view)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        modal.deleteLater()
        del modal
    assentar()

    assert view.findChildren(FuncionarioDialog) == []


# ---------------------------------------------------------------------------
# Turno / horário
# ---------------------------------------------------------------------------


def test_a_edicao_abre_com_o_turno_atual_no_campo(abrir, funcionarios, gerente):
    """Quem abre a edição para corrigir a faixa tem que encontrar o rótulo
    inteiro escrito: o campo é livre, e abrir vazio obrigaria a redigitar
    "T2 · Noite ·" só para mexer na hora."""
    pessoa = funcionarios.criar("Caixa Turno - Noite", "Caixa", None, "T2 · Noite · 16h–00h")

    modal = abrir(pessoa)

    assert modal._campo_turno.text() == "T2 · Noite · 16h–00h"


def test_o_turno_editado_sai_no_resultado(abrir, funcionarios, gerente):
    pessoa = funcionarios.criar("Caixa Turno - Noite", "Caixa", None, "T2 · Noite · 16h–00h")
    modal = abrir(pessoa)

    modal._campo_turno.setText("T2 · Noite · 18h–00h")

    assert modal.resultado().turno_horario == "T2 · Noite · 18h–00h"


def test_turno_vazio_vira_none(abrir):
    """`None`, e não `""` — mesmo contrato do telefone."""
    modal = abrir()
    modal._campo_nome.setText("Pedro")

    assert modal.resultado().turno_horario is None


def test_o_cadastro_novo_nao_inventa_turno(abrir, funcionarios, gerente):
    """Só os dois operadores do seed nascem com turno. Um garçom cadastrado no
    balcão não pode sair daqui com a etiqueta do placeholder."""
    modal = abrir()
    modal._campo_nome.setText("Pedro")
    _clicar_cargo(modal, "Garçom")

    assert modal.resultado().turno_horario is None
