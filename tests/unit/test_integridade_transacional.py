"""A fronteira transacional dos services — `REMASTERIZACAO-V1.md` §3.1.

O `UnitOfWork` promete na própria docstring: "ou as três coisas são gravadas,
ou nenhuma é: `commit()` no fim do service, `rollback()` se qualquer regra
estourar". Até a Fase 1 da Remasterização essa segunda metade não existia:
`rollback()` só era chamado em `UnitOfWork.__exit__`, e `with UnitOfWork(...)`
não era usado em lugar nenhum do projeto.

O resultado era uma operação rejeitada por regra de negócio ficar pendurada na
Session e ser gravada pelo `commit()` da **operação seguinte**, que não tinha
nada a ver com ela. Num sistema que movimenta dinheiro, isso é o defeito mais
grave que a auditoria encontrou.

Estes testes travam as propriedades que a correção precisa ter — as primeiras
são o defeito, e as últimas são o que a correção **não pode
quebrar** ao consertá-lo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.exceptions import AcessoNegadoError, RegraDeNegocioError


@pytest.fixture
def cardapio(uow, auth):
    return CardapioService(uow, auth)


@pytest.fixture
def impressora_gravada(cardapio, gerente):
    impressora = cardapio.criar_impressora(
        nome="Cozinha",
        tipo_conexao=TipoConexaoImpressora.ARQUIVO,
        caminho_arquivo="c:/tmp/cupom.txt",
    )
    return impressora


def test_operacao_abortada_nao_persiste_no_commit_seguinte(uow, cardapio, impressora_gravada):
    """O defeito do §3.1, no caminho exato em que foi reproduzido.

    Editar a impressora com nome novo + host inválido: o service muta
    `impressora.nome` e só depois valida a conexão, então quando a regra estoura
    o nome novo já está sujo na Session. Sem rollback, o `commit()` de uma
    operação seguinte — aqui, cadastrar uma categoria — grava também esse nome.
    """
    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_impressora(
            impressora_gravada.id,
            nome="NOME QUE NAO DEVIA PERSISTIR",
            tipo_conexao=TipoConexaoImpressora.REDE,
            host="",  # inválido de propósito
        )

    # Operação sem nenhuma relação com a anterior. O commit dela não pode
    # arrastar junto o que a operação rejeitada deixou para trás.
    cardapio.criar_categoria("Bebidas")

    uow.session.expire_all()
    relida = uow.impressoras.buscar_por_id(impressora_gravada.id)
    assert relida.nome == "Cozinha", (
        "A edição rejeitada foi gravada pelo commit de outra operação — "
        "o rollback do §3.1 não está acontecendo."
    )


def test_sessao_nao_fica_travada_apos_erro_de_integridade(uow, cardapio, gerente):
    """Erro do banco não pode inutilizar o app até reiniciar o processo.

    Um `IntegrityError` deixa a Session em estado de rollback pendente: toda
    operação seguinte falha com `PendingRollbackError` até alguém chamar
    `rollback()`. Este teste prova que a recuperação funciona — é o par do
    teste acima, que cobre o caso em que ninguém chama.
    """
    cardapio.criar_categoria("Lanches")

    # Mesmo nome: viola o `unique=True` de `Categoria.nome`. O erro estoura já
    # no `flush()` de `salvar`, antes mesmo do commit.
    with pytest.raises(IntegrityError):
        uow.categorias.salvar(Categoria(nome="Lanches"))
    uow.rollback()

    # O app tem de continuar utilizável depois disso.
    categoria = cardapio.criar_categoria("Bebidas")
    assert categoria.id is not None
    assert {c.nome for c in cardapio.listar_categorias()} == {"Lanches", "Bebidas"}


def test_app_segue_utilizavel_apos_falha_de_regra_sem_rollback_manual(uow, cardapio, gerente):
    """Depois de uma operação recusada, a tela seguinte tem de funcionar.

    Ninguém na camada de UI chama `rollback()` — as views só capturam o erro do
    service e mostram a mensagem. Então a Session precisa voltar limpa sozinha,
    sem o chamador saber que isso é necessário.
    """
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_categoria("")

    # `IdentitySet` não compara com `set()`, então a verificação é de vazio.
    assert not uow.session.new
    assert not uow.session.dirty
    assert not uow.session.deleted

    categoria = cardapio.criar_categoria("Bebidas")
    assert categoria.id is not None


def test_chave_estrangeira_e_aplicada_pelo_banco(uow):
    """As 38 `ForeignKey` do `domain/` precisam valer de verdade — §3.5.

    O SQLite nasce com `PRAGMA foreign_keys` **desligado**, e a configuração
    vale por conexão (não fica gravada no arquivo). Sem o listener de
    `repository/base.py`, as FKs eram decoração: dava para gravar comanda de um
    caixa que não existe, item de um produto apagado, pagamento de comanda
    inexistente — e o estrago só apareceria semanas depois, como relatório que
    não fecha.
    """
    ligada = uow.session.execute(text("PRAGMA foreign_keys")).scalar()
    assert ligada == 1, "PRAGMA foreign_keys está desligado — o listener não rodou"

    # `usuario_id` e `caixa_id` apontam para linhas que não existem. Todas as
    # demais colunas obrigatórias vão preenchidas de propósito: assim o erro só
    # pode ser de chave estrangeira, e não um NOT NULL disfarçado.
    with pytest.raises(IntegrityError) as capturado:
        uow.session.execute(
            text(
                "INSERT INTO comandas (status, aberta_em, valor_desconto, usuario_id, caixa_id) "
                "VALUES ('ABERTA', '2026-09-06 10:00:00', 0, 9999, 9999)"
            )
        )
        uow.session.flush()
    assert "FOREIGN KEY" in str(capturado.value.orig).upper(), (
        f"O INSERT falhou, mas não por chave estrangeira: {capturado.value.orig}"
    )
    uow.rollback()


def test_unit_of_work_como_context_manager_desfaz_ao_estourar(session):
    """O `__exit__` que o `main.py` passou a usar precisa desfazer de verdade.

    Antes da Fase 1 este caminho existia mas era código morto: `with
    UnitOfWork(...)` não aparecia em lugar nenhum do projeto. Agora o `main.py`
    depende dele para o app não encerrar deixando escrita pendente.
    """
    from gestor_comercial.repository.unit_of_work import UnitOfWork

    with pytest.raises(RuntimeError):
        with UnitOfWork(session=session) as uow:
            uow.categorias.salvar(Categoria(nome="Nunca gravada"))
            raise RuntimeError("algo estourou depois da escrita")

    assert not session.new
    assert not session.dirty
    assert session.query(Categoria).filter_by(nome="Nunca gravada").first() is None


def test_cascata_de_pin_continua_funcionando(auth, gerente):
    """Guarda-corpo da correção, não do defeito.

    A cascata de 3 níveis usa exceção como **fluxo normal**:
    `senha_*_confere` chama `validar_senha_*` e captura `AcessoNegadoError` para
    devolver `False`. Uma senha errada é evento rotineiro, não falha de
    operação. Se a correção do §3.1 fizesse rollback em qualquer exceção, toda
    digitação errada de PIN passaria a descartar trabalho pendente.
    """
    loja = auth.loja_config

    assert loja.senha_master_confere("000000") is False
    assert loja.senha_operacional_confere("000000") is False
    assert loja.senha_login_confere("000000") is False

    with pytest.raises(AcessoNegadoError):
        loja.validar_senha_master("000000")

    # E o caminho feliz segue intacto depois de todas essas recusas.
    assert loja.senha_master_confere("050727") is True


def test_erro_de_regra_nao_descarta_o_que_ja_foi_comitado(uow, cardapio, gerente):
    """Rollback não pode ir longe demais: o que já foi comitado está gravado.

    Descartar alterações pendentes é o objetivo; desfazer venda já concluída
    seria uma regressão pior que o defeito original.
    """
    cardapio.criar_categoria("Lanches")
    categoria_salva = cardapio.criar_categoria("Bebidas")

    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto(nome="", preco=Decimal("10.00"), categoria_id=categoria_salva.id)

    uow.session.expire_all()
    assert {c.nome for c in cardapio.listar_categorias()} == {"Lanches", "Bebidas"}
