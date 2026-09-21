"""O nome do turno é o mesmo em todo cabeçalho, e muda em todos de uma vez.

O defeito relatado: o operador "Caixa Turno - Noite" abriu o caixa às 17:36, e
os cabeçalhos diziam "Caixa Turno - Tarde" (a regra de hora), enquanto as telas
de venda diziam o operador. E cada cabeçalho só se atualizava na próxima
navegação — abrir o turno, fechar o turno ou renomear o operador em
Funcionários deixava nomes diferentes na tela ao mesmo tempo.

Agora há uma fonte (`IdentidadeDoTurno`), avisada por quem muda o que ela lê
(login, `CaixaView.turno_alterado`, `FuncionariosView.cadastro_alterado`), e um
só lugar que escreve nos cinco cabeçalhos (`MainWindow._mostrar_identidade`).
Os testes abaixo operam as telas de verdade — o modal abre, o `exec()` roda — e
nunca navegam: se um rótulo só ficar certo depois de um clique na sidebar, é
aqui que falha.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.services.dinheiro import dinheiro
from gestor_comercial.ui.main_window import MainWindow
from gestor_comercial.ui.rotulo_identidade import IdentidadeDoTurno
from gestor_comercial.ui.widgets.abertura_caixa_dialog import AberturaCaixaDialog
from gestor_comercial.ui.widgets.fechamento_caixa_dialog import FechamentoCaixaDialog
from gestor_comercial.ui.widgets.funcionario_dialog import FuncionarioDialog
from tests.conftest import PIN_GERENTE

NOITE = "Caixa Turno - Noite"


@pytest.fixture
def operador_da_noite(auth, funcionarios, gerente):
    """O par do seed — login e funcionário com o mesmo nome — e a sessão dele."""
    login = auth.criar_usuario(NOITE, PerfilUsuario.GERENTE)
    pessoa = funcionarios.criar(NOITE, "Caixa", None, "T2 · Noite · 17h–01h")
    auth.login_como(login.id, PIN_GERENTE)
    return login, pessoa


@pytest.fixture
def janela(qapp, auth, comandas, cardapio, caixas_service, pagamentos, impressao, funcionarios):
    tela = MainWindow(auth, comandas, cardapio, caixas_service, pagamentos, impressao, funcionarios)
    yield tela
    tela.deleteLater()


def _entrar(janela: MainWindow, usuario) -> None:
    """O caminho da tela de login: o sinal que ela emite depois do PIN certo."""
    janela._login_view.autenticado.emit(usuario)


def _cabecalhos(janela: MainWindow) -> dict[str, str]:
    return {
        "barra do shell": janela._label_usuario.text().upper(),
        "Central de Loja": janela._loja_hub_view._breadcrumb.text(),
        "Impressoras": janela._impressoras_view._breadcrumb.text(),
        "Relatórios": janela._relatorios_view._label_breadcrumb.text(),
        "Funcionários": janela._funcionarios_view._label_eyebrow.text(),
    }


def _todos_dizem(janela: MainWindow, esperado: str) -> None:
    cabecalhos = _cabecalhos(janela)
    divergentes = {onde: texto for onde, texto in cabecalhos.items() if texto != esperado.upper()}
    assert not divergentes, f"esperado {esperado.upper()!r} em todos: {cabecalhos}"


TETO_DO_MODAL_MS = 3000


def _operar_modal(qapp, view, tipo, gesto, abrir) -> None:
    """Abre um modal pela tela (`abrir`) e faz o `gesto` nele, de dentro do `exec()`.

    **Tem teto**, pelo mesmo motivo do helper de `test_impressoras_cadastro`: um
    modal que não fecha prenderia o `exec()` para sempre, e a suíte travaria em
    vez de reprovar — foi o que a checagem por mutação destes testes encontrou.
    O vigia é filho da tela e é parado na volta, para não disparar no teste
    seguinte.
    """
    erros: list[str] = []

    def aberto():
        return next((m for m in view.findChildren(tipo) if m.isVisible()), None)

    def agir() -> None:
        modal = aberto()
        if modal is None:
            erros.append(f"nenhum {tipo.__name__} abriu")
            return
        try:
            gesto(modal)
        except Exception as erro:  # pragma: no cover - só aparece quando o teste quebra
            erros.append(repr(erro))
            modal.reject()

    def vigiar() -> None:
        modal = aberto()
        if modal is not None:
            erros.append(f"{tipo.__name__} continuou aberto depois de {TETO_DO_MODAL_MS}ms")
            modal.reject()

    vigia = QTimer(view)
    vigia.setSingleShot(True)
    vigia.setInterval(TETO_DO_MODAL_MS)
    vigia.timeout.connect(vigiar)
    vigia.start()
    QTimer.singleShot(0, agir)
    try:
        abrir()
        qapp.processEvents()
    finally:
        vigia.stop()
        vigia.timeout.disconnect(vigiar)
        vigia.deleteLater()
    assert not erros, erros


def _abrir_caixa_pela_tela(qapp, janela: MainWindow) -> None:
    """O botão "Abrir caixa" com o modal de verdade; R$ 0,00 é fundo legítimo."""
    view = janela._caixa_view
    view.atualizar()
    _operar_modal(qapp, view, AberturaCaixaDialog, lambda m: m.accept(), view._botao_abrir.click)


def _fechar_caixa_pela_tela(qapp, janela: MainWindow) -> None:
    view = janela._caixa_view
    view.atualizar()
    _operar_modal(
        qapp, view, FechamentoCaixaDialog, lambda m: m.accept(), view._botao_fechar.click
    )


def _renomear_pela_tela(qapp, janela: MainWindow, funcionario_id: int, nome: str) -> None:
    """O "Editar" de Funcionários com o modal de verdade, trocando só o nome."""
    view = janela._funcionarios_view
    view.atualizar()

    def trocar_o_nome(modal: FuncionarioDialog) -> None:
        modal._campo_nome.setText(nome)
        modal.accept()

    _operar_modal(
        qapp, view, FuncionarioDialog, trocar_o_nome, lambda: view._editar_id(funcionario_id)
    )


# ---------------------------------------------------------------------------
# A fonte
# ---------------------------------------------------------------------------


def test_recalcular_sem_mudanca_nao_avisa_ninguem(qapp, auth, caixas_service, gerente):
    """Recalcular custa uma consulta; repintar cinco cabeçalhos sem motivo, não."""
    identidade = IdentidadeDoTurno(auth, caixas_service)
    avisos: list[str] = []
    identidade.rotulo_mudou.connect(avisos.append)

    identidade.recalcular()
    identidade.recalcular()

    assert avisos == ["Gerente · Gerente"]
    assert identidade.rotulo == "Gerente · Gerente"


# ---------------------------------------------------------------------------
# Os cinco cabeçalhos, em cada momento em que o nome muda
# ---------------------------------------------------------------------------


def test_ao_entrar_todos_os_cabecalhos_dizem_o_mesmo(janela, operador_da_noite):
    login, _pessoa = operador_da_noite

    _entrar(janela, login)

    _todos_dizem(janela, f"{NOITE} · Gerente")


def test_abrir_o_caixa_renomeia_todos_os_cabecalhos_sem_navegar(
    qapp, janela, operador_da_noite, caixas_service
):
    """O defeito: o turno do operador da Noite aparecia como "Tarde" no
    cabeçalho — e só depois de navegar."""
    login, _pessoa = operador_da_noite
    _entrar(janela, login)
    pagina_antes = janela._paginas.currentWidget()

    _abrir_caixa_pela_tela(qapp, janela)

    assert caixas_service.buscar_aberto().aberto_por_id == login.id
    assert janela._paginas.currentWidget() is pagina_antes, "o teste não pode navegar"
    _todos_dizem(janela, NOITE)
    assert janela._caixa_view._label_titulo.text() == NOITE


def test_fechar_o_caixa_devolve_os_cabecalhos_ao_operador_sem_navegar(
    qapp, janela, operador_da_noite, caixas_service
):
    login, _pessoa = operador_da_noite
    _entrar(janela, login)
    _abrir_caixa_pela_tela(qapp, janela)
    _todos_dizem(janela, NOITE)

    _fechar_caixa_pela_tela(qapp, janela)

    assert janela._caixa_view._caixa_id is None, "o caixa não fechou"
    _todos_dizem(janela, f"{NOITE} · Gerente")


def test_renomear_em_funcionarios_renomeia_o_turno_em_todos_os_cabecalhos(
    qapp, janela, operador_da_noite, caixas_service
):
    """"Deve ser o que eu editar e deixar editado": o nome escrito em
    Funcionários vira o nome do turno aberto, em todo cabeçalho, na hora."""
    login, pessoa = operador_da_noite
    _entrar(janela, login)
    _abrir_caixa_pela_tela(qapp, janela)

    _renomear_pela_tela(qapp, janela, pessoa.id, "Caixa")

    _todos_dizem(janela, "Caixa")
    assert caixas_service.identificacao_turno(caixas_service.buscar_aberto()) == "Caixa"


def test_o_nome_editado_chega_ao_dropdown_do_login(qapp, janela, operador_da_noite):
    """O login é o mesmo cadastro: quem sai e volta escolhe "Caixa", e o nome
    antigo não sobra na lista."""
    login, pessoa = operador_da_noite
    _entrar(janela, login)

    _renomear_pela_tela(qapp, janela, pessoa.id, "Caixa")
    janela._deslogar_agora()
    janela._login_view._carregar_usuarios()

    combo = janela._login_view._combo_usuario
    nomes = [combo.itemText(indice) for indice in range(combo.count())]
    assert "Caixa" in nomes
    assert NOITE not in nomes


def test_sair_apaga_o_nome_de_todos_os_cabecalhos(qapp, janela, operador_da_noite):
    """O nome de quem saiu não fica esperando o próximo operador."""
    login, _pessoa = operador_da_noite
    _entrar(janela, login)
    _abrir_caixa_pela_tela(qapp, janela)

    janela._deslogar_agora()

    _todos_dizem(janela, "")


def test_quem_entra_com_o_turno_de_outro_aberto_ve_o_nome_do_turno(
    qapp, janela, auth, operador_da_noite, gerente
):
    """O turno se chama como quem o ABRIU: outro operador entrando no meio
    dele não o renomeia."""
    login, _pessoa = operador_da_noite
    _entrar(janela, login)
    _abrir_caixa_pela_tela(qapp, janela)
    janela._deslogar_agora()

    auth.login_como(gerente.id, PIN_GERENTE)
    _entrar(janela, gerente)

    _todos_dizem(janela, NOITE)


def test_um_turno_aberto_as_17h36_nao_vira_tarde(
    qapp, janela, uow, operador_da_noite, caixas_service
):
    """O horário exato do banco de trabalho do Vitor: 17:36 é "Tarde" na regra
    de hora, que já não nomeia turno com operador."""
    from datetime import datetime

    login, _pessoa = operador_da_noite
    caixa = caixas_service.abrir(dinheiro("0.00"))
    caixa.aberto_em = datetime(2026, 9, 19, 17, 36)
    uow.commit()

    _entrar(janela, login)

    _todos_dizem(janela, NOITE)
