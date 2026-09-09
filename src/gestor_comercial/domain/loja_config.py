from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gestor_comercial.repository.base import Base


class LojaConfig(Base):
    """Configuração única da loja: cascata de 3 níveis de PIN — Senha de
    Login (Nível 1), Senha Operacional/Caixa (Nível 2), Senha Master/Dono
    (Nível 3) — e CPF do Dono (§3.13, módulo "Senhas e Acesso").

    Singleton (sempre id=1, ver `LojaConfigRepository.obter`). A autenticação
    usa só hash+salt de cada segredo — igual ao PIN antigo de `Usuario`, agora
    removido —, e a tela mostra `••••••••` no lugar do valor.

    Ao lado do hash existe hoje uma **segunda cópia recuperável** de cada
    segredo (colunas `*_cifrada`/`*_cifrado`, ver o bloco no fim desta classe),
    que só o botão de olho de "Senhas e Acesso" lê, e só depois de o CPF do
    Dono ser digitado e conferir. Ela não participa de autenticação nenhuma.

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

    # ------------------------------------------------------------------
    # Cópia recuperável, para o botão de olho de "Senhas e Acesso"
    # ------------------------------------------------------------------
    # A docstring acima diz que nenhuma tela precisa exibir o valor real de
    # volta. Deixou de ser verdade quando o Vitor pediu o olho: quem esquece a
    # Senha Master não tem para onde ir, porque a única credencial acima dela é
    # o CPF do Dono — que é justamente o que o olho exige para revelar.
    #
    # Estas colunas NÃO substituem o hash e não participam de autenticação
    # nenhuma: quem confere o que foi digitado continua sendo `senha_*_hash`.
    # São uma segunda cópia, embaralhada por `services/segredo_reversivel.py`,
    # que só a tela lê e só depois do CPF conferir.
    #
    # `NULL` significa "não temos cópia deste valor": banco anterior a estas
    # colunas cuja senha já tinha sido trocada (a migração `b6e2d80a3f14` só
    # consegue recuperar as que ainda estão na senha de fábrica, conferindo
    # contra o hash — mesma técnica de `c1d5b8e37a42`). A tela mostra
    # "indisponível" e o valor entra sozinho na próxima troca de senha.
    #
    # O que isto entrega a quem tiver o arquivo do banco: ver
    # `segredo_reversivel` — é ofuscação em repouso, não proteção contra quem
    # tem o `.db` e o programa. A barreira de verdade é o CPF na tela.
    senha_master_cifrada: Mapped[str | None] = mapped_column(String(255))
    senha_operacional_cifrada: Mapped[str | None] = mapped_column(String(255))
    senha_login_cifrada: Mapped[str | None] = mapped_column(String(255))
    cpf_dono_cifrado: Mapped[str | None] = mapped_column(String(255))
