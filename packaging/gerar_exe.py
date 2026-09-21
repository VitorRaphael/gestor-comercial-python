"""Fluxo completo do `.exe` de produção, sem passo manual.

    .venv\\Scripts\\python.exe packaging\\gerar_exe.py [--sem-testes] [--origem CAMINHO]

1. **Ícone** — gera `resources/icons/app_icon.ico` se ainda não existir.
2. **Testes** — a suíte inteira; qualquer falha interrompe o build.
3. **Build** — `pyinstaller --clean` sobre `packaging/app.spec`, que prepara a
   semente do banco e empacota.
4. **Prova de fumaça** — abre o `.exe` DE VERDADE numa pasta de usuário falsa
   (`APPDATA` e `TEMP` apontando para uma pasta descartável) e confere o que o
   pai do Vitor vai ver na primeira abertura:
   - a janela principal abriu, sem nenhuma falha no log;
   - o banco nasceu da semente, com os mesmos produtos e todas as fotos;
   - `GESTOR_COMERCIAL_DB` apontando para outro banco é ignorada;
   - o banco de trabalho desta máquina (`~/.gestor_comercial`) não foi tocado;
   - na segunda abertura, o banco existente é preservado — um dado gravado
     entre as duas continua lá.
5. **Pasta do pendrive** — monta `App_Pendrive/` na raiz: o `.exe`, o banco da
   semente (só cadastro: o build já recusou venda) e as fotos, no leiaute do
   modo portátil (`core/caminhos.py`), mais um `LEIA-ME.txt`. Uma
   `App_Pendrive` que já tenha venda gravada não é sobrescrita: o build para.
6. **Prova do modo portátil** — abre o `.exe` de uma CÓPIA da `App_Pendrive`
   (a pasta entregue sai sem log nem `-wal`), com a pasta atual do processo em
   outro lugar, e confere que ele usou o banco ao lado dele e não tocou no
   `APPDATA`; depois move a cópia para outro caminho (o pendrive virando
   `C:\\`) e confere que a segunda abertura acha o mesmo banco lá.

`--origem CAMINHO` gera a semente de outro banco em vez do de trabalho — por
exemplo, uma cópia limpa com `tools/limpar_vendas.py` enquanto o programa segue
aberto no banco de trabalho. Só o passo de build recebe o caminho; a suíte roda
nos bancos dela.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = Path(sys.executable)
EXE = RAIZ / "dist" / "GestorComercial.exe"
ICONE = RAIZ / "resources" / "icons" / "app_icon.ico"
SEMENTE = RAIZ / "build" / "semente"
PENDRIVE = RAIZ / "App_Pendrive"

sys.path.insert(0, str(RAIZ / "src"))
from gestor_comercial.core.banco_semente import (  # noqa: E402
    ARQUIVO_DO_BANCO_SEMENTE,
    PASTA_DAS_FOTOS_DA_SEMENTE,
)
from gestor_comercial.core.caminhos import (  # noqa: E402
    NOME_DA_PASTA_DE_PRODUCAO,
    NOME_DO_BANCO,
    SUBPASTA_DAS_FOTOS,
    VARIAVEL_DO_BANCO,
)
from gestor_comercial.repository.limpeza_de_vendas import contar_movimento  # noqa: E402

SEGUNDOS_ESPERANDO_A_JANELA = 180

LEIA_ME_DO_PENDRIVE = """\
GESTOR COMERCIAL

Para abrir: dois cliques em GestorComercial.exe.

Esta pasta é o programa E os dados dele. Tudo o que for vendido fica gravado
aqui dentro, no arquivo gestor_comercial.db, e as fotos do cardápio ficam na
pasta uploads. Por isso:

- Não apague, não renomeie e não separe os arquivos desta pasta.
- Para levar para outro computador, copie a PASTA INTEIRA.
- O melhor é copiar a pasta para o computador (por exemplo, C:\\GestorComercial)
  e abrir de lá. Direto do pendrive também funciona, mas se o pendrive sair
  com o programa aberto, a venda em andamento pode se perder.
- A pasta backups (criada aqui dentro) guarda uma cópia a cada fechamento de
  caixa. Configurações > Cópia de Segurança gera uma na hora.

Na primeira vez, o Windows pode avisar "O Windows protegeu o computador":
clique em "Mais informações" e depois em "Executar assim mesmo".
"""


class FalhaNoBuild(Exception):
    pass


def etapa(titulo: str) -> None:
    print(f"\n==> {titulo}", flush=True)


def rodar(*comando: str | Path, ambiente: dict[str, str] | None = None) -> None:
    resultado = subprocess.run([str(parte) for parte in comando], cwd=RAIZ, env=ambiente)
    if resultado.returncode != 0:
        raise FalhaNoBuild(f"Comando falhou (código {resultado.returncode}): {' '.join(map(str, comando))}")


def _assinatura(caminho: Path) -> tuple[int, int] | None:
    return (caminho.stat().st_size, caminho.stat().st_mtime_ns) if caminho.exists() else None


def _contar(banco: Path, sql: str) -> int:
    """Lê um número do banco que o `.exe` acabou de largar.

    Conexão de leitura e escrita, e não `mode=ro`: o `.exe` é encerrado à força,
    o que deixa o `-wal` pedindo recuperação — e só uma conexão que pode escrever
    a faz (a somente leitura devolve "disk I/O error", o mesmo do teste de queda de
    energia).
    """
    with closing(sqlite3.connect(banco, timeout=5)) as conexao:
        return conexao.execute(sql).fetchone()[0]


def _filhos(pid: int) -> list[int]:
    """PIDs cujo pai é `pid` (Toolhelp32 do Windows, sem dependência nova)."""
    import ctypes
    from ctypes import wintypes

    class Entrada(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    retrato = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    entrada = Entrada(dwSize=ctypes.sizeof(Entrada))
    filhos = []
    try:
        continua = kernel32.Process32FirstW(retrato, ctypes.byref(entrada))
        while continua:
            if entrada.th32ParentProcessID == pid:
                filhos.append(entrada.th32ProcessID)
            continua = kernel32.Process32NextW(retrato, ctypes.byref(entrada))
    finally:
        kernel32.CloseHandle(retrato)
    return filhos


def _encerrar_arvore(processo: subprocess.Popen) -> None:
    """Mata o `.exe` e só volta quando o processo que segura o banco morreu de fato.

    O `.exe` de arquivo único é um processo pai que extrai e abre um filho — é o
    FILHO que abre a janela e o banco. O `taskkill` é assíncrono e o `wait()` do
    `Popen` só enxerga o pai: sem esperar o filho, a prova mexia no banco enquanto
    ele ainda estava mapeado por um processo morrendo, e o SQLite devolvia
    "disk I/O error".
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    alcas = [a for a in (kernel32.OpenProcess(0x00100000, False, pid) for pid in _filhos(processo.pid)) if a]  # SYNCHRONIZE
    try:
        subprocess.run(["taskkill", "/PID", str(processo.pid), "/T", "/F"], capture_output=True)
        processo.wait(timeout=30)
        for alca in alcas:
            if kernel32.WaitForSingleObject(ctypes.c_void_p(alca), 30_000) != 0:
                raise FalhaNoBuild("O processo do .exe não terminou em 30s depois do taskkill.")
    finally:
        for alca in alcas:
            kernel32.CloseHandle(ctypes.c_void_p(alca))


def _abrir_e_esperar_janela(
    ambiente: dict[str, str], log: Path, ocorrencia: int, *, exe: Path = EXE, pasta_atual: Path | None = None
) -> float:
    """Abre o `.exe`, espera a `ocorrencia`-ésima "Janela principal aberta" e o encerra."""
    inicio = time.monotonic()
    processo = subprocess.Popen([str(exe)], env=ambiente, cwd=pasta_atual)
    try:
        while time.monotonic() - inicio < SEGUNDOS_ESPERANDO_A_JANELA:
            texto = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            if "ERROR" in texto or "CRITICAL" in texto:
                raise FalhaNoBuild(f"O .exe registrou erro no log:\n{texto}")
            if texto.count("Janela principal aberta") >= ocorrencia:
                return time.monotonic() - inicio
            if processo.poll() is not None:
                raise FalhaNoBuild(f"O .exe fechou sozinho (código {processo.returncode}). Log:\n{texto}")
            time.sleep(0.5)
        raise FalhaNoBuild(f"A janela não abriu em {SEGUNDOS_ESPERANDO_A_JANELA}s.")
    finally:
        _encerrar_arvore(processo)


def prova_de_fumaca() -> None:
    trabalho = Path.home() / ".gestor_comercial" / NOME_DO_BANCO
    antes = {sufixo: _assinatura(Path(f"{trabalho}{sufixo}")) for sufixo in ("", "-wal")}
    produtos_da_semente = _contar(SEMENTE / "banco_seed.db", "SELECT COUNT(*) FROM produtos")
    fotos_da_semente = len(list((SEMENTE / "thumbnails").iterdir()))

    pasta = Path(tempfile.mkdtemp(prefix="gestor_fumaca_"))
    try:
        appdata = pasta / "AppData" / "Roaming"
        temporaria = pasta / "Temp"
        isca = pasta / "banco_antigo" / NOME_DO_BANCO
        for criar in (appdata, temporaria):
            criar.mkdir(parents=True)
        ambiente = {
            **os.environ,
            "APPDATA": str(appdata),
            "TEMP": str(temporaria),
            "TMP": str(temporaria),
            "GESTOR_COMERCIAL_DB": str(isca),
        }
        dados = appdata / NOME_DA_PASTA_DE_PRODUCAO
        banco = dados / NOME_DO_BANCO
        log = dados / "logs" / "gestor.log"

        segundos = _abrir_e_esperar_janela(ambiente, log, ocorrencia=1)
        print(f"  primeira abertura: janela em {segundos:.1f}s")
        produtos = _contar(banco, "SELECT COUNT(*) FROM produtos")
        fotos = len(list((dados / SUBPASTA_DAS_FOTOS).iterdir()))
        if produtos != produtos_da_semente or fotos != fotos_da_semente:
            raise FalhaNoBuild(
                f"Banco provisionado diverge da semente: produtos {produtos}/{produtos_da_semente}, "
                f"fotos {fotos}/{fotos_da_semente}"
            )
        print(f"  banco criado da semente em {banco}: {produtos} produtos, {fotos} fotos")
        if "banco criado a partir da semente" not in log.read_text(encoding="utf-8"):
            raise FalhaNoBuild("O log não registrou a criação do banco a partir da semente.")
        if isca.parent.exists():
            raise FalhaNoBuild(f"O .exe seguiu GESTOR_COMERCIAL_DB e criou {isca.parent}")
        print("  GESTOR_COMERCIAL_DB ignorada: nenhum arquivo criado no caminho da isca")

        with closing(sqlite3.connect(banco)) as conexao:
            conexao.execute("INSERT INTO preferencias (chave, valor) VALUES ('prova_de_fumaca', 'viva')")
            conexao.commit()
        segundos = _abrir_e_esperar_janela(ambiente, log, ocorrencia=2)
        print(f"  segunda abertura: janela em {segundos:.1f}s")
        marca = _contar(banco, "SELECT COUNT(*) FROM preferencias WHERE chave = 'prova_de_fumaca'")
        if marca != 1 or "banco existente preservado" not in log.read_text(encoding="utf-8"):
            raise FalhaNoBuild("A segunda abertura não preservou o banco existente.")
        print("  banco existente preservado na segunda abertura")

        depois = {sufixo: _assinatura(Path(f"{trabalho}{sufixo}")) for sufixo in ("", "-wal")}
        if antes != depois:
            raise FalhaNoBuild(f"O banco de trabalho {trabalho} foi alterado durante a prova: {antes} -> {depois}")
        print(f"  banco de trabalho intocado: {trabalho}")
    finally:
        for _ in range(10):
            shutil.rmtree(pasta, ignore_errors=True)
            if not pasta.exists():
                break
            time.sleep(1)


def _arquivos(pasta: Path) -> set[str]:
    return {caminho.relative_to(pasta).as_posix() for caminho in pasta.rglob("*") if caminho.is_file()}


def montar_pasta_do_pendrive() -> None:
    """`App_Pendrive/`: o `.exe`, o banco limpo e as fotos, prontos para copiar.

    Montada ao lado e trocada de nome no fim: um build que falha no meio não
    deixa uma pasta pela metade com cara de pronta.
    """
    banco = PENDRIVE / NOME_DO_BANCO
    if banco.is_file():
        vendas = {tabela: linhas for tabela, linhas in contar_movimento(banco).items() if linhas}
        if vendas:
            raise FalhaNoBuild(
                f"{banco} já tem venda gravada ({vendas}) — alguém usou o programa de dentro dela. "
                "Ela não é sobrescrita: tire essa pasta daí (ou guarde o banco) e gere de novo."
            )
    montando = PENDRIVE.with_name(f"{PENDRIVE.name}.montando")
    shutil.rmtree(montando, ignore_errors=True)
    fotos = montando / SUBPASTA_DAS_FOTOS
    fotos.mkdir(parents=True)
    shutil.copy2(EXE, montando / EXE.name)
    shutil.copyfile(SEMENTE / ARQUIVO_DO_BANCO_SEMENTE, montando / NOME_DO_BANCO)
    for foto in sorted((SEMENTE / PASTA_DAS_FOTOS_DA_SEMENTE).iterdir()):
        shutil.copyfile(foto, fotos / foto.name)
    (montando / "LEIA-ME.txt").write_text(LEIA_ME_DO_PENDRIVE, encoding="utf-8-sig", newline="\r\n")
    if PENDRIVE.exists():
        shutil.rmtree(PENDRIVE)
    montando.rename(PENDRIVE)

    tamanho = sum((PENDRIVE / nome).stat().st_size for nome in _arquivos(PENDRIVE))
    print(f"  {PENDRIVE}: {len(_arquivos(PENDRIVE))} arquivos, {tamanho / 1e6:.1f} MB")


def prova_do_modo_portatil() -> None:
    entregue = _arquivos(PENDRIVE)
    produtos_da_semente = _contar(SEMENTE / ARQUIVO_DO_BANCO_SEMENTE, "SELECT COUNT(*) FROM produtos")
    fotos_da_semente = len(list((SEMENTE / PASTA_DAS_FOTOS_DA_SEMENTE).iterdir()))

    pasta = Path(tempfile.mkdtemp(prefix="gestor_pendrive_"))
    try:
        appdata = pasta / "AppData" / "Roaming"
        temporaria = pasta / "Temp"
        fora = pasta / "PastaAtual"
        isca = pasta / "banco_antigo" / NOME_DO_BANCO
        for criar in (appdata, temporaria, fora):
            criar.mkdir(parents=True)
        ambiente = {
            **os.environ,
            "APPDATA": str(appdata),
            "TEMP": str(temporaria),
            "TMP": str(temporaria),
            VARIAVEL_DO_BANCO: str(isca),
        }

        pendrive = pasta / "E" / PENDRIVE.name
        shutil.copytree(PENDRIVE, pendrive)
        log = pendrive / "logs" / "gestor.log"
        segundos = _abrir_e_esperar_janela(ambiente, log, 1, exe=pendrive / EXE.name, pasta_atual=fora)
        print(f"  primeira abertura (pendrive): janela em {segundos:.1f}s")
        esperado = f"banco existente preservado ({pendrive.resolve() / NOME_DO_BANCO})"
        if esperado not in log.read_text(encoding="utf-8"):
            raise FalhaNoBuild(f"O .exe não usou o banco ao lado dele. Esperado no log: {esperado}")
        produtos = _contar(pendrive / NOME_DO_BANCO, "SELECT COUNT(*) FROM produtos")
        fotos = len(list((pendrive / SUBPASTA_DAS_FOTOS).iterdir()))
        if produtos != produtos_da_semente or fotos != fotos_da_semente:
            raise FalhaNoBuild(f"Pasta portátil diverge da semente: produtos {produtos}, fotos {fotos}")
        print(f"  banco ao lado do .exe em uso: {produtos} produtos, {fotos} fotos")
        vazamentos = [p for p in (appdata / NOME_DA_PASTA_DE_PRODUCAO, isca.parent) if p.exists()]
        vazamentos += [fora / nome for nome in _arquivos(fora)]
        if vazamentos:
            raise FalhaNoBuild(f"O .exe portátil gravou fora da própria pasta: {vazamentos}")
        print("  nada gravado no APPDATA, na pasta atual do processo nem no GESTOR_COMERCIAL_DB")

        with closing(sqlite3.connect(pendrive / NOME_DO_BANCO)) as conexao:
            conexao.execute("INSERT INTO preferencias (chave, valor) VALUES ('prova_portatil', 'viva')")
            conexao.commit()
        copiada = pasta / "C" / "GestorComercial"
        copiada.parent.mkdir()
        pendrive.rename(copiada)
        segundos = _abrir_e_esperar_janela(
            ambiente, copiada / "logs" / "gestor.log", 2, exe=copiada / EXE.name, pasta_atual=fora
        )
        print(f"  segunda abertura (pasta movida para {copiada}): janela em {segundos:.1f}s")
        marca = _contar(copiada / NOME_DO_BANCO, "SELECT COUNT(*) FROM preferencias WHERE chave = 'prova_portatil'")
        if marca != 1 or (appdata / NOME_DA_PASTA_DE_PRODUCAO).exists():
            raise FalhaNoBuild("Com a pasta movida, o .exe não achou o próprio banco.")
        print("  pasta movida: o .exe achou o mesmo banco no lugar novo")

        if _arquivos(PENDRIVE) != entregue:
            raise FalhaNoBuild(f"A prova alterou a pasta entregue {PENDRIVE}")
        print(f"  {PENDRIVE} intocada pela prova ({len(entregue)} arquivos)")
    finally:
        for _ in range(10):
            shutil.rmtree(pasta, ignore_errors=True)
            if not pasta.exists():
                break
            time.sleep(1)


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Gera e valida o .exe de produção.")
    parser.add_argument("--sem-testes", action="store_true", help="pula a suíte (só para iterar no empacotamento)")
    parser.add_argument("--origem", type=Path, help="banco de onde sai a semente (padrão: o de trabalho)")
    argumentos = parser.parse_args()
    ambiente_do_build = None
    if argumentos.origem is not None:
        if not argumentos.origem.is_file():
            print(f"\nBUILD REPROVADO: banco de origem não encontrado: {argumentos.origem}", file=sys.stderr)
            return 1
        ambiente_do_build = {**os.environ, VARIAVEL_DO_BANCO: str(argumentos.origem.resolve())}
    try:
        if not ICONE.is_file():
            etapa("Ícone")
            rodar(PYTHON, RAIZ / "packaging" / "gerar_icone.py")
        if not argumentos.sem_testes:
            etapa("Testes")
            rodar(PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider")
        etapa("Build")
        rodar(
            PYTHON, "-m", "PyInstaller", "--clean", "--noconfirm", RAIZ / "packaging" / "app.spec",
            ambiente=ambiente_do_build,
        )
        if not EXE.is_file():
            raise FalhaNoBuild(f"O PyInstaller terminou sem gerar {EXE}")
        print(f"  {EXE} ({EXE.stat().st_size / 1e6:.1f} MB)")
        etapa("Prova de fumaça")
        prova_de_fumaca()
        etapa("Pasta do pendrive")
        montar_pasta_do_pendrive()
        etapa("Prova do modo portátil")
        prova_do_modo_portatil()
    except FalhaNoBuild as erro:
        print(f"\nBUILD REPROVADO: {erro}", file=sys.stderr)
        return 1
    print(f"\nBUILD APROVADO: {EXE}\n                {PENDRIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
