"""Comanda de produção, recibo do cliente e fechamento de caixa no papel (§3.12).

Porte de RoteamentoImpressaoService.java + ImpressaoService.java. No Java eram
dois services e a impressão era simulada com `log.info`: nada chegava na
cozinha. Aqui o roteamento (agrupar os itens por impressora da categoria)
continua sendo a regra central, mas o cupom sai de verdade pela camada
`hardware/`.

Este service é o único lugar que sabe **o que** cada cupom mostra. Ele não sabe
contar coluna (isso é do `formatador_cupom`) nem falar ESC/POS (isso é do
`hardware/impressora_escpos`). O que ele guarda são as três regras que custam
dinheiro se estiverem erradas:

1. Item de categoria sem impressora não pode sumir — vai pra padrão, e se não
   houver padrão vira aviso na tela, não silêncio.
2. `impresso_em` só é marcado no que realmente saiu no papel, senão o item
   some da via de acréscimo sem a cozinha nunca ter visto o pedido.
3. Impressora quebrada não derruba a venda (RNF inegociável de §2): o cliente
   paga e vai embora mesmo que a cozinha tenha que ouvir o pedido gritado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import FormaPagamento, StatusCaixa
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.hardware.impressora_escpos import (
    BlocoTexto,
    Documento,
    ErroDeImpressao,
)
from gestor_comercial.hardware.impressora_escpos import abrir_driver as abrir_driver_escpos
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services import formatador_cupom as cupom
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import (
    FORMAS_MAQUININHA,
    CaixaService,
    ResumoCaixa,
)
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import RecursoNaoEncontradoError

# Nome do grupo cujos itens não têm para onde ir. Aparece na tela do operador
# junto com o motivo, para ele saber qual categoria configurar.
GRUPO_SEM_IMPRESSORA = "SEM IMPRESSORA DEFINIDA"

# Rótulos escritos por extenso e acentuados: o cupom é lido pelo cliente, não
# pelo programador. Um `.value.capitalize()` daria "Consumo_interno".
ROTULO_FORMA_PAGAMENTO = {
    FormaPagamento.DINHEIRO: "Dinheiro",
    FormaPagamento.CREDITO: "Cartão de crédito",
    FormaPagamento.DEBITO: "Cartão de débito",
    FormaPagamento.PIX: "PIX",
    FormaPagamento.CONSUMO_INTERNO: "Consumo interno",
}


@dataclass(frozen=True)
class ResultadoImpressao:
    """O que aconteceu com um cupom, para a tela contar ao operador.

    Nunca é exceção: mesmo a falha vem por aqui, com `sucesso=False` e a
    mensagem já pronta para aparecer na barra de avisos.
    """

    impressora_nome: str
    quantidade_itens: int
    sucesso: bool
    erro: str | None = None


@dataclass
class _GrupoDeImpressao:
    """Os itens de uma comanda que saem juntos, no mesmo cupom.

    `impressora=None` é o grupo órfão: itens sem destino nenhum. `motivos`
    guarda, por categoria, por que cada um ficou órfão — é o texto que vira
    instrução acionável na tela.
    """

    impressora: Impressora | None
    itens: list[ItemComanda] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)


class ImpressaoService:
    """Roteia e imprime comanda de produção, recibo do cliente e fechamento (§3.12)."""

    def __init__(self, uow: UnitOfWork, auth: AuthService, abrir_driver=abrir_driver_escpos) -> None:
        self.uow = uow
        self.auth = auth
        # `abrir_driver` injetável é a costura de teste: a suíte passa um driver
        # falso e exercita todo o roteamento sem impressora, sem escpos e sem
        # arquivo em disco.
        self._abrir_driver = abrir_driver
        # ComandaService e CaixaService são construídos aqui, e não recebidos no
        # __init__, porque a conta de dinheiro do cupom (total da comanda, saldo
        # esperado do caixa) já está escrita neles — refazer a soma aqui criaria
        # uma segunda verdade sobre o mesmo valor. Ambos compartilham o mesmo
        # UnitOfWork, então continua tudo na mesma Session.
        self._comandas = ComandaService(uow, auth)
        self._caixas = CaixaService(uow, auth)

    # ------------------------------------------------------------------
    # Comanda de produção (porte de RoteamentoImpressaoService.java)
    # ------------------------------------------------------------------

    def imprimir_comanda(self, comanda_id: int) -> list[ResultadoImpressao]:
        """Via de acréscimo: manda pra produção só o que a cozinha ainda não viu.

        Lista vazia significa "não havia nada novo" — é o caso normal de quem
        clica em Imprimir duas vezes seguidas, não um erro.
        """
        comanda = self._buscar_comanda(comanda_id)
        itens = self.uow.itens.listar_nao_impressos_por_comanda(comanda.id)
        if not itens:
            return []

        agora = datetime.now()
        resultados, impressos = self._imprimir_grupos(comanda, itens, agora, segunda_via=False)

        # `impresso_em` só nos grupos que saíram no papel. O grupo que falhou
        # continua NULL e sai de novo no próximo clique — marcar antes de saber
        # o resultado esconderia o item da cozinha para sempre.
        if impressos:
            for item in impressos:
                item.impresso_em = agora
                self.uow.itens.salvar(item)
            self.uow.commit()  # commit único, depois de todos os grupos
        return resultados

    def reimprimir_comanda(self, comanda_id: int) -> list[ResultadoImpressao]:
        """2ª via: repete a comanda inteira e não mexe em `impresso_em`.

        É a ação de quando o cupom rasgou, borrou ou se perdeu na cozinha —
        o que já foi enviado continua marcado como enviado.
        """
        comanda = self._buscar_comanda(comanda_id)
        itens = [
            item for item in self.uow.itens.listar_por_comanda(comanda.id) if not item.cancelado
        ]
        if not itens:
            return []

        resultados, _ = self._imprimir_grupos(comanda, itens, datetime.now(), segunda_via=True)
        return resultados

    # ------------------------------------------------------------------
    # Recibo do cliente
    # ------------------------------------------------------------------

    def imprimir_recibo(self, comanda_id: int) -> ResultadoImpressao:
        """Recibo do cliente, sempre na impressora padrão (a do balcão)."""
        comanda = self._buscar_comanda(comanda_id)
        itens = [
            item for item in self.uow.itens.listar_por_comanda(comanda.id) if not item.cancelado
        ]

        padrao = self.uow.impressoras.buscar_padrao()
        if padrao is None:
            return self._sem_impressora_padrao("o recibo do cliente", len(itens))

        documento = self._documento_recibo(comanda, itens, padrao, datetime.now())
        return self._enviar(padrao, documento, len(itens))

    # ------------------------------------------------------------------
    # Fechamento de caixa
    # ------------------------------------------------------------------

    def imprimir_fechamento_caixa(self, caixa_id: int) -> ResultadoImpressao:
        """Relatório de conferência da gaveta, na impressora padrão."""
        self.auth.usuario_atual()
        caixa = self._caixas.buscar(caixa_id)

        padrao = self.uow.impressoras.buscar_padrao()
        if padrao is None:
            return self._sem_impressora_padrao("o fechamento de caixa", 0)

        # Toda a conta vem pronta de CaixaService.resumo: abertura, totais por
        # forma, movimentos da gaveta, saldo esperado e diferença. Recalcular
        # qualquer uma delas aqui criaria um relatório que diverge da tela.
        resumo = self._caixas.resumo(caixa.id)
        documento = self._documento_fechamento(caixa, resumo, padrao, datetime.now())
        return self._enviar(padrao, documento, 0)

    # ------------------------------------------------------------------
    # Teste de impressora
    # ------------------------------------------------------------------

    def imprimir_teste(self, impressora_id: int) -> ResultadoImpressao:
        """Cupom de conferência da tela de Impressoras: cabo, papel e largura."""
        self.auth.usuario_atual()
        impressora = self.uow.impressoras.buscar_por_id(impressora_id)
        if impressora is None:
            raise RecursoNaoEncontradoError(f"Impressora não encontrada (código {impressora_id}).")

        # Impressora desativada não é barrada aqui de propósito: o teste existe
        # justamente para o gerente conferir o cabo antes de reativá-la.
        documento = self._documento_teste(impressora, datetime.now())
        return self._enviar(impressora, documento, 0)

    # ------------------------------------------------------------------
    # Roteamento (porte de RoteamentoImpressaoService.rotear)
    # ------------------------------------------------------------------

    def _imprimir_grupos(
        self,
        comanda: Comanda,
        itens: list[ItemComanda],
        agora: datetime,
        segunda_via: bool,
    ) -> tuple[list[ResultadoImpressao], list[ItemComanda]]:
        """Imprime um cupom por impressora e devolve (resultados, itens que saíram)."""
        resultados: list[ResultadoImpressao] = []
        impressos: list[ItemComanda] = []

        for grupo in self._agrupar_por_impressora(itens):
            if grupo.impressora is None:
                resultados.append(
                    ResultadoImpressao(
                        impressora_nome=GRUPO_SEM_IMPRESSORA,
                        quantidade_itens=len(grupo.itens),
                        sucesso=False,
                        erro=self._erro_do_grupo_orfao(grupo),
                    )
                )
                continue

            documento = self._documento_producao(comanda, grupo, agora, segunda_via)
            resultado = self._enviar(grupo.impressora, documento, len(grupo.itens))
            resultados.append(resultado)
            if resultado.sucesso:
                impressos.extend(grupo.itens)

        return resultados, impressos

    def _agrupar_por_impressora(self, itens: list[ItemComanda]) -> list[_GrupoDeImpressao]:
        """Agrupa por `item.produto.categoria.impressora`, na ordem de lançamento.

        O dict comum do Python preserva a ordem de inserção, que é a mesma razão
        pela qual o Java usava LinkedHashMap: a cozinha lê o cupom na sequência
        em que o atendente digitou.
        """
        padrao = self.uow.impressoras.buscar_padrao()
        grupos: dict[int | None, _GrupoDeImpressao] = {}

        for item in itens:
            impressora, motivo = self._destino_do_item(item, padrao)
            chave = None if impressora is None else impressora.id
            grupo = grupos.get(chave)
            if grupo is None:
                grupo = _GrupoDeImpressao(impressora=impressora)
                grupos[chave] = grupo
            grupo.itens.append(item)
            if motivo is not None and motivo not in grupo.motivos:
                grupo.motivos.append(motivo)

        return list(grupos.values())

    @staticmethod
    def _destino_do_item(
        item: ItemComanda, padrao: Impressora | None
    ) -> tuple[Impressora | None, str | None]:
        """Descobre em qual impressora este item sai, e por que ficou sem uma.

        DIVERGÊNCIA do Java: lá o item de categoria sem impressora ia pro grupo
        SEM_IMPRESSORA_DEFINIDA, que só era logado — ou seja, o pedido nunca
        chegava na cozinha e ninguém ficava sabendo. Aqui ele cai na impressora
        padrão, e só vira aviso na tela quando nem padrão existe: comida que
        ninguém faz é pior do que um aviso.
        """
        categoria = getattr(item.produto, "categoria", None)
        nome_categoria = getattr(categoria, "nome", None) or "sem categoria"
        impressora = getattr(categoria, "impressora", None)

        # Impressora desativada pelo gerente também cai no fallback: ele desligou
        # aquele destino, não a comanda.
        if impressora is not None and impressora.ativa:
            return impressora, None
        if padrao is not None:
            return padrao, None
        if impressora is None:
            return None, f"a categoria '{nome_categoria}' não tem impressora associada"
        return None, (
            f"a impressora '{impressora.nome}' da categoria '{nome_categoria}' está desativada"
        )

    @staticmethod
    def _erro_do_grupo_orfao(grupo: _GrupoDeImpressao) -> str:
        motivos = "; ".join(grupo.motivos) or "estes itens não têm impressora"
        return (
            f"{len(grupo.itens)} item(ns) não foram impressos porque {motivos}. "
            "Associe uma impressora a essas categorias no Cardápio, ou marque uma "
            "impressora como padrão na tela de Impressoras."
        )

    # ------------------------------------------------------------------
    # Envio (a única fronteira com o hardware)
    # ------------------------------------------------------------------

    def _enviar(
        self, impressora: Impressora, documento: Documento, quantidade_itens: int
    ) -> ResultadoImpressao:
        """Abre o driver, imprime e transforma qualquer falha em resultado.

        O timeout curto (3 s) é o default de `abrir_driver`: a impressão roda na
        thread da UI, então nada aqui pode ficar pendurado esperando um IP que
        não responde. Chamar com um único argumento também é o que permite ao
        teste injetar um driver falso de assinatura simples.
        """
        try:
            with self._abrir_driver(impressora) as driver:
                driver.imprimir(documento)
        except ErroDeImpressao as erro:
            return ResultadoImpressao(impressora.nome, quantidade_itens, False, str(erro))
        except Exception as erro:  # noqa: BLE001 - último cinto de segurança do RNF
            # `hardware/` promete só levantar ErroDeImpressao, mas se um dia
            # escapar outra coisa dali a venda não pode cair junto. Mensagem
            # diferente de propósito: "erro inesperado" é o sinal de que a falha
            # é nossa, não do cabo da impressora.
            return ResultadoImpressao(
                impressora.nome,
                quantidade_itens,
                False,
                f"Erro inesperado ao imprimir em '{impressora.nome}': {erro}",
            )
        return ResultadoImpressao(impressora.nome, quantidade_itens, True)

    # ------------------------------------------------------------------
    # Montagem dos documentos
    # ------------------------------------------------------------------

    def _documento_producao(
        self,
        comanda: Comanda,
        grupo: _GrupoDeImpressao,
        agora: datetime,
        segunda_via: bool,
    ) -> Documento:
        """Cupom da cozinha: o que produzir, para qual mesa, em que ordem."""
        impressora = grupo.impressora
        largura = cupom.largura_util(impressora.colunas)

        # O nome da impressora é texto de tamanho livre como qualquer outro
        # (`impressoras.nome` aceita 80 caracteres e a bobina pode ter 20), e é
        # logo a primeira linha do cupom — a que diz para qual praça o pedido
        # vai. Sem quebrar, a impressora corta o excedente e o cabeçalho mente.
        documento: Documento = [
            BlocoTexto(linha, negrito=True, centralizado=True)
            for linha in cupom.quebrar(impressora.nome.upper(), largura)
        ]
        if segunda_via:
            documento.append(BlocoTexto("2ª VIA", negrito=True, centralizado=True))

        # Mesa em dobro: é a única informação que a cozinha precisa ler de longe,
        # de dentro do vapor da chapa, sem chegar perto do cupom.
        documento.append(
            BlocoTexto(self._destino_da_comanda(comanda), dobro=True, centralizado=True)
        )
        documento.append(
            BlocoTexto(cupom.duas_colunas(f"Comanda {comanda.id}", cupom.hora(agora), largura))
        )
        # Passa pelo `quebrar` como qualquer outro texto de tamanho livre:
        # `funcionarios.nome` aceita 120 caracteres e a bobina tem 32.
        for linha in cupom.quebrar(f"Atendente: {self._nome_do_atendente(comanda)}", largura):
            documento.append(BlocoTexto(linha))
        documento.append(BlocoTexto(cupom.separador(largura)))

        for item in grupo.itens:
            for linha in cupom.linha_de_item(item.quantidade, item.produto.nome, largura):
                # Nome do item em negrito: é o que a cozinha procura primeiro.
                documento.append(BlocoTexto(linha, negrito=True))
            for linha in cupom.linha_secundaria(item.observacao, largura, prefixo="obs: "):
                documento.append(BlocoTexto(linha))
            for linha in cupom.linha_secundaria(item.produto.descricao, largura):
                documento.append(BlocoTexto(linha))

        documento.append(BlocoTexto(cupom.separador(largura)))
        return documento

    def _documento_recibo(
        self,
        comanda: Comanda,
        itens: list[ItemComanda],
        impressora: Impressora,
        agora: datetime,
    ) -> Documento:
        """Recibo do cliente: o que ele levou, quanto deu e como pagou."""
        largura = cupom.largura_util(impressora.colunas)
        total = self._comandas.calcular_total(comanda.id)
        pagos_por_forma, troco, total_pago = self._pagamentos_da_comanda(comanda.id)

        documento: Documento = [
            BlocoTexto("RECIBO", negrito=True, centralizado=True),
            BlocoTexto(
                f"Comanda {comanda.id} - {self._destino_da_comanda(comanda)}",
                centralizado=True,
            ),
            BlocoTexto(cupom.data_hora(agora), centralizado=True),
            BlocoTexto(cupom.separador(largura)),
        ]

        for item in itens:
            valor = dinheiro(item.preco_unit_congelado) * item.quantidade
            for linha in cupom.linha_de_item(
                item.quantidade, item.produto.nome, largura, valor=valor
            ):
                documento.append(BlocoTexto(linha))
            for linha in cupom.linha_secundaria(item.observacao, largura):
                documento.append(BlocoTexto(linha))

        documento.append(BlocoTexto(cupom.separador(largura)))
        documento.append(
            BlocoTexto(
                cupom.duas_colunas("TOTAL", f"R$ {cupom.moeda(total)}", largura, preenchimento="."),
                negrito=True,
            )
        )

        if pagos_por_forma:
            documento.append(BlocoTexto(cupom.separador(largura, titulo="PAGAMENTO")))
            for forma, valor in pagos_por_forma.items():
                rotulo = ROTULO_FORMA_PAGAMENTO.get(forma, forma.value)
                documento.append(BlocoTexto(cupom.linha_de_valor(rotulo, valor, largura)))
            if troco > ZERO:
                documento.append(BlocoTexto(cupom.linha_de_valor("Troco", troco, largura)))

        restante = dinheiro(max(total - total_pago, ZERO))
        if restante > ZERO:
            # Comanda fechada por gerente com saldo em aberto (§3.7): o cupom
            # tem que mostrar o que ficou faltando, senão vira o único registro
            # de uma venda que parece paga.
            documento.append(
                BlocoTexto(cupom.linha_de_valor("A RECEBER", restante, largura), negrito=True)
            )

        documento.append(BlocoTexto(cupom.separador(largura)))
        for linha in cupom.quebrar(f"Atendente: {self._nome_do_atendente(comanda)}", largura):
            documento.append(BlocoTexto(linha))
        # O rodapé também é quebrado: na bobina de 20 colunas — largura válida no
        # cadastro — nenhuma das duas frases cabe inteira, e texto estourado sai
        # cortado pela impressora, não continuado na linha de baixo.
        for texto in ("Não é documento fiscal", "Obrigado e volte sempre!"):
            for linha in cupom.quebrar(texto, largura):
                documento.append(BlocoTexto(linha, centralizado=True))
        return documento

    def _documento_fechamento(
        self, caixa: Caixa, resumo: ResumoCaixa, impressora: Impressora, agora: datetime
    ) -> Documento:
        """Relatório de conferência da gaveta, com os números do `CaixaService`."""
        largura = cupom.largura_util(impressora.colunas)

        documento: Documento = [BlocoTexto("FECHAMENTO DE CAIXA", negrito=True, centralizado=True)]
        if caixa.numero_sequencial_dia is not None and caixa.fechado_em is not None:
            # Identificação oficial do fechamento (§ sequência diária): indexada
            # por `fechado_em`, é o número que a contabilidade usa pra achar
            # este turno depois — não existe enquanto o caixa está aberto.
            documento.append(
                BlocoTexto(self._caixas.titulo_fechamento(caixa.id), centralizado=True)
            )
        documento.append(BlocoTexto(f"Caixa {caixa.id}", centralizado=True))
        documento.extend([
            BlocoTexto(cupom.duas_colunas("Aberto em", cupom.data_hora(caixa.aberto_em), largura)),
            BlocoTexto(
                cupom.duas_colunas(
                    "Fechado em",
                    cupom.data_hora(caixa.fechado_em) if caixa.fechado_em else "em aberto",
                    largura,
                )
            ),
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto(cupom.linha_de_valor("Valor de abertura", resumo.valor_abertura, largura)),
            BlocoTexto(cupom.separador(largura, titulo="VENDAS")),
            BlocoTexto(cupom.linha_de_valor("Dinheiro", resumo.total_dinheiro, largura)),
        ])

        # `resumo` já traz o total da maquininha somado; a quebra por bandeira é
        # detalhe que só existe aqui, porque é o que o gerente confere contra o
        # extrato da máquina no fim da noite.
        detalhe = self._detalhe_da_maquininha(caixa.id)
        for rotulo, valor in detalhe:
            documento.append(BlocoTexto(cupom.linha_de_valor(rotulo, valor, largura)))
        if len(detalhe) != 1:
            # Com uma forma só de cartão, a linha dela já É o total da
            # maquininha, e repetir o mesmo número confunde quem está conferindo.
            documento.append(
                BlocoTexto(cupom.linha_de_valor("Maquininha", resumo.total_maquininha, largura))
            )
        documento.append(
            BlocoTexto(
                cupom.linha_de_valor("Consumo interno", resumo.total_consumo_interno, largura)
            )
        )
        documento.append(
            BlocoTexto(
                cupom.linha_de_valor(
                    "Total em vendas",
                    dinheiro(
                        resumo.total_dinheiro
                        + resumo.total_maquininha
                        + resumo.total_consumo_interno
                    ),
                    largura,
                )
            )
        )

        documento.append(BlocoTexto(cupom.separador(largura, titulo="GAVETA")))
        documento.append(BlocoTexto(cupom.linha_de_valor("Reforços", resumo.reforcos, largura)))
        documento.append(BlocoTexto(cupom.linha_de_valor("Sangrias", resumo.sangrias, largura)))
        documento.append(BlocoTexto(cupom.linha_de_valor("Despesas", resumo.despesas, largura)))

        documento.append(BlocoTexto(cupom.separador(largura)))
        documento.append(
            BlocoTexto(
                cupom.duas_colunas(
                    "SALDO ESPERADO",
                    f"R$ {cupom.moeda(resumo.saldo_esperado)}",
                    largura,
                    preenchimento=".",
                ),
                negrito=True,
            )
        )

        if resumo.valor_contado is None:
            # Caixa ainda aberto: o relatório serve de conferência parcial, e a
            # linha de assinatura é onde o gerente anota o que contou na mão.
            documento.append(BlocoTexto(cupom.duas_colunas("Valor contado", "_" * 10, largura)))
        else:
            documento.append(
                BlocoTexto(cupom.linha_de_valor("Valor contado", resumo.valor_contado, largura))
            )
            documento.append(
                BlocoTexto(
                    cupom.linha_de_valor(
                        "Diferença",
                        ZERO if resumo.diferenca is None else resumo.diferenca,
                        largura,
                    ),
                    negrito=True,
                )
            )
        if caixa.observacao_fechamento:
            for linha in cupom.linha_secundaria(
                caixa.observacao_fechamento, largura, prefixo="Obs: "
            ):
                documento.append(BlocoTexto(linha))

        documento.append(BlocoTexto(cupom.separador(largura)))
        situacao = "FECHADO" if caixa.status is StatusCaixa.FECHADO else "ABERTO"
        documento.append(BlocoTexto(cupom.duas_colunas("Situação", situacao, largura)))
        # Os dois operadores do turno: quem declarou o fundo de troco pode não
        # ser quem conferiu a gaveta no fim, e o histórico depende de mostrar
        # os dois nomes, não só quem está segurando a impressão agora.
        if caixa.aberto_por is not None:
            for linha in cupom.quebrar(f"Aberto por: {caixa.aberto_por.nome}", largura):
                documento.append(BlocoTexto(linha))
        if caixa.fechado_por is not None:
            for linha in cupom.quebrar(f"Fechado por: {caixa.fechado_por.nome}", largura):
                documento.append(BlocoTexto(linha))
        documento.append(
            BlocoTexto(cupom.duas_colunas("Impresso em", cupom.data_hora(agora), largura))
        )
        for linha in cupom.quebrar(
            f"Conferido por: {self.auth.usuario_atual().nome}", largura
        ):
            documento.append(BlocoTexto(linha))
        return documento

    def _documento_teste(self, impressora: Impressora, agora: datetime) -> Documento:
        """Cupom de teste: prova cabo, papel, acento e largura de uma vez só."""
        largura = cupom.largura_util(impressora.colunas)
        tipo = getattr(impressora.tipo_conexao, "value", impressora.tipo_conexao)

        documento: Documento = [BlocoTexto("TESTE DE IMPRESSÃO", negrito=True, centralizado=True)]
        # Mesmo motivo do cupom de produção: nome comprido estouraria a bobina.
        for linha in cupom.quebrar(impressora.nome, largura):
            documento.append(BlocoTexto(linha, centralizado=True))

        documento.extend([
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto(cupom.duas_colunas("Conexão", str(tipo), largura)),
            BlocoTexto(cupom.duas_colunas("Largura", f"{largura} colunas", largura)),
            BlocoTexto(cupom.duas_colunas("Data", cupom.data_hora(agora), largura)),
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto("Texto normal: ação, pão, café."),
            BlocoTexto("Texto em negrito", negrito=True),
            BlocoTexto("MESA 12", dobro=True, centralizado=True),
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto(cupom.regua(largura)),
        ])
        # A instrução também é quebrada: numa bobina de 32 colunas a frase tem
        # quase o triplo da largura, e sair cortada justamente no cupom que
        # ensina a conferir a largura seria irônico demais.
        for linha in cupom.quebrar(
            f"Se a régua acima ocupou uma linha só, a largura de {largura} "
            "colunas está correta para esta bobina.",
            largura,
        ):
            documento.append(BlocoTexto(linha))
        documento.append(BlocoTexto(cupom.separador(largura)))
        return documento

    # ------------------------------------------------------------------
    # Apoio
    # ------------------------------------------------------------------

    def _buscar_comanda(self, comanda_id: int) -> Comanda:
        """Exige sessão antes de tocar no banco e devolve a comanda pedida.

        As duas únicas exceções que sobem deste service saem daqui:
        NaoAutorizadoError (ninguém logado) e RecursoNaoEncontradoError (id que
        não existe). Falha de impressora vira `ResultadoImpressao`.
        """
        self.auth.usuario_atual()
        return self._comandas.buscar(comanda_id)

    @staticmethod
    def _sem_impressora_padrao(o_que: str, quantidade_itens: int) -> ResultadoImpressao:
        return ResultadoImpressao(
            impressora_nome=GRUPO_SEM_IMPRESSORA,
            quantidade_itens=quantidade_itens,
            sucesso=False,
            erro=(
                f"Nenhuma impressora está marcada como padrão, então {o_que} não saiu. "
                "Abra a tela de Impressoras e use 'Definir como padrão'."
            ),
        )

    def _pagamentos_da_comanda(
        self, comanda_id: int
    ) -> tuple[dict[FormaPagamento, Decimal], Decimal, Decimal]:
        """Soma os pagamentos por forma, o troco devolvido e o total recebido.

        Uma varredura só na lista que o repository já devolve ordenada: o
        recibo mostra as formas na ordem em que o cliente pagou.
        """
        por_forma: dict[FormaPagamento, Decimal] = {}
        troco = ZERO
        total = ZERO
        for pagamento in self.uow.pagamentos.listar_por_comanda(comanda_id):
            valor = dinheiro(pagamento.valor)
            por_forma[pagamento.forma] = dinheiro(por_forma.get(pagamento.forma, ZERO) + valor)
            total += valor
            if pagamento.troco is not None:
                troco += dinheiro(pagamento.troco)
        return por_forma, dinheiro(troco), dinheiro(total)

    def _detalhe_da_maquininha(self, caixa_id: int) -> list[tuple[str, Decimal]]:
        """Crédito, débito e PIX separados — só as formas que tiveram movimento."""
        detalhe: list[tuple[str, Decimal]] = []
        for forma in FORMAS_MAQUININHA:
            total = ZERO
            for pagamento in self.uow.pagamentos.listar_por_caixa(caixa_id, formas=[forma]):
                total += dinheiro(pagamento.valor)
            if total > ZERO:
                detalhe.append((ROTULO_FORMA_PAGAMENTO.get(forma, forma.value), dinheiro(total)))
        return detalhe

    @staticmethod
    def _destino_da_comanda(comanda: Comanda) -> str:
        """'MESA 12' ou 'BALCÃO' — para onde o pedido vai."""
        mesa = getattr(comanda, "mesa", None)
        if mesa is None:
            return "BALCÃO"
        return f"MESA {mesa.numero}"

    def _nome_do_atendente(self, comanda: Comanda) -> str:
        """Quem abriu a comanda; na falta dele, quem está operando agora."""
        funcionario = getattr(comanda, "funcionario", None)
        if funcionario is not None:
            return funcionario.nome
        return self.auth.usuario_atual().nome
