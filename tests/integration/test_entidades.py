from datetime import datetime
from decimal import Decimal

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import (
    FormaPagamento,
    PerfilFuncionario,
    StatusCaixa,
    StatusComanda,
    StatusMesa,
    TipoMovimento,
)
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.domain.produto import Produto
from gestor_comercial.domain.quitacao_consumo import QuitacaoConsumo


def test_funcionario(session):
    func = Funcionario(nome="Gerente", pin_hash="h", salt="s", perfil=PerfilFuncionario.GERENTE)
    session.add(func)
    session.commit()

    salvo = session.query(Funcionario).one()
    assert salvo.nome == "Gerente"
    assert salvo.perfil == PerfilFuncionario.GERENTE
    assert salvo.ativo is True
    assert salvo.saldo_devedor == Decimal("0")


def test_mesa(session):
    mesa = Mesa(numero=1)
    session.add(mesa)
    session.commit()

    salva = session.query(Mesa).one()
    assert salva.numero == 1
    assert salva.status == StatusMesa.LIVRE


def test_impressora_e_categoria(session):
    impressora = Impressora(nome="Cozinha")
    session.add(impressora)
    session.flush()

    categoria = Categoria(nome="Lanches", impressora_id=impressora.id)
    session.add(categoria)
    session.commit()

    salva = session.query(Categoria).one()
    assert salva.nome == "Lanches"
    assert salva.impressora.nome == "Cozinha"
    assert impressora.categorias == [salva]


def test_produto_e_combo_item(session):
    categoria = Categoria(nome="Lanches")
    session.add(categoria)
    session.flush()

    componente = Produto(nome="Pão", preco=Decimal("2.00"), categoria_id=categoria.id)
    combo = Produto(nome="Combo X", preco=Decimal("20.00"), categoria_id=categoria.id, is_combo=True)
    session.add_all([componente, combo])
    session.flush()

    item = ComboItem(quantidade=1, combo_id=combo.id, produto_id=componente.id)
    session.add(item)
    session.commit()

    salvo = session.query(ComboItem).one()
    assert salvo.combo.nome == "Combo X"
    assert salvo.produto.nome == "Pão"
    assert combo.componentes == [salvo]


def test_caixa_e_movimento_caixa(session):
    func = Funcionario(nome="Atendente", pin_hash="h", salt="s", perfil=PerfilFuncionario.ATENDENTE)
    session.add(func)
    session.flush()

    caixa = Caixa(valor_abertura=Decimal("100.00"))
    session.add(caixa)
    session.flush()

    movimento = MovimentoCaixa(
        tipo=TipoMovimento.REFORCO,
        valor=Decimal("50.00"),
        registrado_em=datetime(2026, 8, 20, 10, 0),
        caixa_id=caixa.id,
        funcionario_id=func.id,
    )
    session.add(movimento)
    session.commit()

    salvo = session.query(MovimentoCaixa).one()
    assert salvo.tipo == TipoMovimento.REFORCO
    assert salvo.caixa.status == StatusCaixa.ABERTO
    assert caixa.movimentos == [salvo]


def test_comanda_item_e_pagamento(session):
    func = Funcionario(nome="Atendente", pin_hash="h", salt="s", perfil=PerfilFuncionario.ATENDENTE)
    mesa = Mesa(numero=5)
    caixa = Caixa(valor_abertura=Decimal("100.00"))
    categoria = Categoria(nome="Lanches")
    session.add_all([func, mesa, caixa, categoria])
    session.flush()

    produto = Produto(nome="X-Burger", preco=Decimal("18.00"), categoria_id=categoria.id)
    session.add(produto)
    session.flush()

    comanda = Comanda(
        aberta_em=datetime(2026, 8, 20, 12, 0),
        mesa_id=mesa.id,
        funcionario_id=func.id,
        caixa_id=caixa.id,
    )
    session.add(comanda)
    session.flush()

    item = ItemComanda(
        quantidade=2,
        preco_unit_congelado=produto.preco,
        comanda_id=comanda.id,
        produto_id=produto.id,
    )
    pagamento = Pagamento(
        forma=FormaPagamento.PIX,
        valor=Decimal("36.00"),
        registrado_em=datetime(2026, 8, 20, 12, 30),
        comanda_id=comanda.id,
    )
    session.add_all([item, pagamento])
    session.commit()

    salva = session.query(Comanda).one()
    assert salva.status == StatusComanda.ABERTA
    assert salva.mesa.numero == 5
    assert len(salva.itens) == 1
    assert salva.itens[0].produto.nome == "X-Burger"
    assert len(salva.pagamentos) == 1
    assert salva.pagamentos[0].forma == FormaPagamento.PIX


def test_pagamento_consumo_interno_e_quitacao_consumo(session):
    atendente = Funcionario(nome="Atendente", pin_hash="h", salt="s", perfil=PerfilFuncionario.ATENDENTE)
    gerente = Funcionario(nome="Gerente", pin_hash="h", salt="s", perfil=PerfilFuncionario.GERENTE)
    caixa = Caixa(valor_abertura=Decimal("100.00"))
    session.add_all([atendente, gerente, caixa])
    session.flush()

    comanda = Comanda(
        aberta_em=datetime(2026, 8, 20, 13, 0),
        funcionario_id=atendente.id,
        caixa_id=caixa.id,
    )
    session.add(comanda)
    session.flush()

    pagamento = Pagamento(
        forma=FormaPagamento.CONSUMO_INTERNO,
        valor=Decimal("15.00"),
        registrado_em=datetime(2026, 8, 20, 13, 10),
        comanda_id=comanda.id,
        funcionario_consumo_id=atendente.id,
    )
    quitacao = QuitacaoConsumo(
        valor_quitado=Decimal("15.00"),
        quitado_em=datetime(2026, 8, 21, 9, 0),
        funcionario_id=atendente.id,
        autorizado_por_id=gerente.id,
    )
    session.add_all([pagamento, quitacao])
    session.commit()

    salvo_pagamento = session.query(Pagamento).one()
    assert salvo_pagamento.funcionario_consumo.nome == "Atendente"

    salva_quitacao = session.query(QuitacaoConsumo).one()
    assert salva_quitacao.funcionario.nome == "Atendente"
    assert salva_quitacao.autorizado_por.nome == "Gerente"
    assert atendente.pagamentos_consumo == [salvo_pagamento]
    assert atendente.quitacoes == [salva_quitacao]
