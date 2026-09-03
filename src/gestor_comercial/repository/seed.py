import base64
import hashlib
import os
from decimal import Decimal

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.repository.base import SessionLocal

TOTAL_MESAS = 60
ADMIN_NOME = "Gerente"
ADMIN_PIN_PADRAO = "264072"

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


def gerar_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def hash_pin(pin: str, salt: str) -> str:
    salt_bytes = base64.b64decode(salt)
    digest = hashlib.sha256(salt_bytes + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def seed_mesas(session) -> None:
    existentes = {m.numero for m in session.query(Mesa.numero).all()}
    for numero in range(1, TOTAL_MESAS + 1):
        if numero not in existentes:
            session.add(Mesa(numero=numero))


def seed_usuario_admin(session) -> None:
    if session.query(Usuario).count() > 0:
        return
    salt = gerar_salt()
    session.add(
        Usuario(
            nome=ADMIN_NOME,
            pin_hash=hash_pin(ADMIN_PIN_PADRAO, salt),
            salt=salt,
            perfil=PerfilUsuario.GERENTE,
        )
    )


def seed_cardapio(session) -> None:
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


def seed_combos(session) -> None:
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


def run_seed() -> None:
    with SessionLocal() as session:
        seed_mesas(session)
        seed_usuario_admin(session)
        seed_cardapio(session)
        seed_combos(session)
        session.commit()


if __name__ == "__main__":
    run_seed()
