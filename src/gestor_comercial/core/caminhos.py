"""Onde o programa lê o que é dele e onde grava o que é do usuário — num lugar só.

São duas raízes, e confundi-las é o defeito que este módulo existe para impedir:

- **Recursos** (`alembic.ini`, `migrations/`, `resources/`, a semente do banco):
  vêm com o programa e são só leitura. Em desenvolvimento moram na raiz do
  repositório; no `.exe` do PyInstaller moram na pasta temporária de extração
  (`sys._MEIPASS`), que é recriada a cada boot.
- **Dados** (banco, fotos, backups, log, cupons de teste): são do usuário e têm
  que sobreviver a reinstalar o programa.

## Por que o `.exe` tem pasta de dados própria

A máquina do food truck já rodou um `.exe` anterior (o de 2026-09-01), que
gravou banco, fotos e log em `%USERPROFILE%\\.gestor_comercial\\`. Aqueles
dados são de uma fase de testes e não podem chegar à produção. O `.exe` atual
grava em `%APPDATA%\\GestorComercial_V2\\` e **não conhece outro lugar**:

- não existe fallback para `~/.gestor_comercial` — se a pasta nova estiver
  vazia, quem a preenche é a semente embutida (`core/banco_semente.py`), nunca
  o banco antigo;
- a variável `GESTOR_COMERCIAL_DB` é **ignorada** no `.exe`. Ela existe para a
  suíte e as ferramentas apontarem para um banco descartável, e o `DEPLOYMENT.md`
  antigo sugeria usá-la para fixar o caminho na máquina do pai — uma variável
  dessas esquecida no Windows dele levaria o programa novo direto para o banco
  velho.

Em desenvolvimento nada mudou: `~/.gestor_comercial/` continua sendo a pasta de
trabalho do Vitor, e a variável continua valendo.

Só stdlib, como todo o `core/`: o log (`core/resilience.py`) precisa saber onde
mora antes de qualquer outra camada carregar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

NOME_DA_PASTA_DE_PRODUCAO = "GestorComercial_V2"
NOME_DA_PASTA_DE_DESENVOLVIMENTO = ".gestor_comercial"
NOME_DO_BANCO = "gestor_comercial.db"
VARIAVEL_DO_BANCO = "GESTOR_COMERCIAL_DB"

# Relativa à pasta de dados. As fotos são gravadas aqui pelo `imagem_service` e
# restauradas aqui pela semente — o mesmo valor nos dois lados.
SUBPASTA_DAS_FOTOS = Path("uploads") / "thumbnails"


def empacotado() -> bool:
    """`True` rodando de dentro do `.exe` gerado pelo PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def raiz_de_recursos() -> Path:
    """Raiz de onde ler `alembic.ini`, `migrations/`, `resources/` e a semente."""
    if empacotado():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # src/gestor_comercial/core/caminhos.py -> raiz do repositório
    return Path(__file__).resolve().parents[3]


def recurso(relativo: str | Path) -> Path:
    """Caminho absoluto de um recurso que viaja com o programa."""
    return raiz_de_recursos() / relativo


def pasta_de_dados() -> Path:
    """A pasta de dados do usuário, derivada em runtime e nunca gravada."""
    if empacotado():
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / NOME_DA_PASTA_DE_PRODUCAO
    bruto = os.environ.get(VARIAVEL_DO_BANCO)
    if bruto and bruto != ":memory:":
        return Path(bruto).expanduser().parent
    return Path.home() / NOME_DA_PASTA_DE_DESENVOLVIMENTO


def caminho_do_banco() -> Path:
    """O arquivo SQLite do app."""
    if empacotado():
        return pasta_de_dados() / NOME_DO_BANCO
    return Path(
        os.environ.get(VARIAVEL_DO_BANCO, Path.home() / NOME_DA_PASTA_DE_DESENVOLVIMENTO / NOME_DO_BANCO)
    )
