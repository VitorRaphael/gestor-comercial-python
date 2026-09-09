"""O olho de "Senhas e Acesso": CPF do Dono, valor à mostra, e o caminho de volta.

A tela sempre mostrou `••••••••` e a regra escrita era que ver o valor não
existe como operação. O Vitor pediu o contrário, com uma barreira: um olho ao
lado de cada linha que, mediante o CPF do Dono, mostra o valor real por alguns
segundos.

O que estes testes trancam é a metade que a tela responde por — a regra de quem
pode ver mora no service e é testada em `tests/unit/test_visualizacao_de_segredo.py`:

* **o segredo não fica**: volta à máscara no timer, no segundo clique, ao sair
  da tela e quando aquele segredo é trocado. Uma senha da loja acesa e esquecida
  no monitor do balcão é o defeito que a barreira existe para não criar;
* **um por vez**: revelar outro campo oculta o anterior;
* **o cartão do CPF** conta dígitos com a máscara no lugar e só confirma com os
  onze — e um CPF errado o mantém aberto, com aviso.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from gestor_comercial.services.exceptions import AcessoNegadoError, RegraDeNegocioError
from gestor_comercial.services.loja_config_service import (
    CAMPO_CPF_DONO,
    CAMPO_SENHA_LOGIN,
    CAMPO_SENHA_MASTER,
    CAMPO_SENHA_OPERACIONAL,
    MASCARA,
    SENHA_MASTER_PADRAO,
    SENHA_OPERACIONAL_PADRAO,
)
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView
from gestor_comercial.ui.widgets.cpf_dono_dialog import CpfDonoDialog, formatar_cpf_parcial
from gestor_comercial.ui.widgets.icone_olho import BotaoOlho

CPF_DO_DONO = "12345678901"
CPF_ERRADO = "98765432100"


# ---------------------------------------------------------------------------
# O visor do cartão de CPF
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "digitos, esperado",
    [
        ("", "•••.•••.•••-••"),
        ("1", "1••.•••.•••-••"),
        ("1234", "123.4••.•••-••"),
        ("123456789", "123.456.789-••"),
        ("12345678901", "123.456.789-01"),
    ],
)
def test_a_mascara_do_cpf_e_preenchida_da_esquerda(digitos, esperado):
    assert formatar_cpf_parcial(digitos) == esperado


def test_a_mascara_tem_sempre_o_mesmo_tamanho():
    """Visor que muda de largura durante a digitação faz o dedo errar a tecla."""
    tamanhos = {len(formatar_cpf_parcial("1" * n)) for n in range(12)}
    assert tamanhos == {14}


@pytest.fixture
def cartao(qapp):
    """O cartão com um revelador de mentira, para exercitar só a tela."""
    pai = QWidget()
    dialogo = CpfDonoDialog(
        "Senha Master (Dono)",
        lambda cpf: SENHA_MASTER_PADRAO if cpf == CPF_DO_DONO else _recusar(),
        pai,
    )
    dialogo._pai_de_teste = pai  # segura o parent vivo pelo tempo do teste
    return dialogo


def _recusar():
    raise AcessoNegadoError("CPF do Dono incorreto.")


def _digitar(dialogo: CpfDonoDialog, texto: str) -> None:
    for caractere in texto:
        dialogo.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_0,
                Qt.KeyboardModifier.NoModifier,
                caractere,
            )
        )


def test_o_numpad_da_tela_digita_igual_ao_teclado(cartao):
    """O dedo no balcão, e não o teclado físico atrás do monitor."""
    for rotulo in "123":
        cartao._teclado.teclas[rotulo].click()

    assert cartao._visor.text() == formatar_cpf_parcial("123")


def test_a_tecla_de_dois_zeros_entra_com_dois_digitos(cartao):
    cartao._teclado.teclas["00"].click()

    assert cartao._visor.text() == formatar_cpf_parcial("00")


def test_o_cpf_nao_passa_de_onze_digitos(cartao):
    _digitar(cartao, "123456789012345")

    assert cartao._visor.text() == formatar_cpf_parcial("12345678901")


def test_o_botao_so_liga_com_o_cpf_inteiro(cartao):
    _digitar(cartao, "1234567890")
    assert cartao._botao_confirmar.isEnabled() is False

    _digitar(cartao, "1")
    assert cartao._botao_confirmar.isEnabled() is True


def test_apagar_desliga_o_botao_de_novo(cartao):
    _digitar(cartao, CPF_DO_DONO)
    cartao._teclado.teclas["⌫"].click()

    assert cartao._botao_confirmar.isEnabled() is False


def test_o_cpf_certo_confirma_e_guarda_o_valor(cartao):
    _digitar(cartao, CPF_DO_DONO)
    cartao._confirmar()

    assert cartao.result() == cartao.DialogCode.Accepted
    assert cartao.resultado() == SENHA_MASTER_PADRAO


def test_o_cpf_errado_nao_fecha_o_cartao(cartao):
    _digitar(cartao, CPF_ERRADO)
    cartao._confirmar()

    assert cartao.result() != cartao.DialogCode.Accepted
    assert cartao._instrucao.property("estado") == "erro"
    assert "INCORRETO" in cartao._instrucao.text()
    assert cartao._visor.text() == formatar_cpf_parcial(""), "o visor tem que limpar"


def test_digitar_de_novo_apaga_o_aviso_de_erro(cartao):
    _digitar(cartao, CPF_ERRADO)
    cartao._confirmar()

    _digitar(cartao, "1")

    assert cartao._instrucao.property("estado") == "normal"
    assert cartao._timer_erro.isActive() is False


def test_o_enter_confirma(cartao):
    _digitar(cartao, CPF_DO_DONO)
    cartao.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )

    assert cartao.result() == cartao.DialogCode.Accepted


def test_o_cpf_sai_da_memoria_no_fechamento(cartao):
    _digitar(cartao, CPF_DO_DONO)
    cartao.reject()

    assert cartao._digitos == ""
    assert cartao._timer_erro.isActive() is False
    assert cartao._teclado.teclas == {}


def test_o_resultado_sobrevive_ao_fechamento(cartao):
    """`resultado()` é lido DEPOIS do `exec()` — o oposto do modal de PIN, e de
    propósito (mesmo critério do §9.6)."""
    _digitar(cartao, CPF_DO_DONO)
    cartao._confirmar()

    assert cartao.resultado() == SENHA_MASTER_PADRAO


# ---------------------------------------------------------------------------
# A tela de Configurações
# ---------------------------------------------------------------------------


@pytest.fixture
def tela(qapp, auth):
    return ConfiguracoesView(auth)


@pytest.fixture
def tela_com_cpf(qapp, auth):
    auth.loja_config.definir_ou_alterar_cpf_dono(None, CPF_DO_DONO)
    return ConfiguracoesView(auth)


def _revelar(qapp, tela, campo, cpf):
    """Aperta o olho e opera o cartão de CPF que abrir, de verdade."""
    visto = []

    def operar() -> None:
        abertos = tela.findChildren(CpfDonoDialog)
        if not abertos:
            return
        cartao = abertos[0]
        visto.append(cartao)
        _digitar(cartao, cpf)
        cartao._confirmar()
        if cartao.result() != cartao.DialogCode.Accepted:
            cartao.reject()

    QTimer.singleShot(0, operar)
    tela._olhos[campo].click()
    qapp.processEvents()
    return bool(visto)


def test_toda_linha_de_segredo_tem_um_olho(tela):
    olhos = tela.findChildren(BotaoOlho)

    assert len(olhos) == 4
    assert set(tela._olhos) == {
        CAMPO_SENHA_LOGIN,
        CAMPO_SENHA_OPERACIONAL,
        CAMPO_SENHA_MASTER,
        CAMPO_CPF_DONO,
    }


def test_a_tela_comeca_toda_mascarada(tela_com_cpf):
    for campo in (CAMPO_SENHA_LOGIN, CAMPO_SENHA_OPERACIONAL, CAMPO_SENHA_MASTER):
        assert tela_com_cpf._valores[campo].text() == MASCARA


def test_sem_cpf_cadastrado_o_olho_nao_abre_cartao_nenhum(qapp, tela):
    """Abrir um teclado que só pode terminar em erro é pior que a mensagem."""
    assert _revelar(qapp, tela, CAMPO_SENHA_MASTER, CPF_DO_DONO) is False
    assert "Cadastre o CPF do Dono primeiro" in tela._label_erro.text()
    assert tela._valores[CAMPO_SENHA_MASTER].text() == MASCARA


def test_o_cpf_certo_revela_o_valor_na_linha(qapp, tela_com_cpf):
    assert _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO) is True

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == SENHA_MASTER_PADRAO
    assert tela_com_cpf._olhos[CAMPO_SENHA_MASTER].property("revelado") is True
    assert tela_com_cpf._timer_revelado.isActive() is True


def test_o_cpf_errado_nao_revela_nada(qapp, tela_com_cpf):
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_ERRADO)

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA
    assert tela_com_cpf._campo_revelado is None


def test_o_segundo_clique_no_mesmo_olho_oculta(qapp, tela_com_cpf):
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO)

    tela_com_cpf._olhos[CAMPO_SENHA_MASTER].click()
    qapp.processEvents()

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA
    assert tela_com_cpf._timer_revelado.isActive() is False


def test_o_timer_devolve_a_mascara(qapp, tela_com_cpf):
    """O disparo do timer, sem esperar os oito segundos de verdade."""
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO)

    tela_com_cpf._timer_revelado.timeout.emit()

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA
    assert tela_com_cpf._olhos[CAMPO_SENHA_MASTER].property("revelado") is False


def test_sair_da_tela_oculta_o_que_estava_a_mostra(qapp, tela_com_cpf):
    """Sem isto, a senha ficaria acesa atrás de qualquer outra página."""
    tela_com_cpf.show()
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO)

    tela_com_cpf.hide()
    qapp.processEvents()

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA
    assert tela_com_cpf._timer_revelado.isActive() is False


def test_revelar_outro_campo_oculta_o_anterior(qapp, tela_com_cpf):
    """Duas senhas da loja acesas ao mesmo tempo é o oposto de uma barreira."""
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO)
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_OPERACIONAL, CPF_DO_DONO)

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA
    assert tela_com_cpf._valores[CAMPO_SENHA_OPERACIONAL].text() == SENHA_OPERACIONAL_PADRAO
    assert tela_com_cpf._campo_revelado == CAMPO_SENHA_OPERACIONAL


def test_trocar_a_senha_oculta_o_valor_antigo(qapp, tela_com_cpf, auth):
    """Depois da troca, o que está na tela é o valor ANTERIOR."""
    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO)

    auth.loja_config.alterar_senha_master(CPF_DO_DONO, "778899")
    tela_com_cpf._atualizar_secao_senhas()

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA


def test_o_cpf_sem_cadastro_mostra_nao_cadastrado_ao_ocultar(qapp, tela):
    """A linha do CPF tem dois estados de máscara, e voltar do revelado não
    pode trocar "Não cadastrado" por `••••••••`."""
    assert tela._valores[CAMPO_CPF_DONO].text() == "Não cadastrado"

    tela.ocultar_revelado()

    assert tela._valores[CAMPO_CPF_DONO].text() == "Não cadastrado"


def test_o_cpf_do_dono_tambem_e_revelavel(qapp, tela_com_cpf):
    _revelar(qapp, tela_com_cpf, CAMPO_CPF_DONO, CPF_DO_DONO)

    assert tela_com_cpf._valores[CAMPO_CPF_DONO].text() == CPF_DO_DONO


def test_o_erro_de_campo_sem_copia_nao_derruba_a_tela(qapp, tela_com_cpf, uow, auth):
    """Banco antigo com a senha trocada antes das colunas novas: o cartão fica
    aberto com a instrução, e a linha continua mascarada."""
    config = auth.loja_config.obter_ou_criar()
    config.senha_master_cifrada = None
    uow.commit()

    _revelar(qapp, tela_com_cpf, CAMPO_SENHA_MASTER, CPF_DO_DONO)

    assert tela_com_cpf._valores[CAMPO_SENHA_MASTER].text() == MASCARA


def test_o_service_e_quem_decide_e_nao_a_tela(tela_com_cpf, auth):
    """A tela não compara CPF nenhum: ela entrega os dígitos e obedece."""
    with pytest.raises((AcessoNegadoError, RegraDeNegocioError)):
        auth.loja_config.revelar(CAMPO_SENHA_MASTER, CPF_ERRADO)
