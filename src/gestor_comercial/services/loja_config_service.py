"""Módulo "Senhas e Acesso" da Central de Loja (§3.13) — cascata de 3 níveis
de PIN, cada um só podendo ser alterado com o de "nível acima":
- Nível 1 — Senha de Login: desbloqueia o terminal na tela de login (para
  qualquer operador do dropdown), visualização do mapa de mesas e abertura
  de comandas. Alterá-la exige a Senha Operacional OU a Senha Master.
- Nível 2 — Senha Operacional (Caixa): tela "Caixa", gaveta
  (sangria/reforço/fechamento de turno) e autorização de cancelamento/
  estorno. Alterá-la exige a Senha Master.
- Nível 3 — Senha Master (Dono): Central de Loja, relatórios financeiros,
  precificação, cadastro de equipe e configurações do sistema. Alterá-la
  exige o CPF do Dono.
- CPF do Dono — chave mestra. Alterá-lo exige o CPF atual.

Cascata (nível acima autentica onde nível abaixo é pedido): a Senha Master
vale onde a Operacional ou a de Login é exigida; a Operacional vale onde a
de Login é exigida. Ver `AuthService.validar_pin_nivel`.

Nenhum valor é guardado em texto puro, e a AUTENTICAÇÃO usa só hash+salt,
gerados com o mesmo esquema SHA-256+salt (`AuthService.hash_pin`). A tela
mostra `••••••••` no lugar do valor.

"Ver o valor" passou a existir como uma operação separada e mais cara:
`revelar(campo, cpf_dono)`, o botão de olho de "Senhas e Acesso". Ela não
autentica nada — devolve texto para a tela mostrar por alguns segundos — e
cobra o CPF do Dono, a credencial de topo da cascata. Existe porque quem
esquece a Senha Master não tem para onde ir: a única coisa acima dela é o
próprio CPF. O que a torna possível é uma segunda cópia embaralhada de cada
segredo (`domain/loja_config.py`, colunas `*_cifrada`), guardada por
`services/segredo_reversivel.py` — que documenta, sem rodeios, o que essa
cópia protege e o que não protege.
"""

from __future__ import annotations

from gestor_comercial.domain.loja_config import LojaConfig
from gestor_comercial.repository.preferencia_repository import CHAVE_DE_EXIBICAO
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    RegraDeNegocioError,
)
from gestor_comercial.services import segredo_reversivel
from gestor_comercial.services.transacao import transacional

SENHA_MASTER_PADRAO = "050727"
SENHA_OPERACIONAL_PADRAO = "26407200"
SENHA_LOGIN_PADRAO = "26407200"

MASCARA = "••••••••"

# Os quatro segredos que o botão de olho consegue revelar, e a coluna de
# `LojaConfig` onde a cópia recuperável de cada um mora. É esta tabela — e não
# quatro `if` na tela — que decide o que é revelável: acrescentar um segredo
# novo à Central de Loja passa a ser uma linha aqui.
CAMPO_SENHA_LOGIN = "senha_login"
CAMPO_SENHA_OPERACIONAL = "senha_operacional"
CAMPO_SENHA_MASTER = "senha_master"
CAMPO_CPF_DONO = "cpf_dono"

COLUNA_CIFRADA_POR_CAMPO = {
    CAMPO_SENHA_LOGIN: "senha_login_cifrada",
    CAMPO_SENHA_OPERACIONAL: "senha_operacional_cifrada",
    CAMPO_SENHA_MASTER: "senha_master_cifrada",
    CAMPO_CPF_DONO: "cpf_dono_cifrado",
}

ROTULO_POR_CAMPO = {
    CAMPO_SENHA_LOGIN: "Senha de Login",
    CAMPO_SENHA_OPERACIONAL: "Senha Operacional (Gerente)",
    CAMPO_SENHA_MASTER: "Senha Master (Dono)",
    CAMPO_CPF_DONO: "CPF do Dono",
}


@transacional
class LojaConfigService:
    """Bootstrap e regras do módulo "Senhas e Acesso"."""

    _CAMPO_DE_TAMANHO_POR_NIVEL = {
        3: "senha_master_tamanho",
        2: "senha_operacional_tamanho",
        1: "senha_login_tamanho",
    }

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def obter_ou_criar(self) -> LojaConfig:
        """Garante a linha singleton, criando com os padrões de fábrica na
        primeira vez que qualquer tela/serviço tocar no módulo."""
        config = self.uow.loja_config.obter()
        if config is not None:
            return config

        salt_master = AuthService.gerar_salt()
        salt_operacional = AuthService.gerar_salt()
        salt_login = AuthService.gerar_salt()
        config = LojaConfig(
            senha_master_hash=AuthService.hash_pin(SENHA_MASTER_PADRAO, salt_master),
            senha_master_salt=salt_master,
            senha_operacional_hash=AuthService.hash_pin(SENHA_OPERACIONAL_PADRAO, salt_operacional),
            senha_operacional_salt=salt_operacional,
            senha_login_hash=AuthService.hash_pin(SENHA_LOGIN_PADRAO, salt_login),
            senha_login_salt=salt_login,
            senha_master_tamanho=len(SENHA_MASTER_PADRAO),
            senha_operacional_tamanho=len(SENHA_OPERACIONAL_PADRAO),
            senha_login_tamanho=len(SENHA_LOGIN_PADRAO),
            cpf_dono_definido=False,
        )
        # As três senhas de fábrica já entram com cópia recuperável: num banco
        # novo o olho funciona desde o primeiro boot, sem exigir que o Vitor
        # troque a senha uma vez só para poder vê-la. O CPF não tem padrão de
        # fábrica e fica sem cópia até o primeiro cadastro.
        chave = self._chave_de_exibicao()
        config.senha_master_cifrada = segredo_reversivel.cifrar(SENHA_MASTER_PADRAO, chave)
        config.senha_operacional_cifrada = segredo_reversivel.cifrar(SENHA_OPERACIONAL_PADRAO, chave)
        config.senha_login_cifrada = segredo_reversivel.cifrar(SENHA_LOGIN_PADRAO, chave)
        self.uow.loja_config.salvar(config)
        self.uow.commit()
        return config

    def _chave_de_exibicao(self) -> str:
        """A chave que embaralha as cópias recuperáveis, criada no primeiro uso.

        Uma por instalação, guardada em `preferencias` — ver
        `services/segredo_reversivel.py` para por que ela mora no mesmo banco
        que aquilo que ela embaralha, e o que isso significa (e não significa)
        em termos de proteção.
        """
        chave = self.uow.preferencias.obter(CHAVE_DE_EXIBICAO)
        if chave:
            return chave
        chave = segredo_reversivel.gerar_chave()
        self.uow.preferencias.definir(CHAVE_DE_EXIBICAO, chave)
        return chave

    def _guardar_para_exibicao(self, config: LojaConfig, campo: str, valor: str) -> None:
        """Atualiza a cópia recuperável de um campo, no mesmo `config` que a
        troca de senha está prestes a gravar.

        Sem `commit` próprio de propósito: quem chama já vai commitar a troca, e
        as duas coisas têm que ir juntas — hash novo com cópia velha faria o
        olho mostrar a senha ANTERIOR, que é pior que não mostrar nada.
        """
        setattr(
            config,
            COLUNA_CIFRADA_POR_CAMPO[campo],
            segredo_reversivel.cifrar(valor, self._chave_de_exibicao()),
        )

    # ------------------------------------------------------------------
    # Validação (desbloqueio)
    # ------------------------------------------------------------------

    def validar_senha_login(self, senha: str) -> None:
        config = self.obter_ou_criar()
        if not self._confere(senha, config.senha_login_salt, config.senha_login_hash):
            raise AcessoNegadoError("Senha de Login incorreta.")

    def senha_login_confere(self, senha: str) -> bool:
        """Versão que não levanta erro — usada pela cascata de
        `AuthService.validar_pin_nivel` (Nível 3 e 2 também valem no lugar
        do Nível 1)."""
        try:
            self.validar_senha_login(senha)
            return True
        except AcessoNegadoError:
            return False

    def validar_senha_master(self, senha: str) -> None:
        config = self.obter_ou_criar()
        if not self._confere(senha, config.senha_master_salt, config.senha_master_hash):
            raise AcessoNegadoError("Senha Master (Dono) incorreta.")

    def validar_senha_operacional(self, senha: str) -> None:
        config = self.obter_ou_criar()
        if not self._confere(senha, config.senha_operacional_salt, config.senha_operacional_hash):
            raise AcessoNegadoError("Senha Operacional (Gerente) incorreta.")

    def senha_operacional_confere(self, senha: str) -> bool:
        """Versão que não levanta erro — usada por quem aceita ESSA senha OU
        outra credencial como alternativa (ex.: PIN pessoal de gerente)."""
        try:
            self.validar_senha_operacional(senha)
            return True
        except AcessoNegadoError:
            return False

    def senha_master_confere(self, senha: str) -> bool:
        try:
            self.validar_senha_master(senha)
            return True
        except AcessoNegadoError:
            return False

    def tamanho_da_senha(self, nivel: int) -> int | None:
        """Quantos caracteres tem a senha DAQUELE nível — nunca qual é ela.

        Existe para o teclado de PIN desenhar a fileira de marcadores do
        tamanho certo antes do primeiro dígito (`PinPadDialog`). É o próprio
        nível, sem cascata: o Nível 2 devolve o tamanho da Operacional, e não o
        da Master que também autentica ali. Quem digita a de cima acaba com
        marcadores sobrando, e isso é de propósito — a fileira é uma dica do
        que se espera, não uma trava, e o ENTRAR nunca depende de ela encher.

        `None` quando o banco é anterior à coluna e aquela senha já tinha sido
        trocada (ver a migração `c1d5b8e37a42`): quem lê cai no piso padrão, e
        o valor certo entra sozinho na próxima troca.
        """
        campo = self._CAMPO_DE_TAMANHO_POR_NIVEL.get(nivel)
        if campo is None:
            return None
        return getattr(self.obter_ou_criar(), campo)

    def validar_cpf_dono(self, cpf: str) -> None:
        config = self.obter_ou_criar()
        if not config.cpf_dono_definido or config.cpf_dono_hash is None:
            raise RegraDeNegocioError("O CPF do Dono ainda não foi cadastrado.")
        if not self._confere(cpf, config.cpf_dono_salt, config.cpf_dono_hash):
            raise AcessoNegadoError("CPF do Dono incorreto.")

    def cpf_dono_definido(self) -> bool:
        return self.obter_ou_criar().cpf_dono_definido

    # ------------------------------------------------------------------
    # Exibição (o botão de olho de "Senhas e Acesso")
    # ------------------------------------------------------------------

    def revelar(self, campo: str, cpf_dono: str) -> str:
        """O valor real de um dos quatro segredos, mediante o CPF do Dono.

        Não é autenticação e não eleva nada: quem passa por aqui recebe **texto
        para a tela mostrar**, e nenhuma outra porta do sistema se abre. O
        `campo` é uma das constantes `CAMPO_*`; o CPF é conferido contra o
        cadastrado, pelo mesmo `validar_cpf_dono` que a troca da Senha Master
        já usava.

        A ordem das recusas é deliberada:

        1. **CPF não cadastrado** — `RegraDeNegocioError`, e a tela manda
           cadastrar. Não é acesso negado: não há nada contra o que comparar.
        2. **CPF errado** — `AcessoNegadoError`, vindo de `validar_cpf_dono`.
        3. **Sem cópia recuperável** — `RegraDeNegocioError` dizendo que basta
           trocar aquela senha uma vez. É o caso do banco que já existia com a
           senha trocada antes destas colunas (ver a migração `b6e2d80a3f14`),
           e o de quem já cadastrou o CPF antes delas.

        A checagem do CPF vem ANTES da conferência de disponibilidade de
        propósito: "este campo não tem cópia" é informação sobre o cadastro da
        loja, e quem não provou ser o dono não tem por que recebê-la.
        """
        coluna = COLUNA_CIFRADA_POR_CAMPO.get(campo)
        if coluna is None:
            raise RegraDeNegocioError(f"Campo desconhecido: {campo}.")

        self.validar_cpf_dono(cpf_dono)

        config = self.obter_ou_criar()
        guardado = getattr(config, coluna)
        valor = (
            segredo_reversivel.decifrar(guardado, self._chave_de_exibicao())
            if guardado
            else None
        )
        if valor is None:
            rotulo = ROTULO_POR_CAMPO[campo]
            raise RegraDeNegocioError(
                f"Não há cópia recuperável da {rotulo} neste computador. "
                "Altere-a uma vez para poder visualizá-la."
            )
        return valor

    def pode_revelar(self, campo: str) -> bool:
        """Existe cópia recuperável deste campo? Sem exigir CPF nenhum.

        A tela usa para decidir o **tooltip** do olho antes do clique. Não
        devolve valor nem indica se o CPF está cadastrado — só se há o que
        mostrar caso o desafio seja vencido.
        """
        coluna = COLUNA_CIFRADA_POR_CAMPO.get(campo)
        if coluna is None:
            return False
        return bool(getattr(self.obter_ou_criar(), coluna))

    # ------------------------------------------------------------------
    # Troca (cada uma exige o segredo de nível acima)
    # ------------------------------------------------------------------

    def alterar_senha_login(self, senha_nivel_2_ou_3: str, nova_senha: str) -> None:
        """Troca a Senha de Login (Nível 1) — exige a Operacional (Nível 2)
        OU a Master (Nível 3). Não chama `AuthService.validar_pin_nivel` (que
        importaria `LojaConfigService` de volta, ciclo de import evitado pelo
        mesmo motivo do `__init__` de `AuthService`): repete aqui a checagem
        de nível 2-ou-3 diretamente com os dois métodos que já existem.
        """
        if not (self.senha_operacional_confere(senha_nivel_2_ou_3) or self.senha_master_confere(senha_nivel_2_ou_3)):
            raise AcessoNegadoError("Senha Operacional (Caixa) ou Senha Master (Dono) incorreta.")
        self._validar_formato(nova_senha, "Senha de Login")
        config = self.obter_ou_criar()
        salt = AuthService.gerar_salt()
        config.senha_login_salt = salt
        config.senha_login_hash = AuthService.hash_pin(nova_senha, salt)
        config.senha_login_tamanho = len(nova_senha.strip())
        self._guardar_para_exibicao(config, CAMPO_SENHA_LOGIN, nova_senha.strip())
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    def alterar_senha_operacional(self, senha_master_atual: str, nova_senha: str) -> None:
        self.validar_senha_master(senha_master_atual)
        self._validar_formato(nova_senha, "Senha Operacional")
        config = self.obter_ou_criar()
        salt = AuthService.gerar_salt()
        config.senha_operacional_salt = salt
        config.senha_operacional_hash = AuthService.hash_pin(nova_senha, salt)
        config.senha_operacional_tamanho = len(nova_senha.strip())
        self._guardar_para_exibicao(config, CAMPO_SENHA_OPERACIONAL, nova_senha.strip())
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    def alterar_senha_master(self, cpf_dono_atual: str, nova_senha: str) -> None:
        self.validar_cpf_dono(cpf_dono_atual)
        self._validar_formato(nova_senha, "Senha Master")
        config = self.obter_ou_criar()
        salt = AuthService.gerar_salt()
        config.senha_master_salt = salt
        config.senha_master_hash = AuthService.hash_pin(nova_senha, salt)
        config.senha_master_tamanho = len(nova_senha.strip())
        self._guardar_para_exibicao(config, CAMPO_SENHA_MASTER, nova_senha.strip())
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    def definir_ou_alterar_cpf_dono(self, cpf_atual_ou_none: str | None, novo_cpf: str) -> None:
        """Primeiro cadastro (sem CPF ainda definido) não exige nada além de
        estar na tela de Senhas e Acesso — não há como exigir "o CPF atual"
        de algo que nunca existiu. A partir do segundo, exige o CPF atual."""
        config = self.obter_ou_criar()
        if config.cpf_dono_definido:
            if not cpf_atual_ou_none:
                raise RegraDeNegocioError("Informe o CPF atual do Dono para alterá-lo.")
            self.validar_cpf_dono(cpf_atual_ou_none)

        cpf_limpo = self._validar_cpf_formato(novo_cpf)
        salt = AuthService.gerar_salt()
        config.cpf_dono_salt = salt
        config.cpf_dono_hash = AuthService.hash_pin(cpf_limpo, salt)
        config.cpf_dono_definido = True
        self._guardar_para_exibicao(config, CAMPO_CPF_DONO, cpf_limpo)
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    # ------------------------------------------------------------------

    @staticmethod
    def _confere(valor: str, salt: str, hash_esperado: str) -> bool:
        if not isinstance(valor, str) or not valor:
            return False
        return AuthService.confere_pin(valor, salt, hash_esperado)

    @staticmethod
    def _validar_formato(senha: str, rotulo: str) -> None:
        if not isinstance(senha, str) or not senha.strip():
            raise RegraDeNegocioError(f"Informe a nova {rotulo}.")
        if len(senha.strip()) < 4:
            raise RegraDeNegocioError(f"A {rotulo} deve ter pelo menos 4 caracteres.")

    @staticmethod
    def _validar_cpf_formato(cpf: str) -> str:
        digitos = "".join(ch for ch in cpf if ch.isdigit()) if isinstance(cpf, str) else ""
        if len(digitos) != 11:
            raise RegraDeNegocioError("Informe um CPF válido, com 11 dígitos.")
        return digitos

    @staticmethod
    def mascarar(_valor_nunca_usado: str | None = None) -> str:
        return MASCARA
