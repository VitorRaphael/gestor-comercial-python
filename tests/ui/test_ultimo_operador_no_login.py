"""O dropdown da tela de login abre no último operador que entrou.

Antes ele abria sempre no primeiro item da lista, que é só quem tem o nome mais
próximo do começo do alfabeto (`UsuarioRepository.listar_ativos` ordena por
nome). No food truck o mesmo turno abre o programa dezenas de vezes seguidas, e
escolher o operador de novo a cada abertura é um passo que só existe para ser
esquecido — e esquecer aqui grava a venda no `aberto_por_id` errado.

A memória é uma linha em `preferencias` (`ultimo_operador_id`), gravada quando
o login dá certo. Estes testes cobrem os dois lados: o `AuthService` que grava e
a `LoginView` que lê — inclusive quando o que está guardado aponta para alguém
que não está mais ativo.

O outro assunto aqui é a lista ficar viva: quem exclui ou desativa um operador
faz isso na tela de Funcionários, com o login escondido atrás, e o dropdown
precisa refletir isso no logout seguinte sem exigir que o programa seja fechado.
"""

from __future__ import annotations

import pytest

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.repository.preferencia_repository import ULTIMO_OPERADOR_ID
from gestor_comercial.ui.views.login_view import LoginView

from tests.conftest import PIN_LOGIN

MANHA = "Caixa Turno - Manhã"
NOITE = "Caixa Turno - Noite"


@pytest.fixture
def dois_turnos(uow, auth):
    """Os dois operadores como o app os tem, em ordem alfabética no dropdown.

    O login no meio é obrigatório e não é detalhe: `criar_usuario` só dispensa
    gerente no bootstrap do primeiro (§3.1). Como esse login gravaria uma
    memória de operador que os testes ainda não pediram, a preferência é
    apagada no fim — a fixture entrega um terminal que nunca viu ninguém entrar.
    """
    manha = auth.criar_usuario(MANHA, PerfilUsuario.GERENTE)
    auth.login_como(manha.id, PIN_LOGIN)
    noite = auth.criar_usuario(NOITE, PerfilUsuario.GERENTE)

    uow.preferencias.remover_chave(ULTIMO_OPERADOR_ID)
    uow.commit()
    return manha, noite


def _nomes(tela: LoginView) -> list[str]:
    combo = tela._combo_usuario
    return [combo.itemText(i) for i in range(combo.count())]


# ----------------------------------------------------------------------
# O service, que grava
# ----------------------------------------------------------------------


def test_o_login_grava_quem_entrou(uow, auth, dois_turnos):
    _, noite = dois_turnos

    auth.login_como(noite.id, PIN_LOGIN)

    assert auth.ultimo_operador_id() == noite.id
    assert uow.preferencias.obter(ULTIMO_OPERADOR_ID) == str(noite.id)


def test_pin_errado_nao_grava_ninguem(auth, dois_turnos):
    """A tela mostra o último que ENTROU, não o último que tentou."""
    _, noite = dois_turnos

    with pytest.raises(Exception):
        auth.login_como(noite.id, "00000000")

    assert auth.ultimo_operador_id() is None


def test_o_segundo_login_substitui_o_primeiro(auth, dois_turnos):
    manha, noite = dois_turnos

    auth.login_como(noite.id, PIN_LOGIN)
    auth.login_como(manha.id, PIN_LOGIN)

    assert auth.ultimo_operador_id() == manha.id


def test_valor_ilegivel_no_banco_e_tratado_como_ausencia(uow, auth, dois_turnos):
    """O único jeito de existir uma linha assim é edição manual do banco, e a
    resposta certa é a tela cair no padrão dela — não estourar no boot."""
    uow.preferencias.definir(ULTIMO_OPERADOR_ID, "nada disso")
    uow.commit()

    assert auth.ultimo_operador_id() is None


# ----------------------------------------------------------------------
# A tela, que lê
# ----------------------------------------------------------------------


def test_sem_historico_o_dropdown_abre_no_primeiro(qapp, auth, dois_turnos):
    """Primeiro boot da instalação: não há o que lembrar."""
    tela = LoginView(auth)

    assert tela._combo_usuario.currentText() == MANHA


def test_o_dropdown_abre_no_ultimo_operador(qapp, auth, dois_turnos):
    _, noite = dois_turnos
    auth.login_como(noite.id, PIN_LOGIN)

    tela = LoginView(auth)

    assert tela._combo_usuario.currentText() == NOITE, (
        "o dropdown voltou a abrir no primeiro da lista"
    )


def test_o_dropdown_guarda_o_id_e_nao_a_instancia(qapp, auth, dois_turnos):
    """Instância de `Usuario` expira a cada `commit` do app, e guardá-la no
    widget prende no dropdown uma linha do banco que pode já não existir."""
    manha, _ = dois_turnos
    tela = LoginView(auth)

    assert tela._combo_usuario.itemData(0) == manha.id


def test_o_ultimo_operador_desativado_cai_no_primeiro(qapp, auth, dois_turnos):
    """O que está guardado é só um id: quem confere se aquele operador ainda
    está no dropdown é a tela, contra a lista que ela mesma carregou."""
    manha, noite = dois_turnos
    auth.login_como(noite.id, PIN_LOGIN)
    auth.desativar_usuario(noite.id)

    tela = LoginView(auth)

    assert _nomes(tela) == [MANHA]
    assert tela._combo_usuario.currentText() == MANHA


def test_reabrir_a_tela_recarrega_a_lista(qapp, auth, dois_turnos):
    """O operador desativado no shell autenticado tem que sumir daqui no
    logout seguinte, sem precisar fechar o programa."""
    manha, noite = dois_turnos
    tela = LoginView(auth)
    assert _nomes(tela) == [MANHA, NOITE], "premissa: os dois começam na lista"

    auth.desativar_usuario(noite.id)
    tela.show()  # é o que acontece a cada logout
    qapp.processEvents()

    assert _nomes(tela) == [MANHA]


def test_reabrir_a_tela_nao_duplica_os_itens(qapp, auth, dois_turnos):
    tela = LoginView(auth)

    for _ in range(3):
        tela.show()
        qapp.processEvents()

    assert _nomes(tela) == [MANHA, NOITE]


def test_a_tela_sem_operador_nenhum_avisa_e_desliga_os_controles(qapp, auth):
    tela = LoginView(auth)

    assert tela._combo_usuario.isEnabled() is False
    assert tela._botao_confirmar.isEnabled() is False
    assert "Nenhum usuário" in tela._label_erro.text()


def test_o_primeiro_operador_cadastrado_religa_os_controles(qapp, auth, dois_turnos):
    """A tela nasce vazia num banco sem usuário; quando algum aparece, o
    recarregamento tem que desfazer o estado desligado."""
    tela = LoginView(auth)
    tela._combo_usuario.setEnabled(False)
    tela._botao_confirmar.setEnabled(False)

    tela.show()
    qapp.processEvents()

    assert tela._combo_usuario.isEnabled() is True
    assert tela._botao_confirmar.isEnabled() is True
