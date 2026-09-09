"""Tela de Configurações: preferências gerais do app, Senhas e Acesso, backup.

Hoje tem três seções: "Selecionar Tema" (claro/escuro, que antes vivia
duplicado na tela de Login e no rodapé da sidebar — ver `ThemeController`) e
"Senhas e Acesso" (§3.13), o módulo de segredos operacionais da loja — cascata
de 3 níveis (Senha de Login, Senha Operacional/Caixa, Senha Master/Dono) e
CPF do Dono — sempre mascarados na tela, cada troca exigindo o segredo de
nível acima (`LojaConfigService`). A troca do Nível 1 (Login) é a única que
aceita duas credenciais alternativas (Nível 2 OU Nível 3): por isso
`_alterar_senha_login` não passa um rótulo fixo de credencial, e sim chama
`LojaConfigService.alterar_senha_login`, que já faz essa checagem "ou" —
`_AlterarSegredoDialog` só coleta os dois valores, sem saber qual regra vale.

A terceira é "Cópia de Segurança": gera um backup do banco sob demanda, além
do automático que roda a cada fechamento de caixa. Existe porque, com
`journal_mode=WAL`, copiar o arquivo do banco à mão com o programa aberto deixa
as últimas vendas para trás — ver `repository/backup.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.repository import backup
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.loja_config_service import (
    CAMPO_CPF_DONO,
    CAMPO_SENHA_LOGIN,
    CAMPO_SENHA_MASTER,
    CAMPO_SENHA_OPERACIONAL,
    MASCARA,
    ROTULO_POR_CAMPO,
    LojaConfigService,
)
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.cpf_dono_dialog import CpfDonoDialog
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.icone_olho import BotaoOlho
from gestor_comercial.ui.widgets.modais import executar_modal

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

# Quanto tempo um segredo revelado fica na tela antes de voltar a `••••••••`.
#
# Oito segundos é o que se leva para ler e anotar oito dígitos, e pouco demais
# para alguém sair de perto do monitor com a senha da loja acesa. Quem precisar
# de mais tempo clica de novo; quem terminou antes clica no olho e oculta na
# hora — o timer é o teto, não a única saída.
SEGUNDOS_REVELADO = 8

# As colunas da grade de "Senhas e Acesso". Nomeadas porque três índices soltos
# num `addWidget` são exatamente o tipo de coisa que alguém troca de lugar sem
# perceber.
_COLUNA_TEXTO = 0
_COLUNA_OLHO = 1
_COLUNA_BOTAO = 2


class ConfiguracoesView(QWidget):
    """Central de preferências do app: tema e Senhas e Acesso da loja."""

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loja_config: LojaConfigService = auth_service.loja_config
        # A Session do app, e não o engine global do módulo `base`: mantém o
        # backup preso ao mesmo banco que a tela está usando.
        self._sessao = auth_service.uow.session

        # Um segredo revelado por vez, e um timer só para todos: clicar no olho
        # de outra linha oculta a anterior antes de abrir a nova. Dois valores
        # acesos ao mesmo tempo seriam duas senhas da loja na tela de uma vez —
        # o oposto do que uma barreira de visualização serve para fazer.
        self._campo_revelado: str | None = None
        self._olhos: dict[str, BotaoOlho] = {}
        self._valores: dict[str, QLabel] = {}
        self._timer_revelado = QTimer(self)
        self._timer_revelado.setSingleShot(True)
        self._timer_revelado.timeout.connect(self.ocultar_revelado)

        # As três seções somam mais altura do que a área de página oferece numa
        # tela de 768px (a classe de monitor da máquina do food truck): sem
        # rolagem, o Qt espreme os cartões abaixo do tamanho natural deles e os
        # botões "Alterar" de Senhas e Acesso ficam sem rótulo, ilegíveis.
        # Mesmo padrão de `HistoricoCaixaView`/`DashboardMensalView`.
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)

        conteudo = QWidget()
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(4)

        eyebrow = QLabel("PREFERÊNCIAS")
        eyebrow.setObjectName("configEyebrow")
        layout.addWidget(eyebrow)

        titulo = QLabel("Configurações")
        titulo.setObjectName("configTitulo")
        layout.addWidget(titulo)

        subtitulo = QLabel("Preferências gerais do sistema")
        subtitulo.setObjectName("configSubtitulo")
        layout.addWidget(subtitulo)

        layout.addSpacing(28)

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout.addWidget(self._label_erro)

        layout.addWidget(self._montar_card_tema())
        layout.addSpacing(20)
        layout.addWidget(self._montar_card_senhas())
        layout.addSpacing(20)
        layout.addWidget(self._montar_card_backup())

        layout.addStretch()

        rolagem = QScrollArea()
        rolagem.setObjectName("configRolagem")
        rolagem.setWidget(conteudo)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout_externo.addWidget(rolagem, 1)

    # ------------------------------------------------------------------
    # Seção "Selecionar Tema"
    # ------------------------------------------------------------------

    def _montar_card_tema(self) -> QWidget:
        bloco = QWidget()
        bloco_layout = QVBoxLayout(bloco)
        bloco_layout.setContentsMargins(0, 0, 0, 0)
        bloco_layout.setSpacing(10)

        secao_titulo = QLabel("SELECIONAR TEMA")
        secao_titulo.setObjectName("configSecaoTitulo")
        bloco_layout.addWidget(secao_titulo)

        cartao = QFrame()
        cartao.setObjectName("configCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 20, 20, 20)
        cartao_layout.setSpacing(10)

        descricao = QLabel("Escolha a aparência usada em todas as telas do sistema.")
        descricao.setProperty("variante", "fraco")
        cartao_layout.addWidget(descricao)

        pilula = QFrame()
        pilula.setProperty("variante", "pilula-tema")
        pilula.setFixedWidth(280)
        layout_pilula = QHBoxLayout(pilula)
        layout_pilula.setContentsMargins(3, 3, 3, 3)
        layout_pilula.setSpacing(0)

        botao_claro = QPushButton("MODO CLARO")
        botao_escuro = QPushButton("MODO ESCURO")
        for botao in (botao_claro, botao_escuro):
            botao.setProperty("variante", "temaBotao")
            botao.setCheckable(True)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            layout_pilula.addWidget(botao)

        controlador = ThemeController.instancia()
        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        grupo.addButton(botao_claro)
        grupo.addButton(botao_escuro)
        botao_claro.setChecked(controlador.claro)
        botao_escuro.setChecked(not controlador.claro)
        botao_claro.toggled.connect(lambda marcado: marcado and controlador.alternar_para(True))
        botao_escuro.toggled.connect(lambda marcado: marcado and controlador.alternar_para(False))
        # Guardado em atributo porque `_ao_mudar_tema` precisa dele — e ele
        # precisa ser um método ligado, não `lambda`; ver o docstring de lá.
        self._botao_tema_claro = botao_claro
        controlador.mudou.connect(self._ao_mudar_tema)

        cartao_layout.addWidget(pilula)
        bloco_layout.addWidget(cartao)
        return bloco

    def _ao_mudar_tema(self, _tokens: dict[str, str]) -> None:
        """Espelha na pílula o tema que passou a valer — inclusive quando quem
        trocou foi outra tela.

        **Isto realimenta de propósito:** `mudou` → `setChecked` → `toggled` →
        `alternar_para`. O que impede o laço infinito é a guarda
        `if claro == self._claro: return` em `ThemeController.alternar_para`;
        mexer aqui ou lá sem olhar para o outro trava o app (§3.14).

        Método ligado, e não `lambda`: o controlador é singleton e vive o
        processo inteiro, então uma conexão sem objeto receptor nunca seria
        desfeita e seguraria esta tela junto.
        """
        self._botao_tema_claro.setChecked(ThemeController.instancia().claro)

    # ------------------------------------------------------------------
    # Seção "Cópia de Segurança"
    # ------------------------------------------------------------------

    def _montar_card_backup(self) -> QWidget:
        """Backup sob demanda, além do automático de cada fechamento de caixa.

        O texto da tela diz explicitamente para NÃO copiar o arquivo do banco
        com o programa aberto: com `journal_mode=WAL` isso deixa as últimas
        vendas para trás, e é o tipo de erro que só aparece no dia em que o
        backup for necessário. O botão existe para haver um caminho certo,
        óbvio, na tela — ver `repository/backup.py`.
        """
        bloco = QWidget()
        bloco_layout = QVBoxLayout(bloco)
        bloco_layout.setContentsMargins(0, 0, 0, 0)
        bloco_layout.setSpacing(10)

        secao_titulo = QLabel("CÓPIA DE SEGURANÇA")
        secao_titulo.setObjectName("configSecaoTitulo")
        bloco_layout.addWidget(secao_titulo)

        cartao = QFrame()
        cartao.setObjectName("configCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 20, 20, 20)
        cartao_layout.setSpacing(4)

        descricao = QLabel(
            "O sistema já guarda uma cópia sozinho a cada fechamento de caixa. "
            "Use o botão para gerar uma agora — antes de mexer no cardápio, ou "
            "para levar num pendrive.\n\n"
            "Copie sempre o arquivo gerado aqui, nunca o banco direto da pasta "
            "com o programa aberto: só a cópia gerada aqui vem completa."
        )
        descricao.setProperty("variante", "fraco")
        descricao.setWordWrap(True)
        cartao_layout.addWidget(descricao)
        cartao_layout.addSpacing(12)

        linha = QHBoxLayout()
        linha.setSpacing(10)
        coluna_texto = QVBoxLayout()
        coluna_texto.setSpacing(2)
        coluna_texto.addWidget(QLabel("Última cópia gerada"))
        self._valor_backup = QLabel("—")
        self._valor_backup.setProperty("variante", "fraco")
        self._valor_backup.setWordWrap(True)
        coluna_texto.addWidget(self._valor_backup)
        linha.addLayout(coluna_texto)
        linha.addStretch()

        self._botao_backup = QPushButton("Gerar cópia agora")
        self._botao_backup.setProperty("variante", "secundario")
        self._botao_backup.clicked.connect(self._gerar_backup)
        linha.addWidget(self._botao_backup, alignment=Qt.AlignmentFlag.AlignVCenter)
        cartao_layout.addLayout(linha)

        bloco_layout.addWidget(cartao)
        return bloco

    def _gerar_backup(self) -> None:
        self._label_erro.setText("")
        try:
            backup.consolidar_wal(self._sessao)
            destino = backup.fazer_backup(origem=self._sessao)
        except Exception as erro:
            # Disco cheio, pasta sem permissão, pendrive removido: a mensagem
            # tem que dizer que a cópia NÃO foi feita, senão o dono sai
            # achando que tem backup e não tem.
            self._valor_backup.setText("—")
            self._label_erro.setText(f"Não foi possível gerar a cópia: {erro}")
            return
        if destino is None:
            self._label_erro.setText("Este banco não tem arquivo em disco para copiar.")
            return
        backup.limpar_backups_antigos(origem=self._sessao)
        self._valor_backup.setText(str(destino))

    # ------------------------------------------------------------------
    # Seção "Senhas e Acesso" (§3.13)
    # ------------------------------------------------------------------

    def _montar_card_senhas(self) -> QWidget:
        bloco = QWidget()
        bloco_layout = QVBoxLayout(bloco)
        bloco_layout.setContentsMargins(0, 0, 0, 0)
        bloco_layout.setSpacing(10)

        secao_titulo = QLabel("SENHAS E ACESSO")
        secao_titulo.setObjectName("configSecaoTitulo")
        bloco_layout.addWidget(secao_titulo)

        cartao = QFrame()
        cartao.setObjectName("configCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 20, 20, 20)
        cartao_layout.setSpacing(4)

        descricao = QLabel(
            "Segredos operacionais da loja. Cada valor só é trocado informando o "
            "segredo de nível acima. Para conferir um valor, use o olho ao lado: "
            "ele exige o CPF do Dono e mostra o segredo por alguns segundos."
        )
        descricao.setProperty("variante", "fraco")
        descricao.setWordWrap(True)
        cartao_layout.addWidget(descricao)
        cartao_layout.addSpacing(12)

        # Grade, e não quatro `QHBoxLayout` empilhados: layouts irmãos não
        # conversam sobre largura, e o botão do CPF ("Cadastrar") é mais largo
        # que os três "Alterar" — em linhas independentes, o olho daquela linha
        # ficava deslocado dos outros três. Numa grade, a coluna do botão é a
        # mesma para as quatro e o alinhamento sai de graça, sem largura fixa
        # chutada em pixel.
        grade = QGridLayout()
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(4)
        grade.setColumnStretch(_COLUNA_TEXTO, 1)
        cartao_layout.addLayout(grade)

        self._botao_senha_login = self._criar_linha_segredo(
            grade, 0, CAMPO_SENHA_LOGIN, self._alterar_senha_login
        )
        self._botao_senha_operacional = self._criar_linha_segredo(
            grade, 1, CAMPO_SENHA_OPERACIONAL, self._alterar_senha_operacional
        )
        self._botao_senha_master = self._criar_linha_segredo(
            grade, 2, CAMPO_SENHA_MASTER, self._alterar_senha_master
        )
        self._botao_cpf_dono = self._criar_linha_segredo(
            grade, 3, CAMPO_CPF_DONO, self._alterar_cpf_dono
        )
        self._valor_cpf_dono = self._valores[CAMPO_CPF_DONO]

        bloco_layout.addWidget(cartao)
        self._atualizar_secao_senhas()
        return bloco

    def _criar_linha_segredo(
        self, grade: QGridLayout, linha: int, campo: str, ao_alterar: Callable[[], None]
    ) -> QPushButton:
        """Uma linha de "Senhas e Acesso": rótulo, valor mascarado, olho e Alterar.

        Devolve só o botão "Alterar" — é o único que quem chama precisa segurar
        (a linha do CPF troca o rótulo dele entre "Cadastrar" e "Alterar"). O
        olho e o rótulo do valor ficam em `self._olhos`/`self._valores`,
        indexados pelo campo, porque quem os procura depois é o fluxo de
        revelação, que sabe o campo e não a ordem em que a linha foi montada.
        """
        coluna_texto = QVBoxLayout()
        coluna_texto.setSpacing(2)
        label_rotulo = QLabel(ROTULO_POR_CAMPO[campo])
        coluna_texto.addWidget(label_rotulo)
        label_valor = QLabel(MASCARA)
        label_valor.setObjectName("configValorSegredo")
        label_valor.setProperty("variante", "fraco")
        label_valor.setProperty("revelado", False)
        coluna_texto.addWidget(label_valor)
        grade.addLayout(coluna_texto, linha, _COLUNA_TEXTO)

        olho = BotaoOlho()
        # O campo viaja no PRÓPRIO botão, e a ligação é um método ligado — não
        # uma `lambda` capturando `self` (§3.14): a conexão vive no botão, o
        # botão é filho da tela, e o ciclo se fecharia sem ninguém para
        # desfazê-lo. Quem apertou sai do `sender()`, mesmo padrão do numpad.
        olho.setProperty("campo", campo)
        olho.setToolTip(self._dica_do_olho(campo))
        olho.clicked.connect(self._ao_clicar_olho)
        grade.addWidget(olho, linha, _COLUNA_OLHO, Qt.AlignmentFlag.AlignVCenter)

        botao = QPushButton("Alterar")
        botao.setProperty("variante", "secundario")
        botao.clicked.connect(ao_alterar)
        grade.addWidget(botao, linha, _COLUNA_BOTAO, Qt.AlignmentFlag.AlignVCenter)

        self._olhos[campo] = olho
        self._valores[campo] = label_valor
        return botao

    # ------------------------------------------------------------------
    # Visualização de um segredo (o olho + o desafio do CPF do Dono)
    # ------------------------------------------------------------------

    @staticmethod
    def _dica_do_olho(campo: str) -> str:
        return f"Ver a {ROTULO_POR_CAMPO[campo]} — exige o CPF do Dono"

    def _ao_clicar_olho(self) -> None:
        """Segundo clique no mesmo olho oculta; clique em outro troca de campo."""
        botao = self.sender()
        if not isinstance(botao, BotaoOlho):
            return
        campo = botao.property("campo")
        if campo == self._campo_revelado:
            self.ocultar_revelado()
            return
        self.revelar_segredo(campo)

    def revelar_segredo(self, campo: str) -> None:
        """Pede o CPF do Dono e, se conferir, mostra o valor por alguns segundos.

        A checagem de "CPF cadastrado" acontece ANTES de abrir o cartão: sem CPF
        na loja não há desafio possível, e abrir um teclado que só pode terminar
        em erro é pior que a mensagem direta. As demais recusas (CPF errado, ou
        segredo sem cópia recuperável) acontecem dentro do cartão, que fica
        aberto para o dono tentar de novo — quem decide é sempre
        `LojaConfigService.revelar`.

        Público porque é por onde a suíte entra: percorrer o clique do olho
        exigiria abrir o modal de verdade, e `exec()` dentro de um teste trava.
        """
        self._label_erro.setText("")
        if not self._loja_config.cpf_dono_definido():
            self._label_erro.setText(
                "Cadastre o CPF do Dono primeiro — é ele que libera a visualização."
            )
            return

        # `partial` de um método ligado, e não `lambda`: o cartão guarda o
        # revelador enquanto vive, e uma `lambda` prenderia esta tela a ele.
        # Mesmo motivo pelo qual o `PinPadDialog` recebe `validar_pin_dono` já
        # ligado, em vez de uma função anônima que chama o service.
        modal = CpfDonoDialog(
            ROTULO_POR_CAMPO[campo],
            partial(self._loja_config.revelar, campo),
            self,
        )
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        valor = modal.resultado()
        if valor is None:
            return
        self._mostrar_revelado(campo, valor)

    def _mostrar_revelado(self, campo: str, valor: str) -> None:
        self.ocultar_revelado()
        self._campo_revelado = campo
        rotulo = self._valores[campo]
        rotulo.setText(valor)
        aplicar_propriedade(rotulo, "revelado", True)
        self._olhos[campo].definir_revelado(True)
        self._olhos[campo].setToolTip("Ocultar de novo")
        self._timer_revelado.start(SEGUNDOS_REVELADO * 1000)

    def ocultar_revelado(self) -> None:
        """Devolve o valor à máscara e para o timer. Sem nada revelado, não faz nada.

        É o ponto único de saída dos quatro caminhos que ocultam: o timer
        estourando, o segundo clique no olho, a tela sendo escondida
        (`hideEvent`) e a troca de um segredo. Assim não existe estado
        "revelado" que sobreviva a um deles.
        """
        self._timer_revelado.stop()
        campo, self._campo_revelado = self._campo_revelado, None
        if campo is None:
            return
        rotulo = self._valores[campo]
        rotulo.setText(self._mascara_de(campo))
        aplicar_propriedade(rotulo, "revelado", False)
        self._olhos[campo].definir_revelado(False)
        self._olhos[campo].setToolTip(self._dica_do_olho(campo))

    def _mascara_de(self, campo: str) -> str:
        """O que a linha mostra quando nada está revelado.

        Só o CPF tem um segundo estado ("Não cadastrado"): as três senhas sempre
        existem, porque nascem com o padrão de fábrica no bootstrap da loja.
        """
        if campo == CAMPO_CPF_DONO and not self._loja_config.cpf_dono_definido():
            return "Não cadastrado"
        return MASCARA

    @nao_deixa_escapar()
    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 (override Qt)
        """Sair da tela oculta o que estiver revelado, sem esperar o timer.

        Sem isto, uma senha revelada e deixada aqui continuaria acesa atrás de
        qualquer outra página — e voltar a Configurações dentro dos oito
        segundos a traria de volta à vista sem ninguém digitar CPF nenhum.
        """
        super().hideEvent(event)
        self.ocultar_revelado()

    def _atualizar_secao_senhas(self) -> None:
        # Todos os valores ficam sempre mascarados (§3.13) — o único estado
        # visível que muda é se o CPF do Dono já foi cadastrado ou não, pra
        # trocar o rótulo do botão e o texto do diálogo (primeiro cadastro
        # não exige "CPF atual", porque ele nunca existiu).
        # Uma troca de segredo invalida o que estivesse à mostra: o valor
        # revelado passou a ser o ANTERIOR, e mostrá-lo depois da troca seria
        # pior que não mostrar nada.
        self.ocultar_revelado()
        cadastrado = self._loja_config.cpf_dono_definido()
        self._botao_cpf_dono.setText("Alterar" if cadastrado else "Cadastrar")
        self._valor_cpf_dono.setText(self._mascara_de(CAMPO_CPF_DONO))

    def _alterar_senha_login(self) -> None:
        modal = _AlterarSegredoDialog(
            "Alterar Senha de Login",
            rotulo_credencial="Senha Operacional (Caixa) ou Senha Master (Dono)",
            rotulo_novo="Nova Senha de Login",
            parent=self,
        )
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        senha_nivel_2_ou_3, nova_senha = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.alterar_senha_login(senha_nivel_2_ou_3, nova_senha)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()

    def _alterar_senha_operacional(self) -> None:
        modal = _AlterarSegredoDialog(
            "Alterar Senha Operacional",
            rotulo_credencial="Senha Master (Dono) atual",
            rotulo_novo="Nova Senha Operacional",
            parent=self,
        )
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        senha_master, nova_senha = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.alterar_senha_operacional(senha_master, nova_senha)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()

    def _alterar_senha_master(self) -> None:
        modal = _AlterarSegredoDialog(
            "Alterar Senha Master",
            rotulo_credencial="CPF do Dono atual",
            rotulo_novo="Nova Senha Master",
            mascarar_credencial=False,
            parent=self,
        )
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        cpf_atual, nova_senha = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.alterar_senha_master(cpf_atual, nova_senha)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()

    def _alterar_cpf_dono(self) -> None:
        ja_cadastrado = self._loja_config.cpf_dono_definido()
        modal = _AlterarSegredoDialog(
            "Cadastrar CPF do Dono" if not ja_cadastrado else "Alterar CPF do Dono",
            rotulo_credencial="CPF do Dono atual",
            rotulo_novo="Novo CPF do Dono",
            exigir_credencial=ja_cadastrado,
            mascarar_credencial=False,
            mascarar_novo=False,
            parent=self,
        )
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        cpf_atual, novo_cpf = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.definir_ou_alterar_cpf_dono(cpf_atual, novo_cpf)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()


class _AlterarSegredoDialog(QDialog):
    """Modal genérico de troca de segredo: credencial de nível acima (quando
    exigida) + novo valor. Reaproveitado pelas 3 linhas de "Senhas e Acesso"
    — só rótulos e mascaramento mudam entre elas."""

    def __init__(
        self,
        titulo: str,
        *,
        rotulo_credencial: str,
        rotulo_novo: str,
        exigir_credencial: bool = True,
        mascarar_credencial: bool = True,
        mascarar_novo: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_credencial: QLineEdit | None = None
        if exigir_credencial:
            self._campo_credencial = QLineEdit()
            if mascarar_credencial:
                self._campo_credencial.setEchoMode(QLineEdit.EchoMode.Password)
            formulario.addRow(rotulo_credencial, self._campo_credencial)

        self._campo_novo = QLineEdit()
        if mascarar_novo:
            self._campo_novo.setEchoMode(QLineEdit.EchoMode.Password)
        formulario.addRow(rotulo_novo, self._campo_novo)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Confirmar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[str | None, str]:
        credencial = self._campo_credencial.text().strip() if self._campo_credencial else None
        novo_valor = self._campo_novo.text().strip()
        return credencial, novo_valor
