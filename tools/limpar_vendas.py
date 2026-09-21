"""Apaga as vendas de teste de um banco e mantém o cardápio. Ver `repository/limpeza_de_vendas.py`.

    .venv\\Scripts\\python.exe tools\\limpar_vendas.py [--banco CAMINHO] [--confirmar]

Sem `--banco`, é o banco de trabalho (`~/.gestor_comercial/`, ou o que
`GESTOR_COMERCIAL_DB` apontar). Mostra quantas linhas de venda cada tabela tem
e pede `SIM` antes de apagar; `--confirmar` pula a pergunta. Feche o programa
antes — com ele aberto, a limpeza é recusada e nada é apagado.

Uso típico, antes de gerar o `.exe`: o build recusa a semente enquanto o banco
tiver venda de teste, e a mensagem manda para cá.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from gestor_comercial.core.caminhos import caminho_do_banco  # noqa: E402
from gestor_comercial.repository.limpeza_de_vendas import (  # noqa: E402
    LimpezaRecusada,
    contar_movimento,
    limpar_vendas,
)


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--banco", type=Path, default=caminho_do_banco())
    parser.add_argument("--confirmar", action="store_true", help="apaga sem perguntar")
    argumentos = parser.parse_args()
    banco: Path = argumentos.banco

    try:
        antes = contar_movimento(banco)
        print(f"\nBanco: {banco}\nLinhas de venda:")
        for tabela, linhas in antes.items():
            print(f"  {tabela:.<28} {linhas}")
        if not any(antes.values()):
            print("\nNenhuma venda no banco. Nada a fazer.\n")
            return 0
        print("\nCardápio, mesas, funcionários, logins, senhas, impressoras e preferências ficam.")
        if not argumentos.confirmar and input("Digite SIM para apagar as vendas: ").strip().upper() != "SIM":
            print("\nCancelado. Nada foi apagado.\n")
            return 1
        relatorio = limpar_vendas(banco)
    except LimpezaRecusada as erro:
        print(f"\nLIMPEZA RECUSADA: {erro}\n", file=sys.stderr)
        return 1

    print(
        "\nVendas apagadas\n"
        f"  linhas ............ {sum(relatorio.apagadas.values())} "
        f"({', '.join(f'{t}: {n}' for t, n in relatorio.apagadas.items() if n) or 'nenhuma'})\n"
        f"  saldos zerados .... {relatorio.funcionarios_com_saldo_zerado}\n"
        f"  mesas liberadas ... {relatorio.mesas_liberadas}\n"
        f"  cópia de antes .... {relatorio.copia_de_seguranca}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
