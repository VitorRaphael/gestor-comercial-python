"""Limpeza de `QTableWidget` — e a correção do §3.3 que estes testes provocaram.

O §3.3 do `REMASTERIZACAO-V1.md` dizia que `setCellWidget` vaza no PySide6, com
50 aberturas deixando 50 widgets vivos. Escrever o teste de premissa deste
arquivo derrubou o achado: **medido com um laço de eventos rodando de verdade,
não vaza.** A medição original rodou sem laço — e sem laço, um `deleteLater()`
legítimo fica pendente para sempre e se parece exatamente com um vazamento.

O que sobra, e o que estes testes trancam, é **determinismo**: sem o utilitário
o widget antigo continua filho do viewport, na geometria velha, até o Qt passar
recolhendo; com ele, sai da árvore no ato. É a mesma garantia que
`layout_utils` dá aos layouts — e a falta dela já custou dois bugs visuais de
sobreposição neste projeto (§3.7).

`test_a_celula_antiga_so_some_sozinha_no_proximo_ciclo` é o teste de premissa
nesta versão corrigida: enquanto ele passar, os utilitários daqui têm razão de
existir.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem

from gestor_comercial.ui.widgets.tabelas import definir_celula, limpar_tabela

RECARGAS = 20


def _tabela_preenchida(linhas: int, colunas: int = 2) -> QTableWidget:
    tabela = QTableWidget(linhas, colunas)
    for linha in range(linhas):
        tabela.setItem(linha, 0, QTableWidgetItem(f"texto {linha}"))
        tabela.setCellWidget(linha, 1, QLabel(f"widget {linha}"))
    return tabela


def test_a_celula_antiga_so_some_sozinha_no_proximo_ciclo(qapp, assentar):
    """A premissa, sem passar por nenhum utilitário.

    As duas asserções contam a história inteira: **antes** de devolver o
    controle ao Qt os 50 widgets antigos continuam pendurados na tabela; depois,
    o Qt recolhe sozinho e sobra o único que está de fato na célula.

    A janela entre uma coisa e outra é onde mora o risco: é nela que a view
    repopula a tabela e manda repintar.
    """
    tabela = QTableWidget(1, 1)

    for indice in range(50):
        tabela.setCellWidget(0, 0, QLabel(f"célula {indice}"))

    assert len(tabela.findChildren(QLabel)) == 50, (
        "`setCellWidget` passou a destruir o ocupante anterior na hora — se isso "
        "virou verdade, `definir_celula` não tem mais motivo para existir."
    )

    assentar()

    assert len(tabela.findChildren(QLabel)) == 1, (
        "O §3.3 voltou a valer: o Qt não está mais recolhendo as células antigas "
        "sozinho, e aí o utilitário deixa de ser determinismo e vira correção de "
        "vazamento. Remedir antes de mexer na Fase 4."
    )


def test_definir_celula_destroi_o_ocupante_anterior_na_hora(qapp):
    """A contraprova direta do teste acima: o mesmo laço de 50 substituições,
    agora pelo utilitário — e **sem** `assentar()`, porque o ponto é justamente
    não depender do ciclo de eventos."""
    tabela = QTableWidget(1, 1)

    for indice in range(50):
        definir_celula(tabela, 0, 0, QLabel(f"célula {indice}"))

    sobreviventes = tabela.findChildren(QLabel)
    assert len(sobreviventes) == 1
    assert sobreviventes[0].text() == "célula 49"


def test_limpar_tabela_tira_os_widgets_da_arvore_na_hora(qapp):
    tabela = _tabela_preenchida(linhas=10)

    limpar_tabela(tabela)

    assert tabela.rowCount() == 0
    assert tabela.findChildren(QLabel) == []


def test_limpar_tabela_deixa_a_tabela_pronta_para_repopular(qapp):
    """O uso real substitui o par `setRowCount(0)` / `setRowCount(len(dados))`."""
    tabela = _tabela_preenchida(linhas=3)

    limpar_tabela(tabela, linhas=7)

    assert tabela.rowCount() == 7
    assert tabela.item(0, 0) is None
    assert tabela.cellWidget(0, 1) is None


def test_vinte_recargas_nao_aumentam_o_numero_de_widgets(qapp, assentar):
    """O caminho real de toda view com tabela: recarregar não pode crescer."""
    tabela = QTableWidget(0, 2)

    def recarregar() -> None:
        limpar_tabela(tabela, linhas=5)
        for linha in range(5):
            tabela.setItem(linha, 0, QTableWidgetItem(f"texto {linha}"))
            definir_celula(tabela, linha, 1, QLabel(f"widget {linha}"))

    recarregar()
    assentar()
    depois_da_primeira = len(tabela.findChildren(QLabel))

    for _ in range(RECARGAS):
        recarregar()
    assentar()

    assert len(tabela.findChildren(QLabel)) == depois_da_primeira == 5


def test_definir_celula_funciona_na_celula_vazia(qapp):
    tabela = QTableWidget(1, 1)

    definir_celula(tabela, 0, 0, QLabel("primeira"))

    assert tabela.cellWidget(0, 0).text() == "primeira"


def test_limpar_tabela_vazia_nao_faz_nada(qapp):
    tabela = QTableWidget(0, 3)

    limpar_tabela(tabela)

    assert tabela.rowCount() == 0
