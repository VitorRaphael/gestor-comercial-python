"""O que a cópia recuperável promete — e o que ela recusa a prometer.

`services/segredo_reversivel.py` existe para o botão de olho de "Senhas e
Acesso" poder mostrar a senha que o dono cadastrou. A promessa é modesta e está
escrita lá: ofuscação em repouso, não proteção contra quem tem o `.db` e o
programa. O que estes testes trancam é justamente a parte que a tela depende:

* o que entra volta igual, e só com a chave certa;
* texto adulterado no banco devolve `None` em vez de uma senha diferente com
  cara de verdadeira — é a diferença entre "não consegui ler" e mentir;
* nada levanta, nunca: quem chama é um slot de clique, e um estouro ali evapora
  sem mensagem (`core/resilience.py`).
"""

from __future__ import annotations

import base64

import pytest

from gestor_comercial.services.segredo_reversivel import (
    TAMANHO_NONCE_BYTES,
    cifrar,
    decifrar,
    gerar_chave,
)

SENHAS = ["050727", "26407200", "1234", "12345678901"]


@pytest.fixture
def chave():
    return gerar_chave()


@pytest.mark.parametrize("valor", SENHAS)
def test_o_que_entra_volta_igual(chave, valor):
    assert decifrar(cifrar(valor, chave), chave) == valor


def test_acento_e_caractere_fora_do_ascii_sobrevivem(chave):
    """O CPF e as senhas são numéricos hoje, mas a regra só exige 4 caracteres —
    nada impede uma senha com acento, e ela não pode voltar quebrada."""
    valor = "Senha-Ç-Ã-é"
    assert decifrar(cifrar(valor, chave), chave) == valor


def test_o_texto_guardado_nao_contem_o_segredo(chave):
    """A promessa mínima: abrir o `.db` num navegador de SQLite não pode
    mostrar a senha do caixa em texto legível."""
    guardado = cifrar("26407200", chave)
    assert "26407200" not in guardado
    assert b"26407200" not in base64.b64decode(guardado)


def test_cifrar_duas_vezes_da_textos_diferentes(chave):
    """Nonce novo a cada chamada.

    Sem ele, a Senha de Login e a Operacional — que de fábrica são a MESMA —
    sairiam com o mesmo texto no banco, e quem olhasse a tabela saberia disso
    sem decifrar nada.
    """
    assert cifrar("26407200", chave) != cifrar("26407200", chave)


def test_chave_errada_nao_decifra(chave):
    assert decifrar(cifrar("050727", chave), gerar_chave()) is None


def test_texto_adulterado_nao_decifra(chave):
    """Um byte trocado no banco tem que virar `None`, e não outra senha.

    O bit é virado no CORPO cifrado (depois do nonce e do selo), que é onde uma
    adulteração faria diferença: sem o selo conferido antes, o XOR devolveria
    alegremente uma string diferente, e a tela a mostraria como se fosse o
    segredo cadastrado.
    """
    bruto = bytearray(base64.b64decode(cifrar("050727", chave)))
    bruto[-1] ^= 0x01
    assert decifrar(base64.b64encode(bytes(bruto)).decode(), chave) is None


def test_selo_adulterado_nao_decifra(chave):
    bruto = bytearray(base64.b64decode(cifrar("050727", chave)))
    bruto[TAMANHO_NONCE_BYTES] ^= 0x01
    assert decifrar(base64.b64encode(bytes(bruto)).decode(), chave) is None


@pytest.mark.parametrize(
    "lixo",
    ["", "   ", "não é base64!", "YWJj", base64.b64encode(b"curto").decode()],
)
def test_lixo_devolve_none_sem_levantar(chave, lixo):
    """Nada aqui pode levantar: quem chama é uma tela que precisa dizer "não
    consegui recuperar este valor" e seguir viva."""
    assert decifrar(lixo, chave) is None


def test_none_e_tipo_errado_tambem_devolvem_none(chave):
    assert decifrar(None, chave) is None
    assert decifrar(123, chave) is None


def test_cada_chave_gerada_e_diferente():
    assert len({gerar_chave() for _ in range(20)}) == 20
