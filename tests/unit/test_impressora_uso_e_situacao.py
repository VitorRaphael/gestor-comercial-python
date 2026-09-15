"""O "Uso da impressão" e a "Situação" do cartão de impressora, no service. §9.19.

Duas decisões do Vitor, perguntadas antes de começar, e as duas moram aqui:

1. **"Uso da impressão" grava a marca de padrão**, e só ela. "Recibo do cliente"
   é `padrao=True`, e a antiga padrão perde a marca **no mesmo commit**;
   "Produção (por categoria)" é `padrao=False`. Schema intacto;
2. **"Impressora ativa" existe também no cadastro**, e impressora desligada
   nunca é a padrão — pedida ou não.

`padrao=None` e `ativa=None` (na edição) continuam sendo "não mexe", e
`criar_impressora("Cozinha")` sem nada continua valendo a regra de sempre: os
testes dela estão em `test_cardapio_service.py` e não foram tocados.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gestor_comercial.domain.enums import PerfilUsuario, TipoConexaoImpressora
from gestor_comercial.repository.base import Base
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.exceptions import RegraDeNegocioError
from tests.conftest import PIN_GERENTE


@pytest.fixture
def cardapio(uow, auth, gerente):
    return CardapioService(uow, auth)


def _marcadas(cardapio: CardapioService) -> list[str]:
    return [impressora.nome for impressora in cardapio.listar_impressoras() if impressora.padrao]


# ----------------------------------------------------------------------
# Situação: `ativa` no cadastro
# ----------------------------------------------------------------------


def test_o_cadastro_nasce_ativo_por_padrao(cardapio):
    assert cardapio.criar_impressora("Caixa 01").ativa is True


def test_o_cadastro_pode_nascer_desligado(cardapio):
    impressora = cardapio.criar_impressora("Caixa 01", ativa=False)

    assert impressora.ativa is False


def test_desligada_no_cadastro_nao_herda_a_padrao_vaga(cardapio, uow):
    """A regra antiga marcaria a primeira impressora como padrão. Desligada, ela
    não pode: o recibo iria para um destino que o gerente acabou de desligar."""
    impressora = cardapio.criar_impressora("Caixa 01", ativa=False)

    assert impressora.padrao is False
    assert uow.impressoras.buscar_padrao() is None


def test_desligada_no_cadastro_nao_vira_padrao_nem_pedindo(cardapio):
    """A regra de proteção do pedido: "force padrao = 0"."""
    impressora = cardapio.criar_impressora("Caixa 01", ativa=False, padrao=True)

    assert impressora.padrao is False


# ----------------------------------------------------------------------
# Uso: `padrao` explícito
# ----------------------------------------------------------------------


def test_recibo_no_cadastro_tira_a_marca_da_antiga(cardapio, uow):
    antiga = cardapio.criar_impressora("Balcão")
    assert antiga.padrao is True, "premissa: a primeira nasce padrão"

    nova = cardapio.criar_impressora("Caixa 01", padrao=True)

    assert nova.padrao is True
    assert antiga.padrao is False
    assert _marcadas(cardapio) == ["Caixa 01"]
    assert uow.impressoras.buscar_padrao().id == nova.id


def test_producao_no_cadastro_recusa_a_padrao_vaga(cardapio, uow):
    """Escolha explícita vence a regra automática: "Produção" é produção, mesmo
    sendo a primeira. É o cartão que avisa "Sem impressora de recibo"."""
    impressora = cardapio.criar_impressora("Cozinha", padrao=False)

    assert impressora.padrao is False
    assert uow.impressoras.buscar_padrao() is None


def test_recibo_na_edicao_tira_a_marca_da_outra(cardapio):
    balcao = cardapio.criar_impressora("Balcão")
    cozinha = cardapio.criar_impressora("Cozinha")

    cardapio.editar_impressora(cozinha.id, "Cozinha", padrao=True)

    assert _marcadas(cardapio) == ["Cozinha"]
    assert balcao.padrao is False


def test_producao_na_edicao_tira_a_marca_da_propria(cardapio, uow):
    balcao = cardapio.criar_impressora("Balcão")

    cardapio.editar_impressora(balcao.id, "Balcão", padrao=False)

    assert balcao.padrao is False
    assert uow.impressoras.buscar_padrao() is None


def test_edicao_sem_padrao_nao_mexe_na_marca(cardapio):
    """`padrao=None` é "não mexe": quem só renomeia não pode perder nem ganhar
    o recibo por tabela."""
    balcao = cardapio.criar_impressora("Balcão")
    cozinha = cardapio.criar_impressora("Cozinha")

    cardapio.editar_impressora(balcao.id, "Balcão Novo")
    cardapio.editar_impressora(cozinha.id, "Cozinha Nova")

    assert _marcadas(cardapio) == ["Balcão Novo"]


def test_desligar_na_edicao_vence_o_pedido_de_recibo(cardapio):
    balcao = cardapio.criar_impressora("Balcão")

    cardapio.editar_impressora(balcao.id, "Balcão", ativa=False, padrao=True)

    assert balcao.padrao is False


def test_nunca_ficam_duas_marcadas(cardapio):
    nomes = ["Balcão", "Cozinha", "Bar"]
    impressoras = [cardapio.criar_impressora(nome) for nome in nomes]

    for impressora in impressoras + list(reversed(impressoras)):
        cardapio.editar_impressora(impressora.id, impressora.nome, padrao=True)
        assert _marcadas(cardapio) == [impressora.nome]


@pytest.fixture
def em_arquivo(tmp_path):
    """Service sobre um banco em ARQUIVO, e uma segunda conexão para espiar.

    O banco da suíte é `:memory:`, e cada conexão a `:memory:` é um banco
    diferente — não há como outra conexão ver o que foi gravado. Em arquivo, a
    segunda conexão enxerga só o que já foi COMMITADO, que é exatamente o que um
    corte de energia deixaria no disco.
    """
    caminho = tmp_path / "gestor.db"
    engine = create_engine(f"sqlite:///{caminho}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as sessao:
        uow = UnitOfWork(session=sessao)
        auth = AuthService(uow)
        usuario = auth.criar_usuario("Gerente", PerfilUsuario.GERENTE)
        auth.login_como(usuario.id, PIN_GERENTE)
        espia = sqlite3.connect(caminho)
        try:
            yield CardapioService(uow, auth), uow, espia
        finally:
            espia.close()
    engine.dispose()


def test_a_troca_de_padrao_e_um_commit_so(em_arquivo, monkeypatch):
    """"Gravação transacional atômica": a antiga padrão perde a marca no MESMO
    commit em que a nova a ganha. No instante do commit, o disco ainda mostra a
    antiga marcada; depois dele, só a nova. Com dois commits (gravar e depois
    `definir_padrao`) haveria um momento, no disco, com duas marcadas ou nenhuma —
    e um corte de energia ali deixaria o recibo sem destino."""
    cardapio, uow, espia = em_arquivo
    cardapio.criar_impressora("Balcão")
    cozinha = cardapio.criar_impressora("Cozinha")
    commit_de_verdade = uow.commit
    no_disco_na_hora_do_commit: list[list[str]] = []

    def commit_espiado() -> None:
        no_disco_na_hora_do_commit.append(
            [nome for (nome,) in espia.execute("SELECT nome FROM impressoras WHERE padrao = 1")]
        )
        commit_de_verdade()

    monkeypatch.setattr(uow, "commit", commit_espiado)
    cardapio.editar_impressora(cozinha.id, "Cozinha", padrao=True)

    assert no_disco_na_hora_do_commit == [["Balcão"]], "a edição fez mais de um commit"
    assert [nome for (nome,) in espia.execute("SELECT nome FROM impressoras WHERE padrao = 1")] == [
        "Cozinha"
    ]


def test_erro_de_conexao_nao_deixa_a_marca_trocada(cardapio, uow):
    """O parâmetro inválido estoura antes do commit, e o `@transacional` desfaz:
    a outra impressora não pode ter perdido a marca no caminho."""
    balcao = cardapio.criar_impressora("Balcão")
    cozinha = cardapio.criar_impressora("Cozinha")

    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_impressora(
            cozinha.id, "Cozinha", TipoConexaoImpressora.USB, vendor_id="zz", product_id="0x0202", padrao=True
        )

    uow.session.expire_all()
    assert _marcadas(cardapio) == ["Balcão"]
    assert balcao.padrao is True


def test_definir_padrao_continua_valendo(cardapio):
    """`definir_padrao` passou a usar a mesma rotina da marca: o botão "Definir
    como padrão" da tela não pode ter mudado de comportamento."""
    cardapio.criar_impressora("Balcão")
    cozinha = cardapio.criar_impressora("Cozinha")

    cardapio.definir_padrao(cozinha.id)

    assert _marcadas(cardapio) == ["Cozinha"]
