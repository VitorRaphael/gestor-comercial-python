"""Excluir um funcionário passa a exigir a Senha Master digitada na hora.

Antes era um `QMessageBox.question` de Sim/Não. `FuncionarioService.excluir` já
exigia gerente (`exigir_gerente`), mas essa exigência é satisfeita pela
**sessão**: quem abriu o turno de manhã e deixou o programa aberto no balcão
autoriza qualquer exclusão que alguém clicar à tarde. Um Sim/Não em cima disso
separa a exclusão de um clique distraído por outro clique — e a linha some do
banco de vez.

A barreira agora é o Nível 3 da cascata (§3.13), a mesma credencial que abre a
Central de Loja: reautenticação na hora, para uma ação física e irreversível.

Os testes da view abrem o modal **de verdade** — `executar_modal` roda, `exec()`
roda, o service grava e o banco responde. Um dublê do diálogo provaria só que o
teste sabe chamar o service.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from gestor_comercial.services.exceptions import NaoAutorizadoError
from gestor_comercial.ui.views.funcionarios_view import FuncionariosView
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog

from tests.conftest import PIN_LOGIN, PIN_MASTER, PIN_OPERACIONAL

NOME = "Maria Entregas"


def _teclar(dialogo: PinPadDialog, texto: str) -> None:
    for caractere in texto:
        dialogo.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_0,
                Qt.KeyboardModifier.NoModifier,
                caractere,
            )
        )


# ---------------------------------------------------------------------------
# O construtor nomeado
# ---------------------------------------------------------------------------


@pytest.fixture
def modal(qapp, auth):
    pai = QWidget()
    dialogo = PinPadDialog.para_exclusao(auth, NOME, pai)
    dialogo._pai_de_teste = pai  # segura o parent vivo pelo tempo do teste
    return dialogo


def test_o_cartao_diz_o_que_vai_ser_apagado(modal):
    """A pergunta com o nome próprio do registro, e não só "confirmar?"."""
    assert modal._label_mensagem.text() == (
        f"Você deseja confirmar a ação de apagar {NOME}?"
    )


def test_o_titulo_e_confirmar_exclusao(modal):
    assert modal.windowTitle() == "Confirmar Exclusão"


def test_a_senha_master_confirma(modal, gerente):
    _teclar(modal, PIN_MASTER)
    modal._confirmar()

    assert modal.result() == modal.DialogCode.Accepted


@pytest.mark.parametrize("senha", [PIN_OPERACIONAL, PIN_LOGIN, "000000"])
def test_nenhuma_credencial_abaixo_da_master_confirma(modal, gerente, senha):
    """Nível 3 não herda de baixo para cima: a Senha Operacional abre o Caixa e
    não pode apagar um cadastro."""
    _teclar(modal, senha)
    modal._confirmar()

    assert modal.result() != modal.DialogCode.Accepted


def test_pin_errado_nao_fecha_o_modal(modal, gerente):
    """Feedback visual e o cartão de pé — quem errou tenta de novo na hora."""
    _teclar(modal, "999999")
    modal._confirmar()

    assert modal.isVisible() is False or modal.result() != modal.DialogCode.Accepted
    assert modal._label_instrucao.property("estado") == "erro"
    assert modal._pin == "", "o PIN recusado tem que sair do campo"


def test_o_validador_e_o_do_nivel_3(modal, auth, gerente):
    """Amarra o construtor à cascata: se alguém trocar por `validar_pin_gerente`
    (Nível 2), a Senha Operacional passaria a apagar cadastro."""
    assert modal._validar == auth.validar_pin_dono

    with pytest.raises(NaoAutorizadoError):
        modal._validar(PIN_OPERACIONAL)


def test_o_pin_sai_da_memoria_no_fechamento(modal, gerente):
    _teclar(modal, PIN_MASTER)
    modal.reject()

    assert modal._pin == ""


def test_os_outros_usos_do_pin_nao_ganharam_mensagem(qapp, auth):
    """A faixa vermelha é só da exclusão: "Caixa" e "Área da Loja" são
    elevações de acesso, e ali o título já diz tudo."""
    assert not hasattr(PinPadDialog.para_caixa(auth), "_label_mensagem")
    assert not hasattr(PinPadDialog.para_loja(auth), "_label_mensagem")


# ---------------------------------------------------------------------------
# O caminho real — a tela, o modal, o service e o banco
# ---------------------------------------------------------------------------


@pytest.fixture
def tela(qapp, funcionarios, pagamentos, auth, caixas_service, gerente):
    return FuncionariosView(funcionarios, pagamentos, auth, caixas_service)


def _excluir_pela_tela(qapp, tela, funcionario_id, senha, confirmar=True):
    """Aperta Excluir e opera o cartão de PIN que abrir, de verdade.

    Devolve `True` se um `PinPadDialog` chegou a existir. Sem esse retorno, um
    dia em que a barreira sumisse (exclusão direta, sem modal) todos os testes
    daqui passariam verdes: o `operar` não acharia diálogo nenhum, o estouro
    morreria dentro do slot do `QTimer` e a exclusão aconteceria assim mesmo.
    """
    visto = []

    def operar() -> None:
        abertos = tela.findChildren(PinPadDialog)
        if not abertos:
            return
        modal = abertos[0]
        visto.append(modal)
        if not confirmar:
            modal.reject()
            return
        _teclar(modal, senha)
        modal._confirmar()
        if modal.result() != modal.DialogCode.Accepted:
            modal.reject()  # PIN recusado: o teste não pode ficar preso no exec()

    QTimer.singleShot(0, operar)
    tela._excluir_id(funcionario_id)
    qapp.processEvents()
    return bool(visto)


def test_o_botao_excluir_abre_o_cartao_de_pin(qapp, tela, funcionarios, uow):
    """Premissa de todos os outros: sem o cartão, "apagou" não prova barreira."""
    alvo = funcionarios.criar(NOME, "Entregador")
    tela.atualizar()

    assert _excluir_pela_tela(qapp, tela, alvo.id, PIN_MASTER, confirmar=False) is True


def test_a_senha_master_apaga_de_verdade(qapp, tela, funcionarios, uow):
    alvo = funcionarios.criar(NOME, "Entregador")
    tela.atualizar()

    assert _excluir_pela_tela(qapp, tela, alvo.id, PIN_MASTER) is True

    assert uow.funcionarios.buscar_por_id(alvo.id) is None
    assert all(f.nome != NOME for f in funcionarios.listar_todos())


def test_cancelar_o_pin_nao_apaga_nada(qapp, tela, funcionarios, uow):
    alvo = funcionarios.criar(NOME, "Entregador")
    tela.atualizar()

    _excluir_pela_tela(qapp, tela, alvo.id, PIN_MASTER, confirmar=False)

    assert uow.funcionarios.buscar_por_id(alvo.id) is not None


def test_senha_errada_nao_apaga_nada(qapp, tela, funcionarios, uow):
    alvo = funcionarios.criar(NOME, "Entregador")
    tela.atualizar()

    _excluir_pela_tela(qapp, tela, alvo.id, PIN_OPERACIONAL)

    assert uow.funcionarios.buscar_por_id(alvo.id) is not None


def test_a_tela_se_atualiza_depois_de_apagar(qapp, tela, funcionarios):
    """A linha some da lista sem precisar de outro clique."""
    alvo = funcionarios.criar(NOME, "Entregador")
    tela.atualizar()
    antes = tela._lista.count()

    _excluir_pela_tela(qapp, tela, alvo.id, PIN_MASTER)

    assert tela._lista.count() == antes - 1


def test_o_erro_do_service_aparece_na_tela(qapp, tela, funcionarios, mesa, caixa_aberto, uow, auth):
    """PIN certo e exclusão recusada por regra: a mensagem tem que chegar ao
    operador em vez de a tela ficar como se nada tivesse acontecido."""
    from gestor_comercial.services.comanda_service import ComandaService

    alvo = funcionarios.criar(NOME, "Entregador")
    comandas = ComandaService(uow, auth)
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.definir_atendente(comanda.id, alvo.id)
    tela.atualizar()

    _excluir_pela_tela(qapp, tela, alvo.id, PIN_MASTER)

    assert "histórico" in tela._label_erro.text()
    assert uow.funcionarios.buscar_por_id(alvo.id) is not None
