"""Gera `build/semente/` a partir do banco de trabalho. Chamado pelo `app.spec`.

Também roda sozinho, para conferir a semente sem gerar o `.exe`:

    .venv\\Scripts\\python.exe packaging\\preparar_semente.py

A regra do que entra e do que é recusado mora em
`repository/preparo_da_semente.py`; este script só escolhe os caminhos e
injeta o Alembic, que leva a CÓPIA até a última migration — o banco de trabalho
é aberto somente para leitura e sai do build do jeito que entrou.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from gestor_comercial.core.caminhos import caminho_do_banco  # noqa: E402
from gestor_comercial.repository.preparo_da_semente import SementeRecusada, preparar_semente  # noqa: E402

PASTA_PADRAO = RAIZ / "build" / "semente"


def _config_do_alembic(banco: Path):
    from alembic.config import Config

    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{banco}")
    return config


def _migrar(banco: Path) -> None:
    from alembic import command

    command.upgrade(_config_do_alembic(banco), "head")


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--origem", type=Path, default=caminho_do_banco())
    parser.add_argument("--destino", type=Path, default=PASTA_PADRAO)
    argumentos = parser.parse_args()

    try:
        relatorio = preparar_semente(argumentos.origem, argumentos.destino, migrar=_migrar)
    except SementeRecusada as erro:
        print(f"\nSEMENTE RECUSADA: {erro}\n", file=sys.stderr)
        return 1

    from alembic.script import ScriptDirectory

    cabeca = ScriptDirectory.from_config(_config_do_alembic(relatorio.banco)).get_current_head()
    if relatorio.revisao != cabeca:
        print(f"\nSEMENTE RECUSADA: revisão {relatorio.revisao}, esperada {cabeca}\n", file=sys.stderr)
        return 1

    print(
        "\nSemente do banco pronta\n"
        f"  origem ............ {argumentos.origem}\n"
        f"  destino ........... {argumentos.destino}\n"
        f"  revisão ........... {relatorio.revisao}\n"
        f"  banco ............. {relatorio.bytes_do_banco // 1024} KB\n"
        f"  categorias ........ {relatorio.categorias}\n"
        f"  subcategorias ..... {relatorio.subcategorias}\n"
        f"  produtos .......... {relatorio.produtos}\n"
        f"  itens de combo .... {relatorio.componentes_de_combo}\n"
        f"  mesas ............. {relatorio.mesas}\n"
        f"  fotos ............. {relatorio.fotos} (sem produto, ignoradas: {relatorio.fotos_sem_produto_ignoradas})\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
