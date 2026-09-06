"""Os componentes compartilhados das duas telas de Relatórios — Fase 6.

Antes desta fase, o Histórico Diário e o Dashboard Mensal montavam a barra de
filtro, o painel da gaveta e o painel de atendentes com **oito corpos de função
idênticos** espalhados nos dois arquivos. Nada quebrava; só que corrigir um
rótulo numa tela deixava a outra para trás, e foi exatamente assim que o
`_criar_linha_forma`/`_criar_linha_atendente` nasceu com dois nomes para o
mesmo código.

Este arquivo tem duas metades, e elas provam coisas diferentes:

  * o **contrato dos componentes** (`PainelGaveta`, `PainelAtendentes`,
    `FiltroPeriodoOperador`): o que eles mostram e quando emitem sinal;
  * a **adoção** pelas duas telas reais, mais a varredura que reprova se
    alguém recolar uma cópia — sem ela, a Fase 6 seria verdade só no dia em
    que foi escrita.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton

import gestor_comercial.ui as pacote_ui
from gestor_comercial.domain.enums import CargoFuncionario, PerfilUsuario
from gestor_comercial.services.caixa_service import FechamentoGaveta, ItemRankingAtendente
from gestor_comercial.ui.views.dashboard_mensal_view import DashboardMensalView
from gestor_comercial.ui.views.historico_caixa_view import HistoricoCaixaView
from gestor_comercial.ui.widgets.filtro_periodo_operador import (
    TODOS_OS_OPERADORES,
    FiltroPeriodoOperador,
)
from gestor_comercial.ui.widgets.paineis_relatorio import (
    PainelAtendentes,
    PainelGaveta,
    linha_barra_proporcao,
)


def _gaveta(diferenca: Decimal | None) -> FechamentoGaveta:
    return FechamentoGaveta(
        caixa_id=1,
        identificacao="Turno da Manhã — 06/09",
        total_faturado=Decimal("1234.50"),
        saldo_apurado=Decimal("1200.00"),
        diferenca=diferenca,
    )


def _textos(widget) -> list[str]:
    return [rotulo.text() for rotulo in widget.findChildren(QLabel)]


# ----------------------------------------------------------------------
# Painel da gaveta
# ----------------------------------------------------------------------


def test_a_gaveta_mostra_traco_quando_o_turno_nao_teve_conferencia(qapp):
    """`diferenca is None` é turno sem as duas contagens — e aí não existe
    quebra nem sobra para afirmar. Zero diria que fechou certinho."""
    painel = PainelGaveta()
    painel.preencher(_gaveta(diferenca=None))

    assert "—" in _textos(painel)
    assert "R$ 0,00" not in _textos(painel)


def test_a_gaveta_mostra_a_diferenca_com_sinal(qapp):
    painel = PainelGaveta()
    painel.preencher(_gaveta(diferenca=Decimal("-12.00")))

    textos = _textos(painel)
    assert "-R$ 12,00" in textos
    assert "R$ 1.234,50" in textos
    assert "Turno da Manhã — 06/09" in textos


def test_a_gaveta_nao_guarda_o_valor_do_periodo_anterior(qapp):
    """Trocar o mês no seletor tem que repintar as três linhas: se uma delas
    ficasse para trás, o operador leria o saldo de um período com a diferença
    de outro."""
    painel = PainelGaveta()
    painel.preencher(_gaveta(diferenca=Decimal("5.00")))
    painel.preencher(_gaveta(diferenca=None))

    assert "R$ 5,00" not in _textos(painel)


# ----------------------------------------------------------------------
# Painel de atendentes
# ----------------------------------------------------------------------


def test_o_painel_de_atendentes_avisa_quando_o_periodo_nao_tem_venda_vinculada(qapp):
    painel = PainelAtendentes()
    painel.preencher([])

    assert "Nenhuma venda vinculada a atendente neste período." in _textos(painel)


def test_o_painel_de_atendentes_desenha_uma_barra_por_atendente(qapp):
    painel = PainelAtendentes()
    painel.preencher(
        [
            ItemRankingAtendente("Maria", Decimal("300.00"), Decimal("75")),
            ItemRankingAtendente("Balcão", Decimal("100.00"), Decimal("25")),
        ]
    )

    textos = _textos(painel)
    assert "Maria" in textos and "Balcão" in textos
    assert "R$ 300,00" in textos
    assert [barra.value() for barra in painel.findChildren(QProgressBar)] == [75, 25]


def test_o_painel_de_atendentes_nao_cresce_a_cada_preenchimento(qapp, assentar):
    """A tela é recarregada a cada troca de filtro. Sem a limpeza do layout, as
    linhas do período anterior ficariam empilhadas embaixo das novas — e num
    mês inteiro de idas e vindas isso vira uma tela ilegível numa máquina que
    já é fraca."""
    painel = PainelAtendentes()
    ranking = [ItemRankingAtendente("Maria", Decimal("300.00"), Decimal("100"))]

    painel.preencher(ranking)
    assentar()
    depois_do_primeiro = len(painel.findChildren(QLabel))

    for _ in range(10):
        painel.preencher(ranking)
    assentar()

    assert len(painel.findChildren(QLabel)) == depois_do_primeiro


@pytest.mark.parametrize(
    ("percentual", "esperado"), [("150", 100), ("-20", 0), ("42.6", 42)]
)
def test_a_barra_de_proporcao_fica_dentro_de_zero_e_cem(qapp, percentual, esperado):
    """Percentual fora da faixa é **ignorado** pelo `QProgressBar` — a barra
    ficaria parada no valor anterior em vez de encher. A saturação garante que
    ela sempre diz alguma coisa, mesmo com dado torto vindo do período."""
    bloco = linha_barra_proporcao("Dinheiro", Decimal("10.00"), Decimal(percentual))
    barra = next(
        bloco.itemAt(i).widget()
        for i in range(bloco.count())
        if isinstance(bloco.itemAt(i).widget(), QProgressBar)
    )

    assert barra.value() == esperado


# ----------------------------------------------------------------------
# Filtro de período e operador
# ----------------------------------------------------------------------


def test_o_seletor_de_mes_abre_no_mes_vigente_e_oferece_doze(qapp, funcionarios, gerente):
    """Mesmo sem nenhum fechamento no mês novo, o mês vigente é o primeiro
    item — é o caso normal de abrir o relatório no dia 1º."""
    from datetime import date

    filtro = FiltroPeriodoOperador(funcionarios)
    hoje = date.today()

    assert filtro.ano_mes() == (hoje.year, hoje.month)
    assert filtro._seletor_mes.count() == 12
    # O 12º item é 11 meses atrás, sem repetir nem pular mês na virada do ano.
    assert filtro._seletor_mes.itemData(11) != filtro._seletor_mes.itemData(0)


def test_nenhuma_pilula_vem_destacada_antes_do_primeiro_clique(qapp, funcionarios, gerente):
    """Igual ao seletor de operador do Login. O filtro já funciona como
    "Todos" desde o começo; só o destaque visual espera o clique."""
    filtro = FiltroPeriodoOperador(funcionarios)
    filtro.atualizar_operadores()

    assert filtro.operador_id() is TODOS_OS_OPERADORES
    assert all(
        pilula.property("ativo") is False for pilula in filtro.findChildren(QPushButton)
    )


def test_clicar_na_pilula_troca_o_filtro_e_avisa_a_tela(qapp, funcionarios, auth, gerente):
    operador = _cadastrar_operador_de_caixa(funcionarios, auth, "Joana")
    filtro = FiltroPeriodoOperador(funcionarios)
    filtro.atualizar_operadores()
    avisos: list[int] = []
    filtro.operador_mudou.connect(lambda: avisos.append(1))

    pilula_joana = next(p for p in filtro.findChildren(QPushButton) if p.text() == "Joana")
    pilula_joana.click()

    assert filtro.operador_id() == operador.id
    assert filtro.nome_operador() == "Joana"
    assert avisos == [1]
    # A pílula clicada é a única destacada depois do clique.
    destacadas = [p.text() for p in filtro.findChildren(QPushButton) if p.property("ativo")]
    assert destacadas == ["Joana"]


def test_o_filtro_volta_para_todos_quando_o_operador_selecionado_some(
    qapp, funcionarios, auth, gerente
):
    """Um Caixa desativado entre duas visitas à tela não pode deixar o filtro
    preso num operador que não aparece mais — a tela mostraria "0 turnos" sem
    nenhuma pílula acesa explicando por quê."""
    operador = _cadastrar_operador_de_caixa(funcionarios, auth, "Joana")
    filtro = FiltroPeriodoOperador(funcionarios)
    filtro.atualizar_operadores()
    next(p for p in filtro.findChildren(QPushButton) if p.text() == "Joana").click()
    assert filtro.operador_id() == operador.id

    funcionario = next(f for f in funcionarios.listar_ativos() if f.nome == "Joana")
    funcionarios.desativar(funcionario.id)
    filtro.atualizar_operadores()

    assert filtro.operador_id() is TODOS_OS_OPERADORES
    assert filtro.nome_operador() == "Todos"


def test_a_barra_de_filtro_nao_ganha_margem_ao_virar_widget(qapp, funcionarios, gerente):
    """A barra era um `QHBoxLayout` aninhado, que no Qt já nasce sem margem;
    um layout instalado num widget herda a margem do estilo. Sem zerar, a
    barra desceria alguns pixels e o topo das duas telas mudaria de lugar."""
    filtro = FiltroPeriodoOperador(funcionarios)

    assert filtro.layout().contentsMargins().top() == 0
    assert filtro.layout().contentsMargins().left() == 0


def test_a_barra_de_filtro_tem_regra_de_fundo_transparente():
    """Sem `objectName` + regra no QSS, este `QWidget` herda o
    `QWidget { background: bg_marca }` global e pinta um retângulo por trás
    das pílulas — o mesmo tropeço já documentado em `SecaoCancelamentos`."""
    from gestor_comercial.ui.theme import tokens
    from gestor_comercial.ui.theme.qss_app import construir_qss_app

    assert "QWidget#relatoriosFiltro" in construir_qss_app(tokens.TEMA_ESCURO)


# ----------------------------------------------------------------------
# Adoção pelas telas reais + catraca contra a cópia voltar
# ----------------------------------------------------------------------


@pytest.fixture
def as_duas_telas(qapp, caixas_service, auth, impressao, funcionarios):
    return (
        HistoricoCaixaView(caixas_service, auth, impressao, funcionarios),
        DashboardMensalView(caixas_service, funcionarios),
    )


@pytest.mark.parametrize(
    "componente", [PainelGaveta, PainelAtendentes, FiltroPeriodoOperador]
)
def test_as_duas_telas_de_relatorio_usam_o_mesmo_componente(as_duas_telas, componente):
    for tela in as_duas_telas:
        assert len(tela.findChildren(componente)) == 1, (
            f"{type(tela).__name__} não usa {componente.__name__} — "
            "uma cópia local voltou para dentro da view"
        )


def test_as_duas_telas_leem_o_periodo_do_mesmo_lugar(as_duas_telas):
    """`RelatoriosView` mostra o subtítulo da aba a partir de `periodo_atual()`
    das duas telas. Continua sendo o texto do seletor, agora vindo do filtro."""
    for tela in as_duas_telas:
        assert tela.periodo_atual() == tela._filtro.texto_periodo()
        assert tela.periodo_atual() != ""


_CORPO_MINIMO = 4
_RAIZ_UI = Path(pacote_ui.__file__).parent


def _corpos_de_funcao() -> dict[str, list[str]]:
    """Mapa `corpo normalizado -> onde aparece`, para toda função da camada de
    UI com pelo menos `_CORPO_MINIMO` comandos.

    Compara o corpo pelo `ast.dump`, então o nome da função não conta: era
    justamente assim que `_criar_linha_forma` e `_criar_linha_atendente`
    passavam despercebidas. Docstring sai da conta — comentar duas cópias de
    formas diferentes não as torna diferentes.
    """
    corpos: dict[str, list[str]] = {}
    arquivos = sorted((_RAIZ_UI / "views").glob("*.py")) + sorted(
        (_RAIZ_UI / "widgets").glob("*.py")
    )
    for arquivo in arquivos:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            corpo = [
                comando
                for comando in no.body
                if not (
                    isinstance(comando, ast.Expr) and isinstance(comando.value, ast.Constant)
                )
            ]
            if len(corpo) < _CORPO_MINIMO:
                continue
            chave = ast.dump(ast.Module(body=corpo, type_ignores=[]))
            corpos.setdefault(chave, []).append(f"{arquivo.name}:{no.lineno} {no.name}")
    return corpos


def test_o_varredor_de_copias_realmente_enxerga_as_funcoes():
    """Teste de premissa: varredor que não acha nada passa em tudo. Antes da
    Fase 6 esta varredura acusava 8 cópias entre as duas telas de relatório."""
    corpos = _corpos_de_funcao()

    assert len(corpos) > 150, "o varredor deixou de enxergar a camada de UI"


def test_nenhuma_funcao_da_ui_repete_o_corpo_de_outra():
    duplicadas = [
        " == ".join(ocorrencias)
        for ocorrencias in _corpos_de_funcao().values()
        if len(ocorrencias) > 1
    ]

    assert duplicadas == [], "corpo de função duplicado na camada de UI:\n" + "\n".join(
        duplicadas
    )


def _cadastrar_operador_de_caixa(funcionarios, auth, nome: str):
    """Um Caixa aparece nas pílulas quando existe `Funcionario` ativo com cargo
    Caixa **e** `Usuario` de login de mesmo nome (§ `listar_operadores_caixa`)."""
    funcionarios.criar(nome, CargoFuncionario.CAIXA.value)
    # Sem `login_como`: quem continua logado é o gerente da fixture — trocar o
    # usuário aqui derrubaria a permissão de desativar no teste seguinte.
    return auth.criar_usuario(nome, PerfilUsuario.OPERADOR_CAIXA)
