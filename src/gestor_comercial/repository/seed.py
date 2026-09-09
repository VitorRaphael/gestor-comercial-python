from decimal import Decimal

from sqlalchemy.orm import Session

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.repository.base import SessionLocal
from gestor_comercial.repository.preferencia_repository import (
    BOOTSTRAP_CONCLUIDO,
    SIM,
    PreferenciaRepository,
)

TOTAL_MESAS = 60

# Substituem o antigo usuário genérico "Gerente" (single-user bootstrap):
# agora o primeiro boot já cria os dois operadores reais de turno do food
# truck, cada um com perfil GERENTE (abrir/fechar caixa exige perfil
# gerencial em `AuthService.exigir_gerente`, ver caixa_service.abrir()).
#
# Os dois compartilham o mesmo PIN de login (decisão do Vitor, 2026-09-05):
# a Senha Operacional (Gerente) da Central de Loja, "26407200" — mesmo valor
# de `LojaConfigService.SENHA_OPERACIONAL_PADRAO` (não importado daqui para
# não inverter a camada repository->services; ver auth_service.login_como,
# que resolve login por operador SELECIONADO + PIN, não só por PIN, já que
# o PIN sozinho não distingue mais os dois operadores).
NOME_CAIXA_MANHA = "Caixa Turno - Manhã"
TURNO_HORARIO_MANHA = "T1 · Manhã · 08h–16h"

NOME_CAIXA_NOITE = "Caixa Turno - Noite"
TURNO_HORARIO_NOITE = "T2 · Noite · 16h–00h"

PIN_CAIXA_PADRAO = "26407200"

# Cardápio portado do Gestor Comercial (Java). Combos ficam de fora
# propositalmente: só fazem sentido depois que todos os itens já
# existirem, para montá-los a partir dos produtos já cadastrados.
CARDAPIO = {
    "Lanches": {
        "Cachorro Quente Linguiça": "14",
        "Cachorro Quente Salsicha": "14",
        "Scooby Cheddar": "18",
        "X Bacon Cheddar Duplo": "16",
        "X Bacon Duplo": "16",
        "X Bacon Frango": "19",
        "X Bacon Picanha": "22",
        "X Burguer": "13",
        "X Egg Burguer": "15",
        "X Egg Frango": "20",
        "X Egg Picanha": "22",
        "X Gostosão Cheddar Duplo": "15",
        "X Gostosão Duplo": "15",
        "X Missão Impossível": "28",
        "X Scooby": "23",
        "X Scooby Cheddar": "23",
        "X Tudo": "16",
        "X Tudo Cheddar Duplo": "20",
        "X Tudo Duplo": "20",
        "X Tudo Frango": "23",
        "X Tudo Picanha": "25",
        "Doçura": "15",
        "Insano Triplo Picanha": "32",
    },
    "Porções": {
        "Aipim": "20",
        "Anel de Cebola": "12",
        "Batata G Cheddar/Bacon": "27",
        "Batata G Simples": "20",
        "Batata P Simples": "10",
        "Camarão Frito": "60",
        "Carne de Sol Acebolada": "65",
        "Frango Passarinho 1kg": "70",
        "Linguiça Mineira Acebolada": "30",
    },
    "Yakisoba": {
        "Yakisoba Carne": "24",
        "Yakisoba Frango": "22",
        "Yakisoba Misto": "24",
        "Yakisoba Camarão": "32",
        "Yakisoba Legumes": "19",
    },
    "Adicionais Lanches": {
        "Carne Smash": "4",
        "Carne Artesanal": "8",
        "Carne Gran-Filé": "3.5",
        "Ovo Extra": "3.5",
        "Cheddar": "2.5",
        "Cheddar Cremoso": "8",
    },
    "Acompanhamentos": {
        "Arroz": "10",
        "Farofa": "5",
        "Feijão": "10",
        "Vinagrete": "5",
        "Salada de Maionese": "12",
    },
    "Adicionais Açaí": {
        "Banana": "4",
        "Creme de Cupuaçu": "4",
        "Morango": "4",
        "Kiwi": "4",
        "Nutella": "6",
    },
    "Pasteis": {
        "Pastel De Carne": "4",
        "Pastel De Camarão": "6",
        "Pastel De Queijo": "4",
        "Pastel De Carne Seca c/Catupiry": "12",
        "Pastel De Camarão 4un": "20",
    },
    "Jantinhas Gril": {
        "Grill 1 Espeto": "26",
        "Grill 2 Espetos": "36",
        "Picanha/Medalhão 1 Espeto": "32",
        "Picanha/Medalhão 2 Espetos": "48",
    },
    "Bebidas": {
        "Água c/Gás": "4",
        "Água s/Gás": "3.5",
        "Chopp Vinho 300ml": "8",
        "Coca 1,5L": "13",
        "Coca 2L": "16",
        "Coca Zero 2L": "16",
        "Coca Lata": "8",
        "Coca Lata Zero": "8",
        "Coca KS": "7",
        "Fanta Laranja Lata": "8",
        "Fanta Uva Lata": "8",
        "Guaracamp": "3.5",
        "Guaraná 1,5L": "14",
        "Guaraná Lata": "8",
        "Guaraná Zero Lata": "7",
        "H2O": "9",
        "Schweeps Lata": "6",
        "Sprite Lata": "8",
        "Suco Laranja 300ml": "9",
        "Suco Laranja 1L": "25",
    },
    "Drinks": {
        "Caipirinha Abacaxi/Limão 500ml": "15",
        "Caipivodka Abacaxi/Limão/Maracujá/Morango 500ml": "18",
    },
    "Doses": {
        "Dose Bananinha": "5",
        "Dose Milho": "5",
        "Dose Mineira": "5",
    },
    "Caldos": {
        "Bobó de Camarão": "22",
        "Angu à Baiana": "18",
        "Feijão Amigo 300ml": "15",
        "Feijão Amigo 500ml": "20",
        "Caldo de Legumes": "15",
        "Mocotó": "20",
        "Caldo de Pinto": "17",
        "Vaca Atolada": "17",
        "Caldo Verde": "15",
        "Sopa de Ervilha 300ml": "15",
        "Sopa de Ervilha 500ml": "20",
    },
    "Milk-Shake": {
        "Milk-Shake Morango": "14",
        "Milk-Shake Chocolate": "14",
        "Milk-Shake Kit Kat": "16",
        "Milk-Shake Nutella": "22",
        "Milk-Shake Oreo": "16",
        "Milk-Shake Ovomaltine": "18",
        "Milk-Shake Paçoca": "16",
    },
    "Doces": {
        "Chiclete Blong": "0.5",
        "Paçoca": "1",
        "Pingo de Leite": "1",
        "Paçoca Caseira": "3",
    },
}

# Combos portados do Gestor Comercial (Java), categoria "Combos".
# Combo Casal Smash e Combo Casal Xtudo ficaram de fora: estavam
# inativos no Java e com composição quebrada/vazia lá.
CATEGORIA_COMBOS = "Combos"
COMBOS = {
    "Combo Fritas + Coca Cola Lata": {
        "preco": "15",
        "itens": {"Batata P Simples": 1, "Coca KS": 1},
    },
    "Combo Fritas + Guaracamp": {
        "preco": "11",
        "itens": {"Batata P Simples": 1, "Guaracamp": 1},
    },
    "Combo Fritas + Coca Cola KS": {
        "preco": "14",
        "itens": {"Batata P Simples": 1, "Coca KS": 1},
    },
    # Sem composição cadastrada no Java (descrição original: "Morango
    # ou Chocolate"). Composição abaixo é uma escolha nossa (Morango
    # como padrão) — ajuste se o Vitor preferir outro sabor/critério.
    "Milk-Shake 300ml + Fritas": {
        "preco": "15",
        "descricao": "Morango ou Chocolate",
        "itens": {"Batata P Simples": 1, "Milk-Shake Morango": 1},
    },
}


def seed_mesas(session: Session) -> None:
    existentes = {m.numero for m in session.query(Mesa.numero).all()}
    for numero in range(1, TOTAL_MESAS + 1):
        if numero not in existentes:
            session.add(Mesa(numero=numero))


def seed_usuarios_turno(session: Session) -> None:
    # Sem PIN pessoal (§3.13, cascata unificada): o `Usuario` só existe pra
    # identificar QUEM está logando no dropdown da tela de login — a senha
    # em si (Nível 1, padrão "26407200") vive em `LojaConfig`, bootstrapada
    # por `LojaConfigService.obter_ou_criar()`, não aqui.
    if session.query(Usuario).count() > 0:
        return
    for nome in (NOME_CAIXA_MANHA, NOME_CAIXA_NOITE):
        session.add(
            Usuario(
                nome=nome,
                perfil=PerfilUsuario.GERENTE,
            )
        )


def seed_funcionarios_turno(session: Session) -> None:
    # Idempotente por nome (não por contagem): precisa rodar tanto num boot
    # fresco quanto numa instalação existente que só ganhou os dois
    # `Usuario` via migração de dados (d3f8a1c4e6b9) e ainda não tem os
    # `Funcionario` correspondentes pra aparecer na tela Funcionários.
    existentes = {
        f.nome for f in session.query(Funcionario.nome).filter(
            Funcionario.nome.in_([NOME_CAIXA_MANHA, NOME_CAIXA_NOITE])
        )
    }
    for nome, turno_horario in (
        (NOME_CAIXA_MANHA, TURNO_HORARIO_MANHA),
        (NOME_CAIXA_NOITE, TURNO_HORARIO_NOITE),
    ):
        if nome not in existentes:
            session.add(
                Funcionario(
                    nome=nome,
                    cargo="Caixa",
                    ativo=True,
                    saldo_devedor=Decimal("0"),
                    turno_horario=turno_horario,
                )
            )


def seed_cardapio(session: Session) -> None:
    categorias_existentes = {c.nome: c for c in session.query(Categoria).all()}
    produtos_existentes = {p.nome for p in session.query(Produto.nome).all()}

    for nome_categoria, itens in CARDAPIO.items():
        categoria = categorias_existentes.get(nome_categoria)
        if categoria is None:
            categoria = Categoria(nome=nome_categoria)
            session.add(categoria)
            session.flush()
            categorias_existentes[nome_categoria] = categoria

        for nome_produto, preco in itens.items():
            if nome_produto not in produtos_existentes:
                session.add(
                    Produto(
                        nome=nome_produto,
                        preco=Decimal(preco),
                        categoria_id=categoria.id,
                    )
                )
                produtos_existentes.add(nome_produto)


def seed_combos(session: Session) -> None:
    categoria = session.query(Categoria).filter_by(nome=CATEGORIA_COMBOS).first()
    if categoria is None:
        categoria = Categoria(nome=CATEGORIA_COMBOS)
        session.add(categoria)
        session.flush()

    produtos_por_nome = {p.nome: p for p in session.query(Produto).all()}
    combos_existentes = {p.nome for p in session.query(Produto.nome).all()}

    for nome_combo, dados in COMBOS.items():
        if nome_combo in combos_existentes:
            continue

        combo = Produto(
            nome=nome_combo,
            preco=Decimal(dados["preco"]),
            descricao=dados.get("descricao"),
            categoria_id=categoria.id,
            is_combo=True,
        )
        session.add(combo)
        session.flush()

        for nome_item, quantidade in dados["itens"].items():
            componente = produtos_por_nome[nome_item]
            session.add(
                ComboItem(
                    quantidade=quantidade,
                    combo_id=combo.id,
                    produto_id=componente.id,
                )
            )


def bootstrap_ja_rodou(session: Session) -> bool:
    """O banco já foi povoado alguma vez?

    A marca é uma linha em `preferencias` (ver `PreferenciaRepository`), e não
    "a tabela tem registros": contar linhas é justamente o que trouxe o defeito
    de volta — apagar tudo faria a contagem zerar e o seed reabastecer.
    """
    return PreferenciaRepository(session).existe(BOOTSTRAP_CONCLUIDO)


def run_seed() -> None:
    """Povoa o banco recém-criado — **uma vez, e nunca mais**.

    ## Por que a marca existe

    Cada `seed_*` daqui é idempotente por conta própria: `seed_mesas` só
    acrescenta a mesa que falta, `seed_cardapio` pula o produto cujo nome já
    existe, `seed_funcionarios_turno` pula o turno já cadastrado. Idempotente,
    porém, é o mesmo que **restaurador**: um registro que o Vitor apagou na
    tela deixa de existir, o seed do boot seguinte não o encontra, conclui que
    "falta" e o cria de novo.

    Foi exatamente o defeito relatado — o operador de turno excluído em
    Funcionários reaparecia no boot seguinte —, e ele não era só dos turnos: o
    produto e a categoria excluídos no Cardápio voltavam pelo mesmo caminho, e
    a mesa também voltaria se alguma tela apagasse mesa.

    A marca troca o critério de "o que falta no banco" por "este banco já
    nasceu": gravada no primeiro boot bem-sucedido, ela faz toda abertura
    seguinte sair na primeira linha, sem consultar nem gravar nada. Uma
    exclusão feita pelo usuário passa a ser definitiva, que é o que uma
    exclusão significa.

    Banco novo continua nascendo completo (60 mesas, cardápio, dois turnos):
    quem instalou o programa hoje não perde nada. Quem já tinha banco recebe a
    marca pela migração `a4c9f1d70b52`, sem reprocessar o seed.
    """
    with SessionLocal() as session:
        if bootstrap_ja_rodou(session):
            return
        seed_mesas(session)
        seed_usuarios_turno(session)
        seed_funcionarios_turno(session)
        seed_cardapio(session)
        seed_combos(session)
        # A marca entra no MESMO commit do que ela marca: se a energia cair no
        # meio, ou o cardápio inteiro está gravado e marcado, ou nada está — e
        # no segundo caso o boot seguinte refaz o povoamento do zero, que é o
        # comportamento certo para um banco que nunca chegou a nascer.
        PreferenciaRepository(session).definir(BOOTSTRAP_CONCLUIDO, SIM)
        session.commit()


if __name__ == "__main__":
    run_seed()
