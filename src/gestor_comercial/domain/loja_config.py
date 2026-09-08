from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gestor_comercial.repository.base import Base


class LojaConfig(Base):
    """Configuração única da loja: cascata de 3 níveis de PIN — Senha de
    Login (Nível 1), Senha Operacional/Caixa (Nível 2), Senha Master/Dono
    (Nível 3) — e CPF do Dono (§3.13, módulo "Senhas e Acesso").

    Singleton (sempre id=1, ver `LojaConfigRepository.obter`). Guarda só
    hash+salt de cada segredo — igual ao PIN antigo de `Usuario`, agora
    removido — porque nenhuma tela precisa exibir o valor real de volta, só
    confirmar que o que foi digitado bate com o que está cadastrado. A tela
    sempre mostra `••••••••` no lugar do valor.

    Cascata (nível acima autentica onde nível abaixo é pedido): quem digita a
    Senha Master passa também onde a Operacional ou a de Login é exigida;
    quem digita a Operacional passa também onde a de Login é exigida. Ver
    `AuthService.validar_pin_nivel`.
    """

    __tablename__ = "loja_config"

    id: Mapped[int] = mapped_column(primary_key=True)

    senha_master_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    senha_master_salt: Mapped[str] = mapped_column(String(64), nullable=False)

    senha_operacional_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    senha_operacional_salt: Mapped[str] = mapped_column(String(64), nullable=False)

    # Nível 1 — desbloqueia o terminal na tela de login, visualização do
    # mapa de mesas e abertura de comandas. Nome da coluna mantido como
    # "senha_login" (não "senha_nivel_1") para casar com o rótulo de tela
    # "Senha de Login" e com o padrão de nomes já usado pelas outras duas.
    senha_login_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    senha_login_salt: Mapped[str] = mapped_column(String(64), nullable=False)

    # Quantos caracteres tem cada senha — NÃO a senha, só o comprimento.
    #
    # Existe para o teclado de PIN (`ui/widgets/pin_pad_dialog.py`) desenhar a
    # fileira de marcadores do tamanho certo ANTES de o operador digitar: um
    # hash é via de mão única e não devolve o comprimento do que gerou ele, e
    # sem este campo a tela mostrava seis bolinhas para a Senha Operacional de
    # oito dígitos.
    #
    # `NULL` significa "não sabemos": banco anterior a esta coluna cuja senha
    # daquele nível já tinha sido trocada (a migração só preencheu os níveis
    # que ainda estavam na senha de fábrica, que ela consegue conferir contra o
    # hash). Quem lê trata `NULL` como "use o piso padrão", e o valor certo
    # entra sozinho na próxima troca de senha.
    #
    # O que isto entrega a quem tiver o arquivo do banco na mão: saber que a
    # senha tem N dígitos. Irrelevante na prática — são 4 a 8 dígitos
    # numéricos, que um ataque offline percorre inteiro em segundos com ou sem
    # esta coluna, e a própria tela do PIN mostra a contagem a quem estiver de
    # pé na frente do monitor.
    senha_master_tamanho: Mapped[int | None] = mapped_column(Integer)
    senha_operacional_tamanho: Mapped[int | None] = mapped_column(Integer)
    senha_login_tamanho: Mapped[int | None] = mapped_column(Integer)

    # CPF do dono é opcional até o primeiro cadastro (§ bootstrap) — sem
    # senha master ainda definida por ele mesmo, não há como exigir "CPF
    # atual" na primeira vez.
    cpf_dono_hash: Mapped[str | None] = mapped_column(String(128))
    cpf_dono_salt: Mapped[str | None] = mapped_column(String(64))
    cpf_dono_definido: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
