# -*- mode: python ; coding: utf-8 -*-
"""Empacota o Gestor Comercial num único .exe (Fase 5 do TODO.md).

Roda com: pyinstaller packaging/build.spec (a partir da raiz do repo).

`alembic.ini` e `migrations/` viajam junto porque `main.py` chama
`alembic.command.upgrade` em todo boot (ver `_aplicar_migrations`) — sem
eles o .exe sobe sem banco. `resources/` viaja pelo mesmo motivo: é onde
mora o QSS do tema (e futuramente ícones/fontes). Nenhum dos dois é código
Python, então o PyInstaller não os descobre sozinho — têm que entrar via
`datas`.

O banco de dados em si (`~/.gestor_comercial/gestor_comercial.db`, ver
`repository/base.py`) fica fora do bundle de propósito: é gerado e mantido
fora do diretório do app, para sobreviver a uma reinstalação do .exe.
"""

from pathlib import Path

RAIZ = Path(SPECPATH).parent

a = Analysis(
    [str(RAIZ / "src" / "gestor_comercial" / "main.py")],
    pathex=[str(RAIZ / "src")],
    binaries=[],
    datas=[
        (str(RAIZ / "alembic.ini"), "."),
        (str(RAIZ / "migrations"), "migrations"),
        (str(RAIZ / "resources"), "resources"),
    ],
    hiddenimports=[
        # `migrations/env.py` só existe pro PyInstaller como arquivo de
        # dado (bundle via `datas` acima) — o Alembic executa esse arquivo
        # em runtime, então os imports de dentro dele (`logging.config`,
        # `sqlalchemy`, etc.) não aparecem na análise estática do spec e
        # precisam ser listados aqui manualmente.
        "logging.config",
        "alembic",
        "sqlalchemy.dialects.sqlite",
        # python-escpos: cada tipo de conexão (USB/Serial/Rede/Windows/
        # Arquivo) só é importado sob demanda por
        # `hardware/impressora_escpos.py`, conforme o tipo cadastrado.
        "escpos.printer",
        "win32print",
        "win32ui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GestorComercial",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RAIZ / "resources" / "icons" / "app.ico"),
)
