"""A semente do banco: o cardápio pronto que viaja dentro do `.exe`.

Não confundir com `repository/seed.py`. Aquele é o povoamento **de fábrica**,
escrito em código (60 mesas, dois turnos, um cardápio de exemplo) e rodado em
banco que nasce vazio. A semente é o **banco de verdade do Vitor** — o cardápio
que ele montou na tela, com subcategorias, combos, senhas e as fotos —,
copiado na hora do build (`repository/preparo_da_semente.py`) e embutido no
`.exe` pelo `packaging/app.spec`.

No boot, `provisionar()` decide entre duas coisas e só duas:

- **a pasta de dados já tem banco** → não faz nada. É o caminho de toda abertura
  depois da primeira, e custa um `stat`. O banco existente nunca é lido,
  comparado nem sobrescrito: dali para frente as vendas são dele.
- **não tem** → copia as fotos e, por último, o banco.

## A ordem é a garantia

O banco é o **ponto de confirmação**. Ele só aparece na pasta de dados (por
`os.replace`, atômico no mesmo volume) depois de todas as fotos gravadas e
sincronizadas no disco. Se a energia cair no meio, o boot seguinte encontra a
pasta sem banco e refaz tudo do zero — com fotos pela metade não há banco que
aponte para elas. Na ordem inversa, uma queda entre o banco e as fotos deixaria
um cardápio sem imagem para sempre, porque "o banco já existe" encerraria a
provisão em todo boot seguinte.

Antes de o banco entrar, saem `-wal`, `-shm` e `-journal` que tenham sobrado de
um banco anterior apagado à mão. O SQLite não confere se o `-wal` pertence ao
arquivo ao lado: aplicaria as páginas de um banco velho sobre a semente e
entregaria um cardápio corrompido.

## Duplo clique

O `.exe` de arquivo único leva segundos para extrair no Celeron, e quem não vê
janela clica de novo. As duas instâncias chegariam aqui juntas, as duas sem
banco. Por isso a cópia roda sob uma trava de arquivo exclusiva do sistema
operacional (que o Windows solta sozinho se o processo morrer): a segunda
espera, e ao entrar confere de novo — encontra o banco que a primeira publicou
e sai sem tocar em nada.

Só stdlib, como todo o `core/`: roda antes do SQLAlchemy existir.
"""

from __future__ import annotations

import enum
import logging
import os
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from gestor_comercial.core.caminhos import SUBPASTA_DAS_FOTOS

# Leiaute da semente, relativo à raiz de recursos do programa. Quem grava é o
# preparo do build; quem lê é `provisionar`. O mesmo valor nos dois lados.
PASTA_DA_SEMENTE = "semente"
ARQUIVO_DO_BANCO_SEMENTE = "banco_seed.db"
PASTA_DAS_FOTOS_DA_SEMENTE = "thumbnails"

# Sufixos que o SQLite cria ao lado do banco.
_SUFIXOS_DO_SQLITE = ("-wal", "-shm", "-journal")
ARQUIVO_DA_TRAVA = ".provisionamento.lock"
SEGUNDOS_ESPERANDO_A_TRAVA = 120.0

_log = logging.getLogger("gestor_comercial")


class Provisionamento(enum.Enum):
    JA_EXISTIA = "banco existente preservado"
    CRIADO_DA_SEMENTE = "banco criado a partir da semente"
    SEM_SEMENTE = "sem semente embutida"


@dataclass(frozen=True, slots=True)
class ResultadoDoProvisionamento:
    situacao: Provisionamento
    banco: Path
    fotos_copiadas: int = 0


def provisionar(banco: Path, semente: Path) -> ResultadoDoProvisionamento:
    """Garante o banco de produção, criando-o da semente se ainda não existir.

    `banco` é o arquivo que o app vai abrir (`core.caminhos.caminho_do_banco`);
    as fotos vão para a pasta ao lado dele, a mesma que o `imagem_service` lê.
    `semente` é a pasta com `banco_seed.db` e `thumbnails/`. Sem ela (rodando do
    código-fonte, por exemplo), não cria nada: o boot segue para as migrations e
    o `run_seed` como sempre fez.
    """
    if banco.exists():
        return ResultadoDoProvisionamento(Provisionamento.JA_EXISTIA, banco)

    banco_semente = semente / ARQUIVO_DO_BANCO_SEMENTE
    if not banco_semente.is_file():
        return ResultadoDoProvisionamento(Provisionamento.SEM_SEMENTE, banco)

    pasta = banco.parent
    pasta.mkdir(parents=True, exist_ok=True)
    with _trava_exclusiva(pasta / ARQUIVO_DA_TRAVA):
        # Outra instância pode ter publicado o banco enquanto esta esperava.
        if banco.exists():
            return ResultadoDoProvisionamento(Provisionamento.JA_EXISTIA, banco)

        fotos = _restaurar_fotos(semente / PASTA_DAS_FOTOS_DA_SEMENTE, pasta / SUBPASTA_DAS_FOTOS)
        for sufixo in _SUFIXOS_DO_SQLITE:
            banco.with_name(banco.name + sufixo).unlink(missing_ok=True)
        _copiar_duravel(banco_semente, banco)

    _log.info("Banco de produção criado da semente em %s (%d fotos)", banco, fotos)
    return ResultadoDoProvisionamento(Provisionamento.CRIADO_DA_SEMENTE, banco, fotos)


def _restaurar_fotos(origem: Path, destino: Path) -> int:
    destino.mkdir(parents=True, exist_ok=True)
    if not origem.is_dir():
        return 0
    copiadas = 0
    for foto in sorted(origem.iterdir()):
        if foto.is_file():
            _copiar_duravel(foto, destino / foto.name)
            copiadas += 1
    return copiadas


def _copiar_duravel(origem: Path, destino: Path) -> None:
    """Copia para um temporário ao lado, força o disco e só então troca o nome.

    Quem olha `destino` vê o arquivo antigo, nenhum, ou o novo inteiro — nunca
    metade. O nome do temporário leva o PID para duas instâncias não escreverem
    no mesmo arquivo.
    """
    temporario = destino.with_name(f"{destino.name}.{os.getpid()}.tmp")
    try:
        with origem.open("rb") as leitura, temporario.open("wb") as escrita:
            shutil.copyfileobj(leitura, escrita, 1024 * 1024)
            escrita.flush()
            os.fsync(escrita.fileno())
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


@contextmanager
def _trava_exclusiva(caminho: Path, espera_maxima: float = SEGUNDOS_ESPERANDO_A_TRAVA) -> Iterator[None]:
    """Trava de byte no arquivo, exclusiva entre processos.

    O sistema operacional solta a trava quando o processo morre, então uma queda
    no meio da provisão não deixa a pasta bloqueada para sempre (o que um arquivo
    de "ocupado" criado e apagado à mão deixaria).
    """
    with caminho.open("a+b") as arquivo:
        _travar(arquivo.fileno(), espera_maxima)
        try:
            yield
        finally:
            _destravar(arquivo.fileno())


if sys.platform == "win32":
    import msvcrt

    def _travar(descritor: int, espera_maxima: float) -> None:
        limite = time.monotonic() + espera_maxima
        while True:
            os.lseek(descritor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descritor, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= limite:
                    raise TimeoutError("Outra janela do programa está preparando o banco há tempo demais.") from None
                time.sleep(0.05)

    def _destravar(descritor: int) -> None:
        os.lseek(descritor, 0, os.SEEK_SET)
        msvcrt.locking(descritor, msvcrt.LK_UNLCK, 1)

else:  # pragma: no cover - o programa roda em Windows; isto é para a suíte fora dele
    import fcntl

    def _travar(descritor: int, espera_maxima: float) -> None:
        fcntl.flock(descritor, fcntl.LOCK_EX)

    def _destravar(descritor: int) -> None:
        fcntl.flock(descritor, fcntl.LOCK_UN)
