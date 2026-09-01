from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.repository.base import Base


class Usuario(Base):
    """Quem loga no sistema com PIN (§3.1). Não confundir com `Funcionario`
    (atendimento, sem login) — ver docs/arquitetura.md §3.1/§3.11."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    perfil: Mapped[PerfilUsuario] = mapped_column(Enum(PerfilUsuario), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    comandas: Mapped[list["Comanda"]] = relationship(
        foreign_keys="Comanda.usuario_id", back_populates="usuario"
    )
    comandas_canceladas: Mapped[list["Comanda"]] = relationship(
        foreign_keys="Comanda.cancelado_por_id", back_populates="cancelado_por"
    )
    itens_cancelados: Mapped[list["ItemComanda"]] = relationship(back_populates="cancelado_por")
    movimentos_caixa: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="usuario")
    caixas_abertos: Mapped[list["Caixa"]] = relationship(
        foreign_keys="Caixa.aberto_por_id", back_populates="aberto_por"
    )
    caixas_fechados: Mapped[list["Caixa"]] = relationship(
        foreign_keys="Caixa.fechado_por_id", back_populates="fechado_por"
    )
    quitacoes_autorizadas: Mapped[list["QuitacaoConsumo"]] = relationship(back_populates="autorizado_por")
