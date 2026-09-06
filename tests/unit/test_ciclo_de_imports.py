"""O import tardio de `AuthService.__init__` é obrigatório. Ver §3.12.

Este arquivo existe por causa de um comentário. O `__init__` do `AuthService`
importa `LojaConfigService` dentro da função, e o comentário ao lado afirmava
que `loja_config_service` **não** importa `auth_service` no nível de módulo —
o oposto do que o código faz (`loja_config_service.py:29`). Quem lesse aquilo
e "limpasse" o import para o topo derrubava o boot do app inteiro, com um
`ImportError` que só aparece ao abrir o programa: nenhum teste de unidade
pegava, porque cada um deles importa os módulos numa ordem que já funciona.

O comentário foi corrigido. O teste abaixo é o que impede a limpeza de passar
mesmo que alguém não leia o comentário nenhum.
"""

from __future__ import annotations

import ast
from pathlib import Path

import gestor_comercial

RAIZ = Path(gestor_comercial.__file__).parent
AUTH = RAIZ / "services" / "auth_service.py"
LOJA_CONFIG = RAIZ / "services" / "loja_config_service.py"


def _importa_no_nivel_de_modulo(arquivo: Path, modulo: str) -> bool:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return any(
        isinstance(no, ast.ImportFrom) and no.module == modulo
        for no in arvore.body  # só o corpo do módulo: import dentro de função não conta
    )


def test_loja_config_importa_auth_no_topo():
    """A metade do ciclo que o comentário antigo negava."""
    assert _importa_no_nivel_de_modulo(
        LOJA_CONFIG, "gestor_comercial.services.auth_service"
    ), "se este import saiu do topo, o import tardio do AuthService pode ter deixado de ser necessário"


def test_auth_nao_importa_loja_config_no_topo():
    """A outra metade: aqui o import TEM que continuar dentro da função."""
    assert not _importa_no_nivel_de_modulo(
        AUTH, "gestor_comercial.services.loja_config_service"
    ), (
        "`LojaConfigService` voltou para o topo de auth_service.py — isto fecha o "
        "ciclo de imports e o app não abre. O import tem que ficar dentro de "
        "`AuthService.__init__` (§3.12)."
    )
