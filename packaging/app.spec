# -*- mode: python ; coding: utf-8 -*-
"""Empacota o Gestor Comercial num único .exe de produção.

Roda com (a partir da raiz do repo):

    .venv\\Scripts\\pyinstaller.exe --clean --noconfirm packaging\\app.spec

ou pelo fluxo completo, com testes e prova de fumaça: `packaging\\gerar_exe.py`.

## O que vai dentro

- `alembic.ini` e `migrations/`: `main.py` chama `alembic.command.upgrade` em
  todo boot — sem eles o .exe sobe sem banco.
- `resources/`: fonte da marca e o ícone da janela.
- A **semente** (`semente/banco_seed.db` + `semente/thumbnails/`): o banco de
  trabalho do Vitor, com o cardápio e as fotos, que o primeiro boot copia para
  `%APPDATA%\\GestorComercial_V2\\` (ver `core/banco_semente.py`). Ela é gerada
  AQUI, a cada build, por `packaging/preparar_semente.py` — nunca sai de um
  arquivo velho esquecido em `build/`. Se o banco de origem não servir (venda de
  teste gravada, foto faltando, banco corrompido), o build para antes de
  empacotar qualquer coisa.

Nenhum desses é código Python, então o PyInstaller não os descobre sozinho.

## O que fica de fora (máquina do food truck: Celeron, 4 GB)

O `.exe` de arquivo único extrai tudo para uma pasta temporária a CADA abertura,
então cada MB cortado é tempo de boot e escrita em disco a menos. O app só usa
QtCore, QtGui e QtWidgets, e o hook do PySide6 trazia junto:

- `opengl32sw.dll` (20,6 MB): OpenGL por software, que só QtQuick/QOpenGLWidget
  usam;
- `translations/` (6,8 MB): o app não instala `QTranslator`;
- plugins que puxam Qt Quick/QML (teclado virtual), Qt PDF (imagem PDF) e Qt
  Network/OpenSSL (toque TUIO, TLS, informação de rede).

As DLLs do Qt não são apagadas por lista: depois de tirar os plugins, cada
`Qt6*.dll` só sai se NENHUM binário que ficou a importa (grafo de imports do
próprio PyInstaller). Esquecer uma dependência aqui derrubaria o boot na
máquina do pai; a poda por alcançabilidade não tem como esquecer.
"""

import re
import subprocess
import sys
from pathlib import Path

from PyInstaller.depend import bindepend
from PyInstaller.utils.hooks import collect_data_files

RAIZ = Path(SPECPATH).parent
SEMENTE = RAIZ / "build" / "semente"
ICONE = RAIZ / "resources" / "icons" / "app_icon.ico"

if not ICONE.is_file():
    raise SystemExit(f"Ícone não encontrado: {ICONE}\nRode: .venv\\Scripts\\python.exe packaging\\gerar_icone.py")

_etapa = subprocess.run([sys.executable, str(RAIZ / "packaging" / "preparar_semente.py"), "--destino", str(SEMENTE)])
if _etapa.returncode != 0:
    raise SystemExit("A semente do banco não pôde ser preparada (motivo acima). Build interrompido.")


def _arquivos_de(pasta: Path, destino: str) -> list[tuple[str, str]]:
    """Cada arquivo da pasta como `datas`, sem `__pycache__` de desenvolvimento."""
    return [
        (str(arquivo), str(Path(destino) / arquivo.parent.relative_to(pasta)))
        for arquivo in sorted(pasta.rglob("*"))
        if arquivo.is_file() and "__pycache__" not in arquivo.parts
    ]


a = Analysis(
    [str(RAIZ / "src" / "gestor_comercial" / "main.py")],
    pathex=[str(RAIZ / "src")],
    binaries=[],
    datas=[
        (str(RAIZ / "alembic.ini"), "."),
        *_arquivos_de(RAIZ / "migrations", "migrations"),
        *_arquivos_de(RAIZ / "resources", "resources"),
        *_arquivos_de(SEMENTE, "semente"),
        # python-escpos lê capabilities.json do próprio pacote em runtime
        # (perfis de comando por modelo de impressora) — sem isso a
        # impressora tipo Windows falha com "No such file or directory:
        # ...\escpos\capabilities.json" (visto em campo, 2026-09-01).
        *collect_data_files("escpos"),
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
    excludes=[
        # Ferramentas de desenvolvimento e bibliotecas que nenhum código do app
        # importa — chegavam por imports opcionais de terceiros (o `pygments`
        # pelo plugin de realce do Mako, o `numpy` pela tipagem do Pillow).
        "tkinter",
        "PIL.ImageTk",
        "PIL._imagingtk",
        "numpy",
        "pygments",
        "setuptools",
        "pkg_resources",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
        "pytest",
        "_pytest",
        "PyInstaller",
        "pip",
        # 7,9 MB do leitor AVIF do Pillow, que o python-escpos arrasta. O
        # Pillow importa esse módulo dentro de try/except, e o app não lê AVIF
        # (o Qt do projeto também não: `imagem_service.EXTENSOES_ACEITAS`).
        "PIL._avif",
    ],
    noarchive=False,
    optimize=0,
)

_CORTES = (
    "PySide6/opengl32sw.dll",
    "PySide6/translations/",
    "PySide6/plugins/platforminputcontexts/",
    "PySide6/plugins/imageformats/qpdf.dll",
    "PySide6/plugins/generic/",
    "PySide6/plugins/networkinformation/",
    "PySide6/plugins/tls/",
)
_PODAVEL = re.compile(r"qt6\w+\.dll|lib(ssl|crypto)-3-x64\.dll")


def _cortado(destino: str) -> bool:
    return destino.replace("\\", "/").startswith(_CORTES)


def _podar(binarios):
    """Tira os cortes e, depois, as DLLs do Qt que nada do que ficou importa."""
    restantes = [e for e in binarios if not _cortado(e[0])]
    podaveis = {Path(e[0]).name.lower(): e for e in restantes if _PODAVEL.fullmatch(Path(e[0]).name.lower())}
    alcancadas = set()
    fila = [e for e in restantes if Path(e[0]).name.lower() not in podaveis]
    while fila:
        _destino, origem, _tipo = fila.pop()
        try:
            importadas = bindepend.get_imports(origem)
        except Exception:
            continue
        for nome, _caminho in importadas:
            nome = nome.lower()
            if nome in podaveis and nome not in alcancadas:
                alcancadas.add(nome)
                fila.append(podaveis[nome])
    removidas = set(podaveis) - alcancadas
    print(f"[app.spec] DLLs do Qt sem ninguém que as importe, removidas: {sorted(removidas) or 'nenhuma'}")
    return [e for e in restantes if Path(e[0]).name.lower() not in removidas]


_antes = sum(Path(e[1]).stat().st_size for e in a.binaries + a.datas if Path(e[1]).is_file())
a.binaries = _podar(a.binaries)
a.datas = [e for e in a.datas if not _cortado(e[0])]
_depois = sum(Path(e[1]).stat().st_size for e in a.binaries + a.datas if Path(e[1]).is_file())
print(f"[app.spec] binários + dados: {_antes / 1e6:.1f} MB -> {_depois / 1e6:.1f} MB")

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
    # Sem UPX: a descompressão custa CPU a cada boot no Celeron, e executável
    # comprimido por UPX é o alvo favorito de falso positivo de antivírus.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICONE),
)
