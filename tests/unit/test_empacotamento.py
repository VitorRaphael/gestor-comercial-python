"""O que o `.exe` precisa encontrar, conferido sem gerar o `.exe`.

A prova de verdade é `packaging/gerar_exe.py`, que abre o executável. Estes
testes pegam antes, na suíte, as duas divergências que o build não acusaria:
um ícone sem os tamanhos que o Windows pede, e o identificador da barra de
tarefas diferente entre o programa e o atalho do instalador — que não quebra
nada, só faz o programa fixado e o programa aberto virarem dois botões.
"""

from __future__ import annotations

import re
from pathlib import Path

import gestor_comercial
from gestor_comercial import main
from gestor_comercial.core.caminhos import recurso

RAIZ = Path(gestor_comercial.__file__).resolve().parents[2]


def test_icone_da_janela_existe_com_todos_os_tamanhos_do_windows():
    from PIL import Image

    icone = recurso(main.ICONE_DO_APP)

    with Image.open(icone) as imagem:
        tamanhos = set(imagem.info["sizes"])
    assert {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= tamanhos


def test_cantos_do_icone_sao_transparentes():
    """A arte oficial veio sobre fundo branco; na barra escura, quinas brancas."""
    from PIL import Image

    with Image.open(recurso(main.ICONE_DO_APP)) as imagem:
        imagem.size = (256, 256)
        quadro = imagem.convert("RGBA")
    assert [quadro.getpixel(p)[3] for p in ((0, 0), (255, 0), (0, 255), (255, 255))] == [0, 0, 0, 0]
    assert quadro.getpixel((128, 128))[3] == 255


def test_atalho_do_instalador_usa_o_mesmo_identificador_do_programa():
    instalador = (RAIZ / "packaging" / "instalador.iss").read_text(encoding="utf-8")

    identificadores = set(re.findall(r'AppUserModelID:\s*"([^"]+)"', instalador))

    assert identificadores == {main.ID_DO_APP_NO_WINDOWS}


def test_spec_e_instalador_apontam_para_o_icone_que_existe():
    spec = (RAIZ / "packaging" / "app.spec").read_text(encoding="utf-8")
    instalador = (RAIZ / "packaging" / "instalador.iss").read_text(encoding="utf-8")

    assert '"app_icon.ico"' in spec
    assert r"SetupIconFile=..\resources\icons\app_icon.ico" in instalador
    assert recurso("resources/icons/app_icon.ico").is_file()
