"""Os utilitários da Fase 5 continuam sendo usados por TODAS as telas.

Ver §3.2 (modais) e §3.3 (tabelas).

Os testes de `test_modais.py` provam que `executar_modal()` funciona. Este aqui
prova a outra metade, que é a que apodrece com o tempo: que os pontos de
chamada do app realmente passam por eles. Sem esta varredura, a Fase 5 seria
verdade só no dia em que foi escrita — o próximo `modal.exec()` ou
`setCellWidget` colado numa tela nova entraria sem ninguém notar.

A regra é a do §3.2, escrita como código:

  * `X.exec()` sem argumento é abertura de diálogo, e tem que virar
    `executar_modal(X)`;
  * a única exceção é o modal **reaproveitado** entre voltas de um `while`
    (`cardapio_view.criar`/`editar`), onde `executar_modal` destruiria o
    diálogo já na primeira iteração. Lá o `.exec()` cru é obrigatório — e, em
    troca, a função tem que descartar a instância ela mesma;
  * `menu.exec(posicao)` e `app.exec()` não entram: o primeiro leva argumento,
    o segundo não mora na camada de UI.

E a do §3.3, mesma ideia: `setRowCount`/`setCellWidget` crus deixam o widget
antigo pendurado no viewport, na geometria velha, até o Qt passar recolhendo.
Quem repopula tabela chama `limpar_tabela`/`definir_celula`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import gestor_comercial.ui as pacote_ui

RAIZ_UI = Path(pacote_ui.__file__).parent
# `modais.py` é o próprio helper: o `modal.exec()` de dentro dele é a
# implementação, não um site de chamada.
ARQUIVO_DO_HELPER = "modais.py"
# 31 no diagnóstico do §3.2; +3 com a subcategoria do §9.9 (o cadastro e a
# renomeação, que reaproveitam o modal num `while`, e a confirmação de
# exclusão, que é um `QMessageBox` comum).
SITES_ESPERADOS = 36

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _e_abertura_de_dialogo(no: ast.AST) -> bool:
    """`X.exec()` pelado — sem argumento, que é o que separa a abertura de
    diálogo do `menu.exec(posicao)` do menu de contexto."""
    return (
        isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "exec"
        and not no.args
        and not no.keywords
    )


def _e_chamada_a(no: ast.AST, nome: str) -> bool:
    return isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == nome


def _funcao_de_cada_no(arvore: ast.Module) -> dict[int, ast.AST]:
    """Mapa `id(nó) -> função que o contém`, pela função **mais interna**.

    Um `ast.walk` a partir de um `FunctionDef` enxerga também o corpo das
    funções aninhadas nele, e as views têm classes de diálogo com métodos
    dentro. Descer de fora para dentro faz a atribuição mais interna vencer, que
    é a que dá a mensagem de erro certa.
    """
    dono: dict[int, ast.AST] = {}

    def descer(no: ast.AST, funcao: ast.AST | None) -> None:
        if funcao is not None:
            dono[id(no)] = funcao
        atual = no if isinstance(no, _DEFS) else funcao
        for filho in ast.iter_child_nodes(no):
            descer(filho, atual)

    descer(arvore, None)
    return dono


def _testes_de_while(arvore: ast.Module) -> set[int]:
    """As chamadas que são a condição de um `while` — o modal reaproveitado.

    Cobre tanto `while modal.exec():` quanto o `while modal.exec() == Accepted:`
    que o cardápio usa.
    """
    alvos: set[int] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.While):
            continue
        condicao = no.test
        if isinstance(condicao, ast.Compare):
            condicao = condicao.left
        alvos.add(id(condicao))
    return alvos


def _varrer() -> tuple[list[str], list[str], int]:
    """Devolve (infratores, reaproveitados, total de sites) da camada de UI."""
    infratores: list[str] = []
    reaproveitados: list[str] = []
    total = 0

    for caminho in sorted(RAIZ_UI.rglob("*.py")):
        if caminho.name == ARQUIVO_DO_HELPER:
            continue
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        relativo = caminho.relative_to(RAIZ_UI).as_posix()
        dono = _funcao_de_cada_no(arvore)
        reaproveitaveis = _testes_de_while(arvore)

        for no in ast.walk(arvore):
            if _e_chamada_a(no, "executar_modal"):
                total += 1
                continue
            if not _e_abertura_de_dialogo(no):
                continue

            funcao = dono.get(id(no))
            onde = f"{relativo}:{no.lineno}" + (f" em {funcao.name}()" if funcao else "")
            if id(no) not in reaproveitaveis:
                infratores.append(onde)
                continue

            total += 1
            reaproveitados.append(onde)
            # O `.exec()` cru só se justifica se a própria função assumir o
            # descarte que ela tirou do `executar_modal`.
            descarta = funcao is not None and any(
                _e_chamada_a(interno, "descartar_modal") for interno in ast.walk(funcao)
            )
            if not descarta:
                infratores.append(f"{onde} — `while` sem descartar_modal() fora do laço")

    return infratores, reaproveitados, total


def test_nenhuma_tela_abre_modal_com_exec_cru():
    infratores, _, _ = _varrer()
    assert not infratores, "aberturas de diálogo fora do executar_modal():\n  " + "\n  ".join(
        infratores
    )


def test_o_modal_reaproveitado_no_while_e_descartado_fora_do_laco():
    """Os quatro `while modal.exec()` do cardápio são a exceção da regra — e a
    exceção só é legítima porque a função descarta a instância ela mesma.

    Eram dois (criar/editar produto). O §9.9 trouxe mais dois, pelo mesmo
    motivo: o cadastro e a renomeação de subcategoria reabrem o MESMO diálogo
    quando o service recusa o nome, para o gerente corrigir sem redigitar."""
    _, reaproveitados, _ = _varrer()
    assert len(reaproveitados) == 4, (
        "esperados exatamente 4 modais reaproveitados (cardapio_view: produto e "
        f"subcategoria, criar/editar), achados {len(reaproveitados)}: {reaproveitados}"
    )
    assert all("cardapio_view.py" in site for site in reaproveitados), reaproveitados


def test_os_sites_do_diagnostico_continuam_cobertos():
    """§3.2 mapeou 31 pontos de abertura e o §9.9 acrescentou 3. Os dois
    últimos são as barreiras de credencial: o PIN Master antes de excluir um
    funcionário e o CPF do Dono antes de revelar um segredo em Configurações.
    Se este número cair sem uma tela sumir junto, alguém trocou
    `executar_modal` por `.exec()` de novo; se subir, há site novo — e ele
    precisa entrar na conta de propósito, não por acidente."""
    _, _, total = _varrer()
    assert total == SITES_ESPERADOS, f"{total} sites de modal, esperados {SITES_ESPERADOS}"


# ---------------------------------------------------------------------------
# §3.3 — tabelas
# ---------------------------------------------------------------------------

ARQUIVO_DAS_TABELAS = "tabelas.py"
# `setRowCount` e `setCellWidget` crus só podem existir dentro do próprio
# utilitário. Fora dele, o par é `limpar_tabela`/`definir_celula`.
METODOS_CRUS = ("setRowCount", "setCellWidget")


def _chamadas_cruas_de_tabela() -> list[str]:
    achados: list[str] = []
    for caminho in sorted(RAIZ_UI.rglob("*.py")):
        if caminho.name == ARQUIVO_DAS_TABELAS:
            continue
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        relativo = caminho.relative_to(RAIZ_UI).as_posix()
        dono = _funcao_de_cada_no(arvore)
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                continue
            if no.func.attr not in METODOS_CRUS:
                continue
            funcao = dono.get(id(no))
            sufixo = f" em {funcao.name}()" if funcao else ""
            achados.append(f"{relativo}:{no.lineno} — {no.func.attr}(){sufixo}")
    return achados


def test_nenhuma_tela_mexe_na_tabela_por_fora_dos_utilitarios():
    """`setRowCount(0)`/`setRowCount(n)` deixam os widgets de célula vivos até o
    Qt recolher, e `setCellWidget` não destrói o ocupante anterior da célula.
    É o par que já custou dois bugs visuais de sobreposição neste projeto."""
    achados = _chamadas_cruas_de_tabela()
    assert not achados, (
        "tabelas mexidas fora de limpar_tabela/definir_celula:\n  "
        + "\n  ".join(achados)
    )
