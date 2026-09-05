from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from gestor_comercial.repository.base import Base


class LojaConfig(Base):
    """Configuração única da loja: Senha Master (Dono), Senha Operacional
    (Gerente) e CPF do Dono (§3.13, módulo "Senhas e Acesso").

    Singleton (sempre id=1, ver `LojaConfigRepository.obter`). Guarda só
    hash+salt de cada segredo — igual ao PIN de `Usuario` — porque nenhuma
    tela precisa exibir o valor real de volta, só confirmar que o que foi
    digitado bate com o que está cadastrado. A tela sempre mostra
    `••••••••` no lugar do valor.
    """

    __tablename__ = "loja_config"

    id: Mapped[int] = mapped_column(primary_key=True)

    senha_master_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    senha_master_salt: Mapped[str] = mapped_column(String(64), nullable=False)

    senha_operacional_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    senha_operacional_salt: Mapped[str] = mapped_column(String(64), nullable=False)

    # CPF do dono é opcional até o primeiro cadastro (§ bootstrap) — sem
    # senha master ainda definida por ele mesmo, não há como exigir "CPF
    # atual" na primeira vez.
    cpf_dono_hash: Mapped[str | None] = mapped_column(String(128))
    cpf_dono_salt: Mapped[str | None] = mapped_column(String(64))
    cpf_dono_definido: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
