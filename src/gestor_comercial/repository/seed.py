import base64
import hashlib
import os

from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.repository.base import SessionLocal

TOTAL_MESAS = 60
ADMIN_NOME = "Gerente"
ADMIN_PIN_PADRAO = "264072"


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


def seed_funcionario_admin(session) -> None:
    if session.query(Funcionario).count() > 0:
        return
    salt = gerar_salt()
    session.add(
        Funcionario(
            nome=ADMIN_NOME,
            pin_hash=hash_pin(ADMIN_PIN_PADRAO, salt),
            salt=salt,
            perfil=PerfilFuncionario.GERENTE,
        )
    )


def run_seed() -> None:
    with SessionLocal() as session:
        seed_mesas(session)
        seed_funcionario_admin(session)
        session.commit()


if __name__ == "__main__":
    run_seed()
