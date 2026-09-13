#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para resetar completamente o banco de dados do Gestor Comercial.

Uso:
    python -m tools.resetar_banco
    ou
    python tools/resetar_banco.py

O que faz:
    1. Deleta o arquivo .db (~/.gestor_comercial/gestor_comercial.db)
    2. Remove a marca 'bootstrap_concluido' para que o seed rode novamente
    3. Deixa o banco pronto para ser recriado do zero

Depois de rodar este script:
    - Abra o app normalmente
    - Ele vai recriar as tabelas e mesas vazias
    - Você pode preencher o cardapio, combos e funcionarios manualmente
    - Quando gerar o .exe, o banco completo vai junto
"""

import os
from pathlib import Path

# Calcular DB_PATH igual ao projeto (ve a variavel de ambiente ou usa o padrao)
DB_PATH = Path(os.environ.get(
    "GESTOR_COMERCIAL_DB",
    Path.home() / ".gestor_comercial" / "gestor_comercial.db"
))


def resetar_banco():
    """Reseta o banco de dados completamente."""

    print("\n" + "=" * 70)
    print("[AVISO] Voce esta prestes a deletar o banco de dados local!")
    print("=" * 70)
    print(f"\nArquivo a ser deletado: {DB_PATH}")
    print("\nIsso vai apagar:")
    print("  - Todas as mesas, comandas e itens")
    print("  - Cardapio e combos")
    print("  - Funcionarios e turnos")
    print("  - Historico de vendas e caixa")
    print("\nDepois, quando voce abrir o app, as tabelas serao recriadas vazias.")
    print("=" * 70)

    resposta = input("\nDeseja continuar? Digite 'SIM' para confirmar: ").strip().upper()

    if resposta != "SIM":
        print("\n[CANCELADO] Nada foi deletado.")
        return False

    # Deletar arquivo .db
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
            print(f"\n[OK] Arquivo deletado: {DB_PATH}")
        except Exception as e:
            print(f"\n[ERRO] Erro ao deletar arquivo: {e}")
            return False
    else:
        print(f"\n[AVISO] Arquivo nao encontrado: {DB_PATH}")
        print("   (O banco pode ja estar vazio ou em outro local)")

    print("\n" + "=" * 70)
    print("[OK] Banco resetado com sucesso!")
    print("\nProximos passos:")
    print("  1. Abra o app normalmente")
    print("  2. Ele vai recriar as tabelas automaticamente")
    print("  3. O seed vai popular dados iniciais (mesas, usuarios)")
    print("  4. Depois voce deleta/desativa os dados que nao quer")
    print("  5. Cria seu cardapio, combos e funcionarios")
    print("  6. Quando estiver pronto, gera o .exe")
    print("=" * 70 + "\n")

    return True


if __name__ == "__main__":
    resetar_banco()
