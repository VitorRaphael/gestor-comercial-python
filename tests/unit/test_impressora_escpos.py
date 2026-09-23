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

# GS ! n — o tamanho do caractere (§9.30): nibble alto é a largura, baixo a
# altura, cada um "multiplicador - 1". 0x00 é o normal, 0x11 o dobro, 0x22 o
# triplo e 0x33 o quádruplo. É o único comando de tamanho que o driver manda.
TAMANHO_NORMAL = b"\x1d!\x00"
TAMANHO_DOBRO = b"\x1d!\x11"
TAMANHO_POR_ESCALA = {2: b"\x1d!\x11", 3: b"\x1d!\x22", 4: b"\x1d!\x33"}


def _bytes_do_cupom(documento, **opcoes):
    """Renderiza o documento no `Dummy` do python-escpos e devolve os bytes crus."""
    from escpos.printer import Dummy

    dummy = Dummy()
    impressora_escpos._DriverEscpos(dummy, "Cozinha", **opcoes).imprimir(documento)
    return dummy.output


def _pedacos_por_texto(saida: bytes, textos: list[str]) -> list[bytes]:
    """Os comandos que antecedem cada linha de texto, linha por linha."""
    pedacos, inicio = [], 0
    for texto in textos:
        fim = saida.index(texto.encode("cp437", errors="replace"), inicio)
        pedacos.append(saida[inicio:fim])
        inicio = fim
    return pedacos


def test_bloco_em_dobro_volta_ao_tamanho_normal_no_bloco_seguinte():
    """Cada linha diz o próprio tamanho: sem isso o dobro do número da mesa
    ligava e nunca desligava, e o cupom inteiro (e o próximo) sairiam dobrados
    e cortados pela largura da bobina."""
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
    """A impressora guarda o estilo entre trabalhos: se o cupom terminar
    ampliado, o recibo seguinte sai ampliado até alguém tirar da tomada."""
    saida = _bytes_do_cupom([BlocoTexto("TOTAL", ampliado=True)], escala=4)

    assert saida.rfind(TAMANHO_NORMAL) > saida.rfind(TAMANHO_POR_ESCALA[4])


@pytest.mark.parametrize("escala", [2, 3, 4])
def test_a_linha_ampliada_sai_na_escala_da_impressora(escala):
    """O `GS !` com o multiplicador da impressora antes da linha de destaque,
    e o normal antes da linha comum seguinte."""
    textos = ["TOTAL R$ 46,00", "Obrigado"]
    saida = _bytes_do_cupom(
        [BlocoTexto(textos[0], negrito=True, ampliado=True), BlocoTexto(textos[1])],
        escala=escala,
    )

    destaque, comum = _pedacos_por_texto(saida, textos)
    assert TAMANHO_POR_ESCALA[escala] in destaque
    assert comum.rfind(TAMANHO_NORMAL) > comum.rfind(TAMANHO_POR_ESCALA[escala])


def test_o_tamanho_nao_passa_pelo_esc_exclamacao():
    """`ESC ! n` e `GS ! n` mexem no mesmo tamanho em muitas térmicas, e o
    `ESC ! 0` não zera com segurança o que o `GS !` ligou. O driver usa um
    comando só — e é por isso que o normal volta de verdade depois do 3x."""
    saida = _bytes_do_cupom(
        [BlocoTexto("MESA 7", ampliado=True), BlocoTexto("MESA 8", dobro=True), BlocoTexto("x")],
        escala=3,
    )

    assert b"\x1b!" not in saida


def test_escala_fora_da_faixa_cai_no_dobro():
    """Objeto de teste ou valor mexido à mão não pode estourar o `GS !` (1 a 8)."""
    for bruto in (None, 0, 9, "3", True):
        campos = {} if bruto is None else {"escala_fonte": bruto}
        assert impressora_escpos.escala_de(impressora_falsa(**campos)) == 2
    assert impressora_escpos.escala_de(impressora_falsa(escala_fonte=4)) == 4


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


# ----------------------------------------------------------------------
# Negrito, fonte condensada e escala (§9.22, §9.30)
# ----------------------------------------------------------------------

# ESC E n — ênfase. ESC M 1 — fonte B (condensada).
ENFASE_LIGA = b"\x1bE\x01"
ENFASE_DESLIGA = b"\x1bE\x00"
FONTE_CONDENSADA = b"\x1bM\x01"


def test_so_o_negrito_do_bloco_liga_a_enfase_e_o_fim_desliga():
    """Sem a letra grossa (que saiu no §9.30), a ênfase é só do bloco negrito,
    e o `ESC E 0` sai no fim para o cupom seguinte não herdar."""
    textos = ["Comanda 12", "2x X-Burger"]
    saida = _bytes_do_cupom([BlocoTexto(textos[0], negrito=True), BlocoTexto(textos[1])])

    titulo, item = _pedacos_por_texto(saida, textos)
    assert ENFASE_LIGA in titulo
    assert ENFASE_LIGA not in item
    assert saida.rfind(ENFASE_DESLIGA) > saida.rfind(ENFASE_LIGA)


def test_sem_condensada_nenhum_comando_de_fonte():
    documento = [
        BlocoTexto("Comanda 12", negrito=True, centralizado=True),
        BlocoTexto("MESA 7", ampliado=True, centralizado=True),
        BlocoTexto("2x X-Burger"),
    ]

    assert b"\x1bM" not in _bytes_do_cupom(documento)


def test_condensada_escolhe_a_fonte_b_em_toda_linha():
    """Inclusive a linha ampliada: o tamanho e a fonte são comandos separados."""
    textos = ["Comanda 12", "MESA 7", "2x X-Burger"]
    saida = _bytes_do_cupom(
        [BlocoTexto(textos[0], negrito=True), BlocoTexto(textos[1], ampliado=True), BlocoTexto(textos[2])],
        condensada=True,
        escala=3,
    )

    for pedaco in _pedacos_por_texto(saida, textos):
        assert FONTE_CONDENSADA in pedaco, pedaco


@pytest.mark.parametrize(
    ("colunas", "bobina_mm", "condensada"),
    [(32, 58, False), (42, 58, True), (48, 58, True), (32, 80, False), (48, 80, False), (64, 80, True), (80, 80, True)],
)
def test_a_fonte_condensada_entra_quando_passa_da_fonte_normal_da_bobina(colunas, bobina_mm, condensada):
    assert impressora_escpos.usa_fonte_condensada(colunas, bobina_mm) is condensada


def test_os_parametros_da_thread_levam_bobina_e_escala():
    """O retrato que atravessa para a thread de impressão tem que levar os dois:
    sem eles, a impressão fora da thread da UI sairia na fonte A e em 2x."""
    parametros = impressora_escpos.ParametrosImpressora.de(
        impressora_falsa(colunas=64, bobina_mm=80, escala_fonte=4)
    )

    assert (parametros.colunas, parametros.bobina_mm, parametros.escala_fonte) == (64, 80, 4)


@pytest.mark.parametrize("bobina_mm", [None, 76, "58"])
def test_sem_bobina_valida_os_parametros_ficam_na_de_80mm(bobina_mm):
    """Do banco ela sempre vem. Um objeto solto, ou um valor mexido à mão,
    cai na de 80mm — que nunca liga a condensada para quem cabe em 48."""
    campos = {} if bobina_mm is None else {"bobina_mm": bobina_mm}
    parametros = impressora_escpos.ParametrosImpressora.de(impressora_falsa(**campos))

    assert (parametros.bobina_mm, parametros.escala_fonte) == (80, 2)


def test_a_sessao_de_impressao_entrega_o_formato_ao_driver(monkeypatch):
    """Do cadastro ao papel: `abrir_driver` lê bobina, colunas e escala da
    impressora, e o driver manda a fonte B e o `GS !` da escala."""
    from escpos.printer import Dummy

    dummy = Dummy()
    dummy.close = lambda: None
    monkeypatch.setattr(impressora_escpos, "_abrir_conexao_escpos", lambda *args: dummy)
    impressora = impressora_falsa(tipo_conexao="REDE", host="10.0.0.9", colunas=64, bobina_mm=80, escala_fonte=3)

    with abrir_driver(impressora) as driver:
        driver.imprimir([BlocoTexto("TOTAL", ampliado=True)])

    assert TAMANHO_POR_ESCALA[3] in dummy.output
    assert FONTE_CONDENSADA in dummy.output


@pytest.mark.parametrize(("escala", "esperado"), [(2, "T O T A L"), (3, "T  O  T  A  L"), (4, "T   O   T   A   L")])
def test_arquivo_simula_a_escala_com_letra_espacada(tmp_path, escala, esperado):
    destino = tmp_path / "caixa.txt"
    impressora = impressora_falsa(caminho_arquivo=str(destino), escala_fonte=escala)

    with abrir_driver(impressora) as driver:
        driver.imprimir([BlocoTexto("TOTAL", ampliado=True), BlocoTexto("2x X-Burger")])

    conteudo = destino.read_text(encoding="utf-8")
    assert esperado in conteudo
    assert "2x X-Burger" in conteudo


def test_arquivo_quebra_a_linha_ampliada_na_largura_dividida_pela_escala(tmp_path):
    """Em 4x numa bobina de 32 colunas cabem 8 caracteres: o .txt mostra o
    mesmo estrago que o papel mostraria, e nenhuma linha passa das 32."""
    destino = tmp_path / "caixa.txt"
    impressora = impressora_falsa(caminho_arquivo=str(destino), colunas=32, escala_fonte=4)

    with abrir_driver(impressora) as driver:
        driver.imprimir([BlocoTexto("SOLVIX LANCHES", ampliado=True)])

    linhas = destino.read_text(encoding="utf-8").splitlines()[1:]
    assert "S   O   L   V   I   X" in linhas
    assert all(len(linha) <= 32 for linha in linhas)


def test_o_destaque_atravessa_a_fila_de_contingencia():
    """`ampliado` vai para o JSON e volta: um recibo guardado na fila reimprime
    com o TOTAL em destaque, na escala que a impressora tiver no dia."""
    documento = [BlocoTexto("TOTAL", negrito=True, ampliado=True), BlocoTexto("MESA 3", dobro=True)]

    volta = impressora_escpos.documento_de_json(impressora_escpos.documento_para_json(documento))

    assert volta == documento


# ----------------------------------------------------------------------
# Escala fixa por bloco (§9.31)
# ----------------------------------------------------------------------


class _ConexaoFalsa:
    """Dublê que anota o tamanho pedido em cada `set()`.

    O tamanho é o que interessa aqui: é ele que vira o byte do `GS !`, e o
    driver manda um `set()` por bloco mais um reset antes do corte.
    """

    def __init__(self):
        self.tamanhos: list[int] = []

    def hw(self, _comando):
        pass

    def set(self, **kwargs):
        self.tamanhos.append(kwargs.get("width"))

    def textln(self, _texto):
        pass

    def cut(self):
        pass



def test_a_escala_do_bloco_ganha_da_escala_da_impressora():
    """O cupom de diagnóstico precisa mostrar 1x, 2x, 3x e 4x no MESMO papel.

    É a única exceção à regra de §9.30 (quem manda na escala é o cadastro), e
    existe justamente para provar o cadastro: se as quatro linhas saem iguais,
    a impressora ignora o `GS !`.
    """
    conexao = _ConexaoFalsa()
    driver = impressora_escpos._DriverEscpos(conexao, "Cozinha", escala=2)

    driver.imprimir(
        [
            BlocoTexto("1x", escala=1),
            BlocoTexto("4x", escala=4),
            BlocoTexto("da impressora", ampliado=True),
            BlocoTexto("normal"),
        ]
    )

    assert conexao.tamanhos == [1, 4, 2, 1, 1]  # o último é o reset antes do corte


def test_a_escala_do_bloco_fica_na_faixa_do_comando_escpos():
    """O `GS !` aceita de 1 a 8. Fora disso a impressora receberia lixo."""
    conexao = _ConexaoFalsa()
    driver = impressora_escpos._DriverEscpos(conexao, "Cozinha", escala=2)

    driver.imprimir([BlocoTexto("gigante", escala=99), BlocoTexto("zero", escala=0)])

    assert conexao.tamanhos[:2] == [impressora_escpos.ESCALA_MAXIMA, 1]


def test_a_escala_do_bloco_atravessa_a_fila_de_contingencia():
    documento = [BlocoTexto("3x MESA 12", negrito=True, escala=3), BlocoTexto("normal")]

    volta = impressora_escpos.documento_de_json(impressora_escpos.documento_para_json(documento))

    assert volta == documento


def test_cupom_guardado_antes_da_escala_por_bloco_volta_sem_ela():
    """Fila antiga (JSON sem a chave) reimprime na escala da impressora."""
    volta = impressora_escpos.documento_de_json(
        '[{"texto": "TOTAL", "negrito": true, "ampliado": true}]'
    )

    assert volta == [BlocoTexto("TOTAL", negrito=True, ampliado=True, escala=None)]
