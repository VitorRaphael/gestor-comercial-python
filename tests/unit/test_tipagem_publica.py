"""Toda função pública do projeto declara os tipos que recebe e devolve. §3, Fase 5.

Tipagem completa aqui não é gosto: é a única documentação que o editor lê. O
projeto é do Vitor, que está aprendendo a programar, e é o autocompletar que
diz que `conectar_mudanca_periodo` quer um `Callable[[int], None]` e não um
`Signal`. Sem anotação, o editor não tem o que oferecer e o erro só aparece
quando o pai dele clica no botão.

Estado em que a Fase 5 encontrou o projeto: **380 de 403 funções públicas já
tipadas**. As 23 que faltavam eram as sobrecargas de evento do Qt, os `session`
do seed e três callbacks. Este teste é o que impede a conta de voltar a cair.

Privadas (`_nome`) ficam de fora de propósito: quem lê uma função privada tem o
corpo dela à mão, e exigir anotação em toda auxiliar de três linhas viraria
ruído sem leitor.
"""

from __future__ import annotations

import ast
from pathlib import Path

import gestor_comercial

RAIZ = Path(gestor_comercial.__file__).parent


def _e_publica(funcao: ast.AST) -> bool:
    """Pública = não começa com `_`. Dunders (`__init__`, `__exit__`) contam:
    são a porta de entrada da classe."""
    nome = funcao.name
    return not nome.startswith("_") or nome.startswith("__")


def _lacunas() -> list[str]:
    achados: list[str] = []
    for caminho in sorted(RAIZ.rglob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        relativo = caminho.relative_to(RAIZ).as_posix()
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _e_publica(no):
                continue
            argumentos = [
                arg
                for arg in no.args.args + no.args.kwonlyargs
                if arg.arg not in ("self", "cls")
            ]
            sem_tipo = [arg.arg for arg in argumentos if arg.annotation is None]
            if sem_tipo:
                achados.append(f"{relativo}:{no.lineno} {no.name}() — sem tipo: {', '.join(sem_tipo)}")
            if no.returns is None:
                achados.append(f"{relativo}:{no.lineno} {no.name}() — sem tipo de retorno")
    return achados


def test_o_varredor_realmente_acha_as_funcoes_publicas():
    """Premissa: um varredor que não acha nada passa verde sem ter olhado."""
    encontradas = sum(
        1
        for caminho in RAIZ.rglob("*.py")
        for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8")))
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and _e_publica(no)
    )

    assert encontradas > 300, f"o varredor só achou {encontradas} funções públicas"


def test_toda_funcao_publica_esta_tipada():
    lacunas = _lacunas()

    assert not lacunas, (
        f"{len(lacunas)} lacuna(s) de tipagem em função pública:\n  " + "\n  ".join(lacunas)
    )
