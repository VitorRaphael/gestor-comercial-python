"""Testes da fronteira com o python-escpos (`hardware/impressora_escpos.py`).

A impressora é fingida com um `SimpleNamespace` de propósito: a camada
`hardware/` não importa `domain/` em runtime, então testar com um objeto solto
prova essa independência e deixa o teste rodar sem banco e sem hardware.
"""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import gestor_comercial
from gestor_comercial.hardware import impressora_escpos
from gestor_comercial.hardware.impressora_escpos import (
    COLUNAS_PADRAO,
    BlocoTexto,
    ErroDeImpressao,
    abrir_driver,
)


def impressora_falsa(**campos):
    """Impressora com todos os campos do cadastro, para o teste sobrescrever só o que importa."""
    padrao = dict(
        nome="Cozinha",
        tipo_conexao="ARQUIVO",
        vendor_id=None,
        product_id=None,
        porta_serial=None,
        baudrate=None,
        host=None,
        porta_rede=None,
        nome_fila=None,
        caminho_arquivo=None,
        colunas=48,
        ativa=True,
        padrao=True,
    )
    padrao.update(campos)
    return SimpleNamespace(**padrao)


def test_arquivo_grava_cupom_legivel(tmp_path):
    destino = tmp_path / "cupons" / "cozinha.txt"
    impressora = impressora_falsa(caminho_arquivo=str(destino))

    with abrir_driver(impressora) as driver:
        driver.imprimir(
            [
                BlocoTexto("Comanda 12", negrito=True, centralizado=True),
                BlocoTexto("MESA 7", dobro=True, centralizado=True),
                BlocoTexto("2x X-Burger"),
            ]
        )

    conteudo = destino.read_text(encoding="utf-8")
    assert "COMANDA 12" in conteudo  # negrito vira maiúscula no arquivo
    assert "M E S A   7" in conteudo  # dobro vira letra espaçada
    assert "2x X-Burger" in conteudo
    assert "CORTE" in conteudo


def test_arquivo_acumula_cupons_em_vez_de_sobrescrever(tmp_path):
    destino = tmp_path / "cozinha.txt"
    impressora = impressora_falsa(caminho_arquivo=str(destino))

    for numero in ("Comanda 1", "Comanda 2"):
        with abrir_driver(impressora) as driver:
            driver.imprimir([BlocoTexto(numero)])

    conteudo = destino.read_text(encoding="utf-8")
    assert "Comanda 1" in conteudo and "Comanda 2" in conteudo


def test_usb_sem_vendor_id(tmp_path):
    impressora = impressora_falsa(tipo_conexao="USB", product_id="0x0202")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "Vendor ID" in str(erro.value)


def test_tipo_de_conexao_desconhecido():
    impressora = impressora_falsa(tipo_conexao="BLUETOOTH")

    with pytest.raises(ErroDeImpressao):
        with abrir_driver(impressora):
            pass


def test_serial_sem_porta():
    impressora = impressora_falsa(tipo_conexao="SERIAL")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "porta" in str(erro.value)


def test_usb_com_id_que_nao_e_hexadecimal():
    impressora = impressora_falsa(tipo_conexao="USB", vendor_id="cabo", product_id="0x0202")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "hexadecimal" in str(erro.value)


def test_rede_sem_host():
    impressora = impressora_falsa(tipo_conexao="REDE")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "endereço" in str(erro.value)


def test_windows_sem_o_nome_da_fila():
    impressora = impressora_falsa(tipo_conexao="WINDOWS")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "Dispositivos e Impressoras" in str(erro.value)


def test_windows_com_fila_inexistente_nao_vaza_excecao_da_biblioteca():
    """Sem pywin32 avisa o que instalar; com ele, a fila inexistente falha na
    conexão. Nos dois caminhos o que atravessa a fronteira é ErroDeImpressao."""
    impressora = impressora_falsa(tipo_conexao="WINDOWS", nome_fila="Fila Que Nao Existe")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "Cozinha" in str(erro.value)


def test_serial_com_baudrate_ilegivel():
    impressora = impressora_falsa(tipo_conexao="SERIAL", porta_serial="COM3", baudrate="rápido")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "inteiro" in str(erro.value)


def test_sem_tipo_de_conexao_cadastrado():
    impressora = impressora_falsa(tipo_conexao=None)

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora):
            pass

    assert "tipo de conexão" in str(erro.value)


def test_rede_com_porta_fechada_vira_mensagem_para_o_operador():
    """Cabo/IP errado tem que estourar aqui, antes de gastar papel — e com o
    timeout curto que a decisão de arquitetura da Fase 4 exige."""
    # Porta 1 em localhost recusa a conexão na hora: prova o tratamento de erro
    # sem depender de rede nem esperar timeout.
    impressora = impressora_falsa(tipo_conexao="REDE", host="127.0.0.1", porta_rede=1)

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora, timeout_s=1.0):
            pass

    assert "Cozinha" in str(erro.value)
    assert "ligada" in str(erro.value)


# ----------------------------------------------------------------------
# Modo ARQUIVO: o que permite testar a venda inteira sem impressora
# ----------------------------------------------------------------------


def test_arquivo_sem_caminho_cai_na_pasta_padrao(tmp_path, monkeypatch):
    monkeypatch.setattr(impressora_escpos, "PASTA_CUPONS_PADRAO", tmp_path)
    # Barra e dois-pontos no nome viram nome de arquivo válido: o gerente
    # batiza a impressora como quiser, sem saber o que o Windows aceita.
    impressora = impressora_falsa(nome="Bar/Chapa", caminho_arquivo=None)

    with abrir_driver(impressora) as driver:
        driver.imprimir([BlocoTexto("Comanda 1")])

    assert (tmp_path / "Bar_Chapa.txt").read_text(encoding="utf-8").count("Comanda 1") == 1


def test_arquivo_em_caminho_impossivel_vira_erro_legivel(tmp_path):
    ocupado = tmp_path / "ocupado.txt"
    ocupado.write_text("não sou pasta", encoding="utf-8")
    impressora = impressora_falsa(caminho_arquivo=str(ocupado / "cupom.txt"))

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora) as driver:
            driver.imprimir([BlocoTexto("Comanda 1")])

    assert "Confira o caminho cadastrado" in str(erro.value)


def test_arquivo_quebra_o_que_nao_cabe_na_bobina(tmp_path):
    """O .txt mostra o mesmo estrago que o papel mostraria."""
    destino = tmp_path / "cozinha.txt"
    impressora = impressora_falsa(caminho_arquivo=str(destino), colunas=32)

    with abrir_driver(impressora) as driver:
        driver.imprimir(
            [BlocoTexto("Combo Especial da Casa com Fritas Grandes e Refrigerante gelado")]
        )

    # A 1ª linha é o carimbo que separa um cupom do outro no arquivo, não papel.
    linhas = destino.read_text(encoding="utf-8").splitlines()[1:]
    assert all(len(linha) <= 32 for linha in linhas)
    assert any("Combo Especial" in linha for linha in linhas)


def test_largura_absurda_no_cadastro_cai_no_padrao(tmp_path):
    """Zero ou NULL em `colunas` não pode derrubar a impressão inteira."""
    destino = tmp_path / "cozinha.txt"
    impressora = impressora_falsa(caminho_arquivo=str(destino), colunas=0)

    with abrir_driver(impressora) as driver:
        driver.imprimir([BlocoTexto("palavra " * 20)])

    linhas = [linha for linha in destino.read_text(encoding="utf-8").splitlines() if linha]
    assert all(len(linha) <= COLUNAS_PADRAO for linha in linhas)
    # Alguma linha passa de 32: provou que usou as 48 do padrão, e não o piso.
    assert any(len(linha) > 32 for linha in linhas)


def test_importar_o_sistema_nao_carrega_o_escpos():
    """RNF de otimização (§2): o boot do app não paga o custo do python-escpos.

    O import da biblioteca é tardio, dentro de `_abrir_conexao_escpos`. Só um
    processo limpo prova isso — nesta sessão de teste os casos acima já
    carregaram o escpos.
    """
    raiz_src = Path(gestor_comercial.__file__).resolve().parent.parent
    codigo = (
        "import sys; import gestor_comercial.services.impressao_service as s; "
        "print('escpos' in sys.modules)"
    )

    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(raiz_src)},
    )

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


# ----------------------------------------------------------------------
# Bytes ESC/POS de verdade: o que o modo ARQUIVO e o driver falso não cobrem
# ----------------------------------------------------------------------

# ESC ! n — comando de tamanho de texto. 0x00 é o normal, 0x30 é altura+largura
# dupla. São os dois bytes que este bloco de testes persegue.
TAMANHO_NORMAL = b"\x1b!\x00"
TAMANHO_DOBRO = b"\x1b!0"


def _bytes_do_cupom(documento):
    """Renderiza o documento no `Dummy` do python-escpos e devolve os bytes crus."""
    from escpos.printer import Dummy

    dummy = Dummy()
    impressora_escpos._DriverEscpos(dummy, "Cozinha").imprimir(documento)
    return dummy.output


def test_bloco_em_dobro_volta_ao_tamanho_normal_no_bloco_seguinte():
    """O `set()` do python-escpos só manda comando de tamanho quando algum dos
    três parâmetros de tamanho é verdadeiro. Sem passar `normal_textsize`, o
    dobro do número da mesa ligava e nunca desligava: o cupom inteiro (e o
    próximo) sairiam dobrados e cortados pela largura da bobina."""
    saida = _bytes_do_cupom(
        [
            BlocoTexto("MESA 7", dobro=True, centralizado=True),
            BlocoTexto("2x X-Burger", negrito=True),
        ]
    )

    posicao_dobro = saida.find(TAMANHO_DOBRO)
    assert posicao_dobro != -1, "o bloco em dobro nem chegou a ligar o tamanho duplo"
    assert TAMANHO_NORMAL in saida[posicao_dobro:], (
        "nada devolveu a impressora ao tamanho normal depois do bloco em dobro"
    )


def test_cupom_termina_no_tamanho_normal_para_nao_contaminar_o_proximo():
    """A impressora guarda o estilo entre trabalhos: se o cupom terminar em
    dobro, o recibo do cliente seguinte sai dobrado até alguém tirar da tomada."""
    saida = _bytes_do_cupom([BlocoTexto("MESA 7", dobro=True)])

    assert saida.rfind(TAMANHO_NORMAL) > saida.rfind(TAMANHO_DOBRO)


def test_cupom_comeca_reinicializando_a_impressora():
    """ESC @ no começo: cupom anterior que morreu no meio (papel acabou, cabo
    caiu) deixa estilo ligado na memória da impressora."""
    saida = _bytes_do_cupom([BlocoTexto("Comanda 1")])

    assert saida.startswith(b"\x1b@")


# ----------------------------------------------------------------------
# Limites de tempo: nada pode ficar pendurado na thread da UI
# ----------------------------------------------------------------------


class _SerialFalsa:
    """Dublê do `escpos.printer.Serial` que guarda como foi construído."""

    ultima = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        # `device` é o objeto do pyserial de verdade: é nele que mora o
        # write_timeout, porque o escpos não repassa esse parâmetro.
        self.device = SimpleNamespace(write_timeout=None)
        _SerialFalsa.ultima = self

    @staticmethod
    def is_usable():
        return True

    def open(self):
        pass

    def close(self):
        pass


def test_serial_e_aberta_com_limite_de_escrita(monkeypatch):
    """No pyserial `timeout` limita só a leitura. Sem `write_timeout`, imprimir
    numa COM3 com a impressora desligada bloqueia para sempre — e como a
    impressão roda na thread da UI, a janela do PDV congela sem exceção nenhuma
    para capturar."""
    import escpos.printer

    monkeypatch.setattr(escpos.printer, "Serial", _SerialFalsa)
    impressora = impressora_falsa(tipo_conexao="SERIAL", porta_serial="COM3")

    with abrir_driver(impressora, timeout_s=3.0):
        pass

    assert _SerialFalsa.ultima.kwargs["timeout"] == 3.0
    assert _SerialFalsa.ultima.device.write_timeout == 3.0
    # Controle de fluxo por hardware ligado (o default do escpos) faz o write
    # esperar um DSR que a impressora desligada nunca manda.
    assert _SerialFalsa.ultima.kwargs["dsrdtr"] is False


class _Win32RawFalsa:
    """Dublê do Win32Raw onde o job só é efetivado (e só falha) no `close()`."""

    @staticmethod
    def is_usable():
        return True

    def __init__(self, **kwargs):
        pass

    def open(self):
        pass

    def hw(self, _comando):
        pass

    def set(self, **kwargs):
        pass

    def textln(self, _texto):
        pass

    def cut(self):
        pass

    def close(self):
        raise OSError("O spooler de impressão não está em execução")


def test_falha_ao_finalizar_o_job_do_windows_vira_erro_de_impressao(monkeypatch):
    """No Win32Raw é o `close()` que faz EndDocPrinter, ou seja, é ele que
    entrega o papel. Engolir esse erro faria o service devolver sucesso, marcar
    `impresso_em` e esconder para sempre um pedido que nunca saiu."""
    import escpos.printer

    monkeypatch.setattr(escpos.printer, "Win32Raw", _Win32RawFalsa)
    impressora = impressora_falsa(tipo_conexao="WINDOWS", nome_fila="Cozinha")

    with pytest.raises(ErroDeImpressao) as erro:
        with abrir_driver(impressora) as driver:
            driver.imprimir([BlocoTexto("Comanda 1")])

    assert "spooler" in str(erro.value).lower()
    assert "2ª via" in str(erro.value)
