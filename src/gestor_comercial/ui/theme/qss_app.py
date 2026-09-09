"""Folha de estilo do shell inteiro (tudo além da tela de login), como um
template parametrizado pelos tokens de `tokens.py` -- portado de
`resources/qss/base.qss` (agora obsoleto/removido) para poder ser
recalculado a cada troca de tema claro/escuro pelo `ThemeController`.

Convenção de propriedade dinâmica para variantes de botão (ver
`QPushButton.setProperty("variante", "primario"|"secundario"|"perigo")`):
qproperty não é usado para estilo -- usamos seletor `[variante="..."]`.
"""

from __future__ import annotations


def construir_qss_app(t: dict[str, str]) -> str:
    return f"""
    * {{
      font-family: "Archivo Black", "Segoe UI Variable Display", "Segoe UI", "Inter", Arial, sans-serif;
    }}

    QWidget {{
      background: {t['bg_marca']};
      color: {t['texto']};
    }}

    QMainWindow {{
      background: {t['bg_marca']};
    }}

    QLineEdit {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 8px;
      padding: 10px 12px;
      color: {t['texto']};
    }}
    QLineEdit:focus {{ border: 1px solid {t['acento']}; }}

    /* ---------- Combo Box ---------- */

    QComboBox {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 8px;
      padding: 8px 12px;
      color: {t['texto']};
      font-size: 13px;
    }}
    QComboBox:focus {{ border: 1px solid {t['acento']}; }}
    QComboBox::drop-down {{ border: none; width: 24px; background: transparent; }}
    QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}

    QComboBox QAbstractItemView {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 8px;
      color: {t['texto']};
      selection-background-color: {t['acento']};
      selection-color: {t['acento_texto']};
    }}
    QComboBox QAbstractItemView::item {{ padding: 8px 12px; border: none; }}
    QComboBox QAbstractItemView::item:hover {{ background: {t['borda']}; }}

    /* ---------- Sidebar ---------- */

    #sidebar {{
      background: {t['bg_terminal']};
      border-right: 1px solid {t['borda']};
    }}
    #sidebarSelo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      padding: 0 12px;
    }}
    #sidebarMarca {{
      color: {t['texto']};
      font-size: 15px;
      font-weight: 700;
      padding: 2px 12px 0 12px;
    }}
    #sidebarDivisor {{
      background: {t['borda']};
      max-height: 1px;
      min-height: 1px;
      margin: 0 8px;
    }}
    #sidebarGrupoRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      padding: 0 12px;
      background: transparent;
    }}
    #sidebarSelo, #sidebarMarca {{ background: transparent; }}

    QPushButton[variante="nav"] {{
      background: transparent;
      border: none;
      border-left: 3px solid transparent;
      color: {t['texto_fraco']};
      text-align: left;
      padding: 11px 12px;
      border-radius: 10px;
      font-size: 13px;
    }}
    QPushButton[variante="nav"]:hover {{ background: {t['superficie']}; color: {t['texto']}; }}
    QPushButton[variante="nav"][ativo="true"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border-left: 3px solid {t['acento']};
    }}

    /* ---------- Pílula de tema (agora só na tela de Configurações) ---------- */

    QFrame[variante="pilula-tema"] {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QPushButton[variante="temaBotao"] {{
      background: transparent;
      color: {t['texto_fraco']};
      border: none;
      border-radius: 11px;
      padding: 7px 0px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
    }}
    QPushButton[variante="temaBotao"]:checked {{
      background: {t['acento']};
      color: {t['acento_texto']};
    }}

    /* ---------- Botões ---------- */

    QPushButton {{
      border: none;
      border-radius: 10px;
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 600;
    }}

    QPushButton[variante="primario"] {{ background: {t['acento']}; color: {t['acento_texto']}; }}
    QPushButton[variante="primario"]:hover {{ background: {t['acento']}; }}
    QPushButton[variante="primario"]:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    QPushButton[variante="secundario"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
    }}
    QPushButton[variante="secundario"]:hover {{ background: {t['borda']}; }}

    QPushButton[variante="perigo"] {{ background: {t['perigo']}; color: white; border: none; }}
    QPushButton[variante="perigo"]:hover {{ background: {t['perigo_hover']}; }}
    QPushButton[variante="perigo"]:pressed {{ background: {t['perigo']}; }}

    /* Ciano: ação de "desativar" no Cardápio -- nem neutra, nem destrutiva. */
    QPushButton[variante="ciano"] {{ background: {t['ciano_acao']}; color: {t['ciano_acao_texto']}; border: none; }}
    QPushButton[variante="ciano"]:hover {{ background: {t['ciano_acao_hover']}; }}
    QPushButton[variante="ciano"]:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    /* Tracejado: "+ Nova categoria" no rodapé da coluna de categorias. */
    QPushButton[variante="tracejado"] {{
      background: transparent;
      color: {t['texto_fraco']};
      border: 1px dashed {t['borda']};
    }}
    QPushButton[variante="tracejado"]:hover {{ color: {t['texto']}; border-color: {t['texto_fraco']}; }}

    /* Variante compacta de "perigo" para botões dentro de linha de tabela
       (Remover/Cancelar em `ComandaView`): o padding padrão de QPushButton
       (10px 16px + fonte 13px) exige ~38px de altura, mais que a linha da
       tabela (~30px) comporta — o botão fica espremido pelo `setCellWidget`
       e, abaixo de um certo limiar, o Qt para de desenhar o texto (vira uma
       barra vermelha vazia). Padding e fonte menores cabem na linha padrão. */
    QPushButton[variante="perigo-tabela"] {{
      background: {t['perigo_tabela_bg']}; color: #FFFFFF; border: none;
      height: 22px; padding: 0 12px; font-size: 11px; font-weight: 700; border-radius: 11px;
    }}
    QPushButton[variante="perigo-tabela"]:hover {{ background: {t['perigo_hover']}; }}
    QPushButton[variante="perigo-tabela"]:pressed {{ background: {t['perigo']}; }}

    /* ---------- Pílulas do cabeçalho da Comanda ---------- */

    /* "← Mesas": ponto de saída da tela — precisa se destacar dos botões
       neutros ao lado (+ Item, 2ª via) pra ficar óbvio que é a saída, não
       mais uma ação da comanda. Borda âmbar + peso maior que o padrão. */
    QPushButton[variante="pilula-voltar"] {{
      background: {t['pill_comanda_bg']};
      color: {t['pill_comanda_texto']};
      border: 1.5px solid {t['pill_comanda_texto']};
      border-radius: 18px;
      padding: 7px 18px;
      font-size: 13px;
      font-weight: 800;
    }}
    QPushButton[variante="pilula-voltar"]:hover {{ background: {t['pill_comanda_bg_2']}; }}
    QPushButton[variante="pilula-voltar"]:disabled {{ color: {t['pilula_disabled_texto']}; border-color: {t['pilula_voltar_disabled_borda']}; }}

    QPushButton[variante="pilula-secundario"] {{
      background: {t['pill_comanda_bg']};
      color: {t['pilula_secundario_texto']};
      border: none;
      border-radius: 18px;
      padding: 7px 18px;
      font-size: 12px;
      font-weight: 600;
    }}
    QPushButton[variante="pilula-secundario"]:hover {{ background: {t['pill_comanda_bg_2']}; }}
    QPushButton[variante="pilula-secundario"]:disabled {{ color: {t['pilula_disabled_texto']}; }}

    QPushButton[variante="pilula-destaque"] {{
      background: {t['barra_total_bg']};
      color: {t['pilula_destaque_texto']};
      border: none;
      border-radius: 18px;
      padding: 7px 20px;
      font-size: 13px;
      font-weight: 800;
    }}
    QPushButton[variante="pilula-destaque"]:hover {{ background: {t['pilula_destaque_hover']}; }}
    QPushButton[variante="pilula-destaque"]:disabled {{ background: {t['pilula_disabled_bg']}; color: {t['pilula_disabled_texto']}; }}

    QPushButton[variante="pilula-perigo"] {{
      background: {t['pilula_perigo_bg']};
      color: {t['pilula_perigo_texto']};
      border: none;
      border-radius: 18px;
      padding: 7px 20px;
      font-size: 13px;
      font-weight: 700;
    }}
    QPushButton[variante="pilula-perigo"]:hover {{ background: {t['pilula_perigo_hover']}; }}
    QPushButton[variante="pilula-perigo"]:disabled {{ background: {t['pilula_disabled_bg']}; color: {t['pilula_disabled_texto']}; }}

    /* Combo "Atendeu": some com a aparência de caixa de formulário e vira
       texto simples, como no mockup — continua clicável/funcional, só sem o
       chrome visual de combo box. */
    QComboBox#combo-atendente {{
      background: transparent;
      border: none;
      padding: 0 4px;
      color: {t['combo_atendente_borda']};
      font-size: 13px;
      font-weight: 500;
    }}
    QComboBox#combo-atendente::drop-down {{ border: none; width: 14px; }}
    QComboBox#combo-atendente QAbstractItemView {{
      background: {t['combo_atendente_bg']};
      border: 1px solid {t['borda_card']};
      color: {t['texto']};
    }}

    /* Botão "Enviar Pedido à Produção", no header do card de pendentes */
    QPushButton[variante="enviar-pedido"] {{
      background: {t['enviar_pedido_bg']};
      color: {t['enviar_pedido_texto']};
      border: none;
      border-radius: 18px;
      padding: 8px 22px;
      font-size: 13px;
      font-weight: 800;
    }}
    QPushButton[variante="enviar-pedido"]:hover {{ background: {t['enviar_pedido_hover']}; }}
    QPushButton[variante="enviar-pedido"]:disabled {{ background: {t['pilula_disabled_bg']}; color: {t['pilula_disabled_texto']}; }}

    /* Botão "Remover" compacto na tabela de itens pendentes */
    QPushButton[variante="remover-tabela"] {{
      background: {t['remover_tabela_bg']};
      color: {t['remover_tabela_texto']};
      border: 1px solid {t['remover_tabela_borda']};
      border-radius: 11px;
      font-size: 11px;
      font-weight: 700;
      height: 22px;
      padding: 0 10px;
    }}
    QPushButton[variante="remover-tabela"]:hover {{ background: {t['remover_tabela_hover']}; }}

    QPushButton[variante="neutro"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
    }}
    QPushButton[variante="neutro"]:hover {{ background: {t['borda']}; }}

    QPushButton[variante="sucesso"] {{ background: {t['sucesso']}; color: white; font-weight: 700; }}
    QPushButton[variante="sucesso"]:hover {{ background: {t['sucesso']}; }}
    QPushButton[variante="sucesso"]:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    /* ---------- Grid de mesas ---------- */

    QFrame[variante="mesa"] {{
      background: {t['mesa_livre_bg']};
      border: 1px solid {t['borda']};
      border-top: 3px solid {t['sucesso']};
      border-radius: 14px;
    }}
    QFrame[variante="mesa"]:hover {{ background: {t['superficie_2']}; }}
    QLabel#mesaCartaoNumero {{ color: {t['texto']}; font-size: 20px; font-weight: 800; background: transparent; }}
    QLabel#mesaCartaoTag {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QFrame[variante="mesa"][ocupada="true"] QLabel#mesaCartaoTag {{ color: {t['mesa_ocupada_tag']}; }}
    QFrame[variante="mesa"][fechando="true"] QLabel#mesaCartaoTag {{ color: {t['mesa_fechando_borda']}; }}
    QLabel#mesaCartaoValor {{ color: {t['texto']}; font-size: 13px; font-weight: 800; background: transparent; }}
    QLabel#mesaCartaoNome {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}
    /* Vermelho Ferrari (2026-09-08), no lugar do ciano. O ciano dizia
       "estado normal, nada a ver aqui" — e mesa ocupada é justamente onde
       está o dinheiro em aberto do salão, o que o operador precisa achar de
       relance numa grade de oito colunas. Vermelho de PERIGO continua sendo
       outro token (`perigo`), e continua só em ação destrutiva: o que estes
       cards usam é a família `mesa_ocupada_*`, que existe só para eles. */
    QFrame[variante="mesa"][ocupada="true"] {{
      background: {t['mesa_ocupada_bg']};
      border: 1px solid {t['mesa_ocupada_borda']};
      border-top: 3px solid {t['mesa_ocupada_borda']};
    }}
    /* O `:hover` genérico lá em cima repinta o card com `superficie_2`, que
       era invisível enquanto ocupada TINHA essa cor de fundo. Com o corpo
       tingido de vermelho ele passaria a apagar o tingimento quando o mouse
       passa por cima — e a mesa cheia piscaria cinza. Esta regra devolve o
       vermelho no hover, e a ordem em que ela aparece é o que a faz vencer. */
    QFrame[variante="mesa"][ocupada="true"]:hover {{
      background: {t['mesa_ocupada_bg']};
    }}
    /* O número da mesa e o valor em aberto são o conteúdo do card ocupado, e
       `texto` não sabe que o fundo mudou: no tema claro ele é quase preto
       sobre o pastel avermelhado. Daí o `mesa_ocupada_texto`, que a paleta já
       trazia desde o redesign "Vívido" e que só agora ficou necessário. */
    QFrame[variante="mesa"][ocupada="true"] QLabel#mesaCartaoNumero,
    QFrame[variante="mesa"][ocupada="true"] QLabel#mesaCartaoValor {{
      color: {t['mesa_ocupada_texto']};
    }}
    /* "Fechando" = comanda em conferência (pré-conta emitida) numa mesa
       ocupada -- sobrepõe a cor de "ocupada" acima. */
    QFrame[variante="mesa"][fechando="true"] {{
      background: {t['mesa_bg']};
      border: 1px solid {t['mesa_fechando_borda']};
      border-top: 3px solid {t['mesa_fechando_borda']};
    }}

    /* ---------- Tela de Mesas: cabeçalho, filtros, container do grid ---------- */

    QLabel#mesasTitulo {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#mesasSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; background: transparent; }}

    QPushButton[variante="filtro-pill"] {{
      background: {t['superficie_2']};
      color: {t['texto_fraco']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
      padding: 7px 16px;
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton[variante="filtro-pill"]:hover {{ color: {t['texto']}; }}
    QPushButton[variante="filtro-pill"][ativo="true"] {{
      background: {t['superficie_2']};
      color: {t['acento']};
      border: 1px solid {t['acento']};
    }}

    QFrame#mesasContainer {{
      background: {t['bg_terminal']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    /* ---------- Painel direito (resumo do salão + comandas ativas) ---------- */

    QFrame#painelResumoSalao, QFrame#painelComandasAtivas {{
      background: {t['mesa_bg']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#painelTituloSecao {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#painelValorGrande {{ color: {t['texto']}; font-size: 32px; font-weight: 800; background: transparent; }}
    QLabel#painelRotuloMini {{ color: {t['texto_fraco']}; font-size: 11px; font-weight: 600; background: transparent; }}
    QFrame#painelBarraTrilho {{ background: {t['borda']}; border-radius: 3px; }}
    QFrame#painelBarraPreenchida {{ background: {t['acento']}; border-radius: 3px; }}

    QFrame#painelMiniStat {{
      background: {t['superficie_2']};
      border-radius: 10px;
    }}
    QLabel#painelMiniStatValor {{ color: {t['texto']}; font-size: 17px; font-weight: 800; background: transparent; }}
    QLabel#painelMiniStatRotulo {{ color: {t['texto_fraco']}; font-size: 10px; font-weight: 600; background: transparent; }}

    QLabel#comandaListaMesa {{ color: {t['texto']}; font-size: 13px; font-weight: 700; background: transparent; }}
    QLabel#comandaListaAtendente {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}
    QLabel#comandaListaValor {{ color: {t['texto']}; font-size: 13px; font-weight: 800; background: transparent; }}
    QLabel#comandaListaPontoOcupada {{ color: {t['mesa_ocupada_borda']}; font-size: 10px; background: transparent; }}
    QLabel#comandaListaPontoFechando {{ color: {t['mesa_fechando_borda']}; font-size: 10px; background: transparent; }}
    QLabel#painelMiniStatDotLivre {{ color: {t['sucesso']}; font-size: 9px; background: transparent; }}
    QLabel#painelMiniStatDotOcupada {{ color: {t['mesa_ocupada_borda']}; font-size: 9px; background: transparent; }}
    QLabel#painelMiniStatDotFechando {{ color: {t['mesa_fechando_borda']}; font-size: 9px; background: transparent; }}

    /* ---------- Painéis / cartões ---------- */

    QFrame[variante="cartao"] {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}

    /* ---------- Tabelas ---------- */

    QTableWidget, QTableView {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
      gridline-color: {t['borda']};
    }}
    QHeaderView::section {{
      background: {t['superficie_2']};
      color: {t['texto_fraco']};
      padding: 10px 12px;
      border: none;
      border-bottom: 1px solid {t['borda']};
      text-transform: uppercase;
      font-size: 11px;
    }}
    QTableWidget::item, QTableView::item {{
      padding: 8px 12px;
      border-bottom: 1px solid {t['borda']};
    }}
    QTableWidget::item:selected, QTableView::item:selected {{ background: {t['superficie_2']}; }}

    /* ---------- Tabelas da Comanda (itens pendentes/lançados) ---------- */

    QTableWidget#tabela-comanda {{
      background: transparent;
      border: none;
      border-radius: 0px;
      gridline-color: transparent;
      outline: none;
    }}
    QTableWidget#tabela-comanda::item {{
      padding: 2px 12px;
      border-bottom: 1px solid {t['tabela_comanda_borda']};
      color: {t['tabela_comanda_texto']};
      font-weight: 600;
      font-size: 14px;
    }}
    QTableWidget#tabela-comanda::item:selected {{
      background: {t['tabela_comanda_selecionado_bg']};
      color: {t['tabela_comanda_texto']};
      outline: none;
    }}
    QTableWidget#tabela-comanda::item:hover {{
      background: {t['tabela_comanda_selecionado_bg']};
    }}
    QTableWidget#tabela-comanda QHeaderView::section {{
      background: transparent;
      color: {t['secao_texto_fraco']};
      padding: 6px 12px;
      border: none;
      border-bottom: 1px solid {t['tabela_comanda_borda']};
      text-transform: uppercase;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.2px;
    }}

    /* ---------- Cards de seção da Comanda ---------- */

    #secao-pendentes {{
      background: {t['secao_pendentes_bg']};
      border: 1px solid {t['secao_pendentes_borda']};
      border-radius: 16px;
      padding: 8px;
    }}
    #titulo-secao-pendentes {{
      color: {t['secao_pendentes_titulo']};
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
    }}
    #secao-lancados {{
      background: {t['secao_lancados_bg']};
      border: 1px solid {t['borda_card']};
      border-radius: 16px;
      padding: 8px;
    }}
    #titulo-secao-lancados {{
      color: {t['secao_texto_fraco']};
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
    }}

    /* ---------- Barra de total (Comanda) ---------- */

    #barra-total {{
      background: {t['barra_total_bg']};
      border-radius: 10px;
      border: none;
      min-height: 34px;
    }}
    #barra-total-rotulo {{
      color: {t['barra_total_texto']};
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      margin-right: 10px;
      background: transparent;
    }}
    #barra-total-valor {{
      color: {t['barra_total_texto_forte']};
      font-size: 18px;
      font-weight: 900;
      background: transparent;
    }}

    /* ---------- Labels auxiliares ---------- */

    QLabel[variante="fraco"] {{ color: {t['texto_fraco']}; }}

    /* ---------- Linha de erro/aviso das telas (§3.15) ----------
       Estas cores viviam em ~14 cópias de `setStyleSheet` inline, resolvidas
       na construção da tela. Como o stylesheet por widget vence o QSS global,
       a paleta do boot ficava congelada ali e a troca de tema não alcançava
       essas linhas. Aqui elas voltam a acompanhar o tema. */

    QLabel#labelErro {{ color: {t['perigo']}; font-size: 12px; background: transparent; }}
    QLabel#labelErro[tom="sucesso"] {{ color: {t['sucesso']}; }}

    /* Âmbar, e não vermelho, de propósito: impressão que falha não interrompe
       a venda — ver o docstring de `AvisoDeImpressao`. */
    QLabel#avisoImpressao {{ color: {t['texto_fraco']}; font-size: 12px; background: transparent; }}
    QLabel#avisoImpressao[tom="sucesso"] {{ color: {t['sucesso']}; }}
    QLabel#avisoImpressao[tom="aviso"] {{ color: {t['aviso']}; }}

    /* Demais cores que estavam congeladas em `setStyleSheet` de construção
       (§3.15). Todas seguem a mesma regra: quem pinta é o QSS, quem escolhe o
       estado é uma propriedade ou o objectName. */

    QLabel#dicaFraca {{ color: {t['texto_fraquissimo']}; font-size: 11px; background: transparent; }}
    QLabel#comandaCelulaTexto {{ color: {t['tabela_comanda_texto']}; }}

    /* Tempo na cozinha: cinza até 30 min, âmbar até 1 h, vermelho depois. */
    QLabel#comandaHorario {{ font-size: 13px; margin-left: 8px; color: {t['texto_fraquissimo']}; }}
    QLabel#comandaHorario[tom="aviso"] {{ color: {t['aviso']}; }}
    QLabel#comandaHorario[tom="perigo"] {{ color: {t['perigo']}; }}

    QLabel#campoErroRotulo {{ color: {t['campo_erro_texto']}; font-size: 11px; background: transparent; }}
    QLineEdit[erro="true"] {{
      border: 1px solid {t['campo_erro_texto']};
      background-color: {t['campo_erro_bg']};
    }}

    /* Barra de margem do cardápio. O trilho é a mesma transparência nos dois
       temas — literal, e não token, porque não existe cor de paleta para ele e
       inventar uma seria decisão de design, não faxina. */
    QFrame#margemTrilho {{ background: rgba(255, 255, 255, 0.08); border-radius: 3px; }}
    QFrame#margemPreenchida {{ background: {t['sucesso']}; border-radius: 3px; }}

    /* Comprovante digital de fechamento. Era o último widget lendo as
       "constantes planas" de `tokens.py` — o bloco inteiro morreu com isto. */
    QDialog#comprovanteDialog {{ background: {t['superficie']}; }}
    QPlainTextEdit#comprovantePapel {{
      background: {t['bg_terminal']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
      padding: 16px;
      selection-background-color: {t['acento']};
    }}
    QLabel#comprovanteStatus {{ color: {t['texto_fraco']}; font-size: 12px; }}

    QLabel#comandaTitulo {{ font-weight: 800; font-size: 32px; color: {t['texto']}; }}
    QLabel#comandaRotuloAtendeu {{
      color: {t['combo_atendente_borda']};
      font-size: 13px;
      font-weight: 500;
    }}

    QLabel#badgeCombo {{
      background-color: {t['badge_combo_bg']};
      color: {t['badge_combo_texto']};
      font-weight: 700;
      font-size: 11px;
      border-radius: 4px;
      padding: 3px 10px;
      margin: 0px;
    }}

    /* ---------- Cardapio: arvore, grupos e subcategoria (§9.9) ----------
       A tela virou a hierarquia Categoria -> Subcategoria -> Produtos, e este
       bloco veste os tres niveis dela.

       O selo que o §9.8 punha na LINHA de cada produto saiu: ele repetia, uma
       vez por item, o que o cabecalho de grupo agora diz uma vez -- e disputava
       largura justamente com o nome do produto. A familia de cor dele ficou, e
       agora veste o cabecalho de grupo e as pilulas de filtro. */

    /* Os eyebrows do Cardapio (CATEGORIAS, o "ACOMPANHAMENTOS · COZINHA" do
       painel da direita e a dica do rodape) sao o mesmo tipo de texto -- caixa
       alta atenuada, o "carimbo" que diz o que vem a seguir. Uma declaracao so
       para os tres: tres poderiam divergir. */
    QLabel#cardapioEyebrow {{
      color: {t['texto_fraco']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#cardapioTituloPainel {{
      color: {t['texto']};
      font-size: 16px;
      font-weight: 700;
      background: transparent;
    }}

    /* ---- A arvore da esquerda ---- */
    QTreeWidget#arvoreCardapio {{
      background: transparent;
      border: none;
      outline: none;
    }}
    /* Sem `border-radius` de proposito: a linha da subcategoria tem DUAS
       colunas (nome e contagem), cada uma com o seu retangulo de item, e o
       arredondamento produzia duas pilulas separadas por uma fresta no meio da
       faixa selecionada. Faixa continua e chapada e o que o olho le como UMA
       linha. */
    QTreeWidget#arvoreCardapio::item {{
      border-radius: 0;
      color: {t['texto_fraco']};
      font-size: 12px;
      font-weight: 600;
    }}
    /* O item de CATEGORIA hospeda um widget proprio (nome + subtitulo +
       badge), entao o que o estado de selecao pinta nele e so o fundo; as
       cores do texto vem do widget. O de SUBCATEGORIA e texto puro do proprio
       item, e por isso acende no acento quando selecionado -- e o unico sinal
       de qual subdivisao a tabela da direita esta mostrando. */
    QTreeWidget#arvoreCardapio::item:hover {{ background: {t['superficie_2']}; }}
    QTreeWidget#arvoreCardapio::item:selected {{
      background: {t['superficie_2']};
      color: {t['texto']};
    }}
    QTreeWidget#arvoreCardapio::item:selected:!has-children {{
      background: {t['acento']};
      color: {t['acento_texto']};
    }}
    /* A area de `::branch` e o recuo do filho, e o Qt a pinta com o azul de
       selecao da paleta do sistema quando a linha esta selecionada -- um
       quadrado de outra cor colado na faixa ambar. Transparente nos dois
       estados: o recuo fica sendo recuo, e nao um segundo destaque. */
    QTreeWidget#arvoreCardapio::branch,
    QTreeWidget#arvoreCardapio::branch:selected,
    QTreeWidget#arvoreCardapio::branch:hover {{ background: transparent; }}
    QTreeWidget#arvoreCardapio QScrollBar:vertical {{
      background: transparent;
      width: 6px;
      margin: 2px 0 2px 0;
    }}
    QTreeWidget#arvoreCardapio QScrollBar::handle:vertical {{
      background: {t['botao_circular_hover']};
      border-radius: 3px;
      min-height: 20px;
    }}
    QTreeWidget#arvoreCardapio QScrollBar::add-line:vertical,
    QTreeWidget#arvoreCardapio QScrollBar::sub-line:vertical {{ height: 0; }}
    QTreeWidget#arvoreCardapio QScrollBar::add-page:vertical,
    QTreeWidget#arvoreCardapio QScrollBar::sub-page:vertical {{ background: transparent; }}

    /* `celulaTransparente` veste os embrulhos de celula de tabela. Existia como
       `setStyleSheet("background: transparent")` no proprio widget, e isso
       DESCE PARA OS FILHOS vencendo o QSS global -- foi o que apagou o fundo
       dos badges assim que eles passaram a se vestir por objectName. Aqui a
       regra e do seletor, e nao do widget, entao ela para no pai. */
    QWidget#celulaTransparente {{ background: transparent; }}
    QLabel#margemPercentual {{
      background: transparent;
      font-size: 12px;
      font-weight: 600;
      color: {t['texto']};
    }}

    QWidget#linhaCategoria {{ background: transparent; }}
    QLabel#categoriaSeta {{
      color: {t['texto_fraquissimo']};
      font-size: 13px;
      font-weight: 700;
      background: transparent;
    }}
    QLabel#categoriaNome {{
      color: {t['texto']};
      font-size: 12px;
      font-weight: 700;
      background: transparent;
    }}
    QLabel#categoriaSubtitulo {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.6px;
      background: transparent;
    }}

    /* ---- O cabecalho de grupo, dentro da tabela ---- */
    QWidget#grupoSubcategoria {{
      background: {t['subcategoria_grupo_bg']};
      border-top: 1px solid {t['subcategoria_grupo_borda']};
      border-bottom: 1px solid {t['subcategoria_grupo_borda']};
    }}
    QWidget#grupoGlifo {{ background: transparent; }}
    QLabel#grupoNome {{
      color: {t['subcategoria_grupo_texto']};
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 1.2px;
      background: transparent;
    }}
    QLabel#grupoContagem {{
      color: {t['subcategoria_grupo_contagem']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.8px;
      background: transparent;
    }}
    QLabel#produtoNome {{ background: transparent; color: {t['texto']}; }}

    /* ---- As pilulas de filtro, entre a busca e a tabela ---- */
    QPushButton#pillSubcategoria {{
      padding: 5px 12px;
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      color: {t['texto_fraco']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
    }}
    QPushButton#pillSubcategoria:hover {{ color: {t['texto']}; }}
    QPushButton#pillSubcategoria[ativa="true"] {{
      background: {t['acento']};
      border-color: {t['acento']};
      color: {t['acento_texto']};
    }}

    /* ---- Os badges de status, agora por objectName ----
       Sairam do `setStyleSheet` de `cardapio_view` para ca (§3.15): la a cor
       era resolvida na construcao da linha, e a tabela so acompanhava o
       alternador Claro/Escuro porque e repovoada a cada refresh. A arvore, que
       nao e, mostraria a cor do boot para sempre. */
    QLabel#badgeAtivo, QLabel#badgeDesativado, QLabel#badgeVazio {{
      font-weight: 700;
      font-size: 11px;
      border-radius: 4px;
      padding: 3px 10px;
      margin: 0px;
    }}
    /* Dentro da arvore o mesmo selo e um degrau menor: la ele divide a coluna
       com o nome da categoria, e nome de categoria cortado e o defeito que esta
       tela veio consertar. Os seletores sao os TRES ids, e nao
       `#linhaCategoria QLabel`: a regra ampla pegava tambem o nome e o
       subtitulo da linha, e encolhia os dois para 9px. */
    QWidget#linhaCategoria QLabel#badgeAtivo,
    QWidget#linhaCategoria QLabel#badgeDesativado,
    QWidget#linhaCategoria QLabel#badgeVazio {{ font-size: 9px; padding: 2px 7px; }}
    QLabel#badgeAtivo {{
      background-color: {t['badge_ativo_bg']};
      color: {t['badge_ativo_texto']};
    }}
    QLabel#badgeDesativado {{
      background-color: {t['badge_desativado_bg']};
      color: {t['badge_desativado_texto']};
    }}
    QLabel#badgeVazio {{
      background-color: {t['badge_vazio_bg']};
      color: {t['badge_vazio_texto']};
    }}

    QComboBox#seletorSubcategoria {{ min-width: 180px; }}

    /* ---------- Modal "Nova subcategoria" (`widgets/subcategoria_dialog.py`)
       Setimo modal em cartao do app, e por isso o setimo a NAO poder herdar o
       `QDialog {{ background }}` la de cima: a janela e frameless e translucida
       para os cantos de 16px sairem redondos de verdade. O ✕, o Cancelar e o
       Confirmar nao aparecem aqui porque ja estao declarados nas familias
       compartilhadas com o modal "Adicionar item". */

    QDialog#subDialog {{ background: transparent; }}
    QWidget#subDialogGlifo {{ background: transparent; }}
    QFrame#subDialogCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QFrame#subDialogIcone {{
      background: {t['subcategoria_grupo_bg']};
      border: 1px solid {t['subcategoria_grupo_borda']};
      border-radius: 21px;
    }}
    QLabel#subDialogTitulo {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}
    QLabel#subDialogSubtitulo {{
      color: {t['texto_fraco']};
      font-size: 12px;
      background: transparent;
    }}
    QLabel#subDialogRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QFrame#subDialogContexto {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#subDialogDestino {{
      color: {t['subcategoria_glifo']};
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1px;
      background: transparent;
    }}
    QFrame#subDialogCaixa {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QFrame#subDialogCaixa[foco="true"] {{ border: 1px solid {t['acento']}; }}
    QLineEdit#subDialogCampo {{
      background: transparent;
      border: none;
      padding: 0;
      color: {t['texto']};
      font-size: 14px;
    }}
    QLabel#subDialogContador {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      background: transparent;
    }}
    /* A linha de aviso troca de papel entre dica, erro e pronto -- mesmo
       mecanismo do rodape do modal "Adicionar item". */
    QLabel#subDialogAviso {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#subDialogAviso[estado="erro"] {{ color: {t['perigo']}; }}
    QLabel#subDialogAviso[estado="ok"] {{ color: {t['sucesso']}; }}
    QWidget#subDialogFaixa {{ background: transparent; }}
    /* As pilulas do "ja existem" sao QLabel e nao QPushButton de proposito:
       elas informam, nao acionam. Um controle cuja unica resposta possivel e
       "ja existe" seria uma armadilha. */
    QLabel#subDialogPill {{
      background: {t['subcategoria_grupo_bg']};
      border: 1px solid {t['subcategoria_grupo_borda']};
      border-radius: 11px;
      padding: 4px 11px;
      color: {t['subcategoria_grupo_texto']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
    }}
    QLabel#subDialogNota {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.8px;
      background: transparent;
    }}

    /* ---- Modal "Confirmar identidade" (`cpf_dono_dialog.py`) e o olho de
       "Senhas e Acesso" (`icone_olho.py`) ----
       Oitavo modal em cartao. Cabecalho, cartao e rodape seguem o mesmo
       desenho dos outros sete; o que e proprio daqui e o visor do CPF e o
       botao de olho. O ✕, o Cancelar e o Confirmar entram nas familias
       compartilhadas mais abaixo. */

    QDialog#cpfDialog {{ background: transparent; }}
    QWidget#iconeOlho {{ background: transparent; }}
    QFrame#cpfDialogCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QFrame#cpfDialogIcone {{
      background: {t['badge_icone_bg']};
      border: 1px solid {t['badge_icone_borda']};
      border-radius: 21px;
    }}
    QLabel#cpfDialogTitulo {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}
    QLabel#cpfDialogSubtitulo {{
      color: {t['badge_icone_glifo']};
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#cpfDialogRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QFrame#cpfDialogContexto {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#cpfDialogAlvo {{
      color: {t['texto']};
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1px;
      background: transparent;
    }}
    /* O visor conta digitos com a pontuacao ja no lugar, entao o espacamento
       entre caracteres e o que separa `123.456.789-01` de um borrao a um metro
       de distancia -- e um metro e a distancia de quem esta de pe no balcao. */
    QLabel#cpfDialogVisor {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      padding: 12px 0px;
      color: {t['texto']};
      font-size: 20px;
      font-weight: 800;
      letter-spacing: 2px;
    }}
    QLabel#cpfDialogInstrucao {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#cpfDialogInstrucao[estado="erro"] {{ color: {t['perigo']}; }}

    /* O olho de cada linha de "Senhas e Acesso". `padding: 0` pelo mesmo
       motivo do ✕ dos modais: num botao de 32px fixos, os 16px de padding
       lateral da regra generica de QPushButton zeram a largura util. O miolo e
       pintado pelo proprio widget (`icone_olho.py`), nao e caractere de fonte,
       entao o que o QSS desenha aqui e so a moldura. */
    QPushButton#botaoOlho {{
      padding: 0;
      background: {t['botao_circular_bg']};
      border: 1px solid {t['botao_circular_borda']};
      border-radius: 10px;
    }}
    QPushButton#botaoOlho:hover {{ background: {t['botao_circular_hover']}; }}
    QPushButton#botaoOlho[revelado="true"] {{ border: 1px solid {t['acento']}; }}

    /* O valor revelado, na propria linha do segredo. Cor de acento e fonte
       maior que a mascara `••••••••` de proposito: e um estado temporario e
       tem que ficar obvio que a tela esta mostrando algo que normalmente nao
       mostra. */
    QLabel#configValorSegredo[revelado="true"] {{
      color: {t['acento']};
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 1px;
      background: transparent;
    }}

    QLabel[variante="badge"] {{
      background: {t['sucesso']};
      color: white;
      border-radius: 999px;
      padding: 3px 10px;
      font-size: 10px;
    }}
    QLabel[variante="badge"][status="ocupada"] {{ background: {t['mesa_ocupada_borda']}; }}
    QLabel[variante="badge"][status="fechada"], QLabel[variante="badge"][status="inativo"] {{
      background: {t['borda']};
      color: {t['texto_fraco']};
    }}
    QLabel[variante="badge"][status="cancelada"], QLabel[variante="badge"][status="perigo"] {{
      background: {t['perigo']};
    }}

    /* ---------- Tela de Caixa: dashboard financeiro do turno ---------- */

    QLabel#caixaEyebrow {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#caixaTitulo {{ color: {t['texto']}; font-size: 22px; font-weight: 800; background: transparent; }}
    QLabel#caixaSubtitulo {{ color: {t['texto_fraco']}; font-size: 12px; background: transparent; }}

    QScrollArea#caixaRolagemResumo {{ background: transparent; border: none; }}
    QScrollArea#caixaRolagemResumo > QWidget > QWidget {{ background: transparent; }}

    QFrame#caixaCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#caixaCardRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#caixaValorGrande {{ color: {t['texto']}; font-size: 30px; font-weight: 800; background: transparent; }}

    QFrame#caixaMiniStat {{
      background: {t['superficie_2']};
      border-radius: 10px;
    }}
    QLabel#caixaMiniStatRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#caixaMiniStatValor {{ color: {t['texto']}; font-size: 16px; font-weight: 800; background: transparent; }}

    QLabel#caixaFormaNome {{ color: {t['texto']}; font-size: 12px; font-weight: 600; background: transparent; }}
    QLabel#caixaFormaValor {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QProgressBar#caixaBarraPagamento {{
      background: {t['borda']};
      border: none;
      border-radius: 2px;
      max-height: 4px;
      min-height: 4px;
    }}
    QProgressBar#caixaBarraPagamento::chunk {{ background: {t['acento']}; border-radius: 2px; }}

    QLabel#caixaAjusteRotulo {{ color: {t['texto']}; font-size: 12px; background: transparent; }}
    QLabel#caixaAjusteValor {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QLabel#caixaAjusteValorNegativo {{ color: {t['perigo_hover']}; font-size: 12px; font-weight: 700; background: transparent; }}

    QFrame#caixaMovimentosCard {{
      background: {t['bg_terminal']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#caixaMovimentosTitulo {{ color: {t['texto']}; font-size: 15px; font-weight: 700; background: transparent; }}
    QLabel#caixaMovimentosSubtitulo {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}

    QLabel[variante="badgeMovimento"] {{
      border: 1px solid;
      border-radius: 999px;
      padding: 2px 10px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: transparent;
    }}
    QLabel[variante="badgeMovimento"][tipo="reforco"] {{ color: {t['sucesso']}; border-color: {t['sucesso']}; }}
    QLabel[variante="badgeMovimento"][tipo="sangria"] {{ color: {t['perigo_hover']}; border-color: {t['perigo_hover']}; }}
    /* `ciano_metrica`, e não `mesa_ocupada_borda`: despesa de caixa não tem
       relação nenhuma com mesa ocupada — o que este seletor queria era a cor,
       e o empréstimo só apareceu quando a mesa ocupada virou vermelha. */
    QLabel[variante="badgeMovimento"][tipo="despesa"] {{ color: {t['ciano_metrica']}; border-color: {t['ciano_metrica']}; }}

    QFrame#caixaMiniCard {{
      background: {t['mesa_bg']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#caixaMiniCardTitulo {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QLabel#caixaMiniCardSub {{ color: {t['texto_fraquissimo']}; font-size: 10px; letter-spacing: 0.4px; background: transparent; }}
    QLabel#caixaMiniCardValorPositivo {{ color: {t['sucesso']}; font-size: 11px; font-weight: 700; background: transparent; }}
    QLabel#caixaMiniCardValorNegativo {{ color: {t['perigo_hover']}; font-size: 11px; font-weight: 700; background: transparent; }}
    QLabel#caixaMiniCardValorNeutro {{ color: {t['texto_fraco']}; font-size: 11px; font-weight: 700; background: transparent; }}

    QPushButton[variante="pilula-vazia"] {{
      background: transparent;
      color: {t['texto']};
      border: 1px solid {t['borda']};
      border-radius: 18px;
      padding: 7px 18px;
      font-size: 12px;
      font-weight: 600;
    }}
    QPushButton[variante="pilula-vazia"]:hover {{ background: {t['superficie_2']}; }}
    QPushButton[variante="pilula-vazia"]:disabled {{ color: {t['texto_fraquissimo']}; }}

    /* `SecaoCancelamentos` (Caixa e Histórico): sem isto, o QWidget e seus
       QLabel herdam o fundo opaco global e pintam um retângulo escuro por
       cima do card mais claro em que o widget é embutido. */
    QWidget#secaoCancelamentos, QWidget#secaoCancelamentos QLabel {{ background: transparent; }}

    /* ---------- Central de Loja ---------- */

    QLabel#centralLojaBreadcrumb {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#centralLojaTitulo {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#centralLojaSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; background: transparent; }}
    QLabel#centralLojaSecaoTitulo {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    QFrame[variante="loja-hub-card"] {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QFrame[variante="loja-hub-card"]:hover {{
      background: {t['superficie_2']};
      border: 1px solid {t['acento']};
    }}
    QLabel[variante="loja-hub-icone"] {{
      background: {t['superficie_2']};
      color: {t['acento']};
      border-radius: 10px;
      font-size: 18px;
      font-weight: 800;
    }}
    QLabel[variante="loja-hub-card-titulo"] {{
      color: {t['texto']};
      font-size: 14px;
      font-weight: 700;
      background: transparent;
    }}
    QLabel[variante="loja-hub-card-subtitulo"] {{
      color: {t['texto_fraco']};
      font-size: 11px;
      background: transparent;
    }}
    QPushButton[variante="voltar-pdv"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      padding: 10px 18px;
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton[variante="voltar-pdv"]:hover {{ background: {t['borda']}; }}

    /* ---------- Configurações ---------- */

    QLabel#configEyebrow {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#configTitulo {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#configSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; background: transparent; }}
    QLabel#configSecaoTitulo {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QFrame#configCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QScrollArea#configRolagem {{ background: transparent; border: none; }}
    QScrollArea#configRolagem > QWidget > QWidget {{ background: transparent; }}

    /* ---------- Modais ---------- */

    QDialog {{ background: {t['superficie']}; }}

    /* ---------- Modal de PIN com numpad (`widgets/pin_pad_dialog.py`) ----------
       O cartao e um QFrame DENTRO do dialogo, nao o dialogo: a janela e
       frameless e translucida para os cantos de 16px aparecerem redondos de
       verdade, entao ela nao pode herdar o `QDialog {{ background }}` acima. */

    QDialog#pinPadDialog {{ background: transparent; }}
    QWidget#modalBackdrop {{ background: transparent; }}
    QWidget#pinPadCadeado {{ background: transparent; }}

    QFrame#pinPadCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    QFrame#pinPadIcone {{
      background: {t['badge_icone_bg']};
      border: 1px solid {t['badge_icone_borda']};
      border-radius: 12px;
    }}

    QLabel#pinPadTitulo {{
      color: {t['texto']};
      font-size: 16px;
      font-weight: 800;
      background: transparent;
    }}
    QLabel#pinPadSubtitulo {{
      color: {t['texto_fraco']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#pinPadInstrucao {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#pinPadInstrucao[estado="erro"] {{ color: {t['perigo']}; }}

    /* A pergunta por extenso, so no PIN de exclusao (`para_exclusao`). Cartao
       proprio com borda de perigo: e o unico uso do teclado de PIN em que
       digitar certo APAGA alguma coisa, e o cartao tem que dizer isso antes do
       primeiro digito. */
    QLabel#pinPadMensagem {{
      color: {t['texto']};
      font-size: 12px;
      background: {t['pin_exclusao_bg']};
      border: 1px solid {t['pin_exclusao_borda']};
      border-radius: 10px;
      padding: 10px 12px;
    }}

    QPushButton#pinPadFechar {{
      /* `padding: 0` NAO e decoracao: a regra generica de QPushButton la em
         cima pede 16px de padding lateral, e num botao de 32px fixos isso
         zera a largura util e o Qt descarta o glifo -- o botao saia como um
         circulo vazio. Vale para toda tecla de tamanho fixo daqui. */
      padding: 0;
      background: {t['botao_circular_bg']};
      border: 1px solid {t['botao_circular_borda']};
      border-radius: 16px;
      color: {t['botao_circular_texto']};
      font-size: 13px;
      font-weight: 700;
    }}
    QPushButton#pinPadFechar:hover {{
      background: {t['botao_circular_hover']};
      color: {t['texto']};
    }}

    QFrame#pinPadDot {{ background: {t['pin_dot_vazio']}; border-radius: 5px; }}
    QFrame#pinPadDot[estado="cheio"] {{ background: {t['pin_dot_cheio']}; }}
    QFrame#pinPadDot[estado="erro"] {{ background: {t['perigo']}; }}

    QPushButton#pinPadTecla, QPushButton#teclaNumerica {{
      padding: 0;
      background: {t['tecla_numerica_bg']};
      border: 1px solid {t['tecla_numerica_borda']};
      border-radius: 10px;
      color: {t['texto']};
      font-size: 18px;
      font-weight: 700;
    }}
    QPushButton#pinPadTecla:hover,
    QPushButton#teclaNumerica:hover {{ background: {t['tecla_numerica_hover']}; }}
    QPushButton#pinPadTecla:pressed,
    QPushButton#teclaNumerica:pressed {{ background: {t['tecla_numerica_pressed']}; }}

    QPushButton#pinPadConfirmar {{
      padding: 0 8px;
      background: {t['pin_confirmar_bg']};
      border: 1px solid {t['pin_confirmar_bg']};
      border-radius: 10px;
      color: {t['pin_confirmar_texto']};
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 1px;
    }}
    QPushButton#pinPadConfirmar:hover {{
      background: {t['pin_confirmar_hover']};
      border-color: {t['pin_confirmar_hover']};
    }}

    QPushButton#pinPadCancelar {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
      color: {t['texto_fraco']};
      font-size: 12px;
      font-weight: 700;
      padding: 10px;
    }}
    QPushButton#pinPadCancelar:hover {{ color: {t['texto']}; }}

    /* ---------- Modal "Adicionar item" (`widgets/adicionar_item_dialog.py`) ----
       Mesmo arranjo do modal de PIN: o cartao e um QFrame DENTRO do dialogo,
       porque a janela e frameless e translucida (cantos de 16px redondos de
       verdade) e por isso nao pode herdar o `QDialog {{ background }}`. */

    QDialog#addItemDialog {{ background: transparent; }}
    QWidget#addItemLupa {{ background: transparent; }}

    QFrame#addItemCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    QLabel#addItemContexto {{
      color: {t['texto_fraco']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#addItemTitulo {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}

    /* `padding: 0` NAO e decoracao: a regra generica de QPushButton pede 16px
       de padding lateral, e num botao de lado fixo isso zera a largura util e
       o Qt descarta o glifo -- o botao sai como um circulo vazio. Vale para o
       fechar e para os dois passos de quantidade. */
    QPushButton#addItemFechar, QPushButton#addItemPasso, QPushButton#funcDialogFechar,
    QPushButton#movCaixaFechar, QPushButton#turnoFechar, QPushButton#subDialogFechar,
    QPushButton#cpfDialogFechar {{
      padding: 0;
      background: {t['botao_circular_bg']};
      border: 1px solid {t['botao_circular_borda']};
      color: {t['botao_circular_texto']};
      font-weight: 700;
    }}
    QPushButton#addItemFechar, QPushButton#funcDialogFechar,
    QPushButton#movCaixaFechar, QPushButton#turnoFechar,
    QPushButton#subDialogFechar, QPushButton#cpfDialogFechar {{ border-radius: 16px; font-size: 13px; }}
    QPushButton#addItemPasso {{ border-radius: 17px; font-size: 18px; }}
    QPushButton#addItemFechar:hover, QPushButton#addItemPasso:hover,
    QPushButton#funcDialogFechar:hover, QPushButton#movCaixaFechar:hover,
    QPushButton#turnoFechar:hover, QPushButton#subDialogFechar:hover,
    QPushButton#cpfDialogFechar:hover {{
      background: {t['botao_circular_hover']};
      color: {t['texto']};
    }}
    QPushButton#addItemPasso:disabled {{
      color: {t['pilula_disabled_texto']};
      background: {t['botao_circular_bg']};
    }}

    QFrame#addItemBuscaCaixa {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QFrame#addItemBuscaCaixa[foco="true"] {{ border: 1px solid {t['acento']}; }}
    QLineEdit#addItemBusca {{
      background: transparent;
      border: none;
      padding: 0;
      color: {t['texto']};
      font-size: 13px;
    }}
    QLabel#addItemDicaEnter {{
      color: {t['texto_fraquissimo']};
      font-size: 8px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    QScrollArea#addItemFaixa {{ background: transparent; border: none; }}
    QScrollArea#addItemFaixa > QWidget > QWidget {{ background: transparent; }}
    QScrollArea#addItemFaixa QScrollBar:vertical {{
      background: transparent;
      width: 5px;
      margin: 0;
    }}
    QScrollArea#addItemFaixa QScrollBar::handle:vertical {{
      background: {t['botao_circular_hover']};
      border-radius: 2px;
      min-height: 16px;
    }}
    QScrollArea#addItemFaixa QScrollBar::add-line:vertical,
    QScrollArea#addItemFaixa QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollArea#addItemFaixa QScrollBar::add-page:vertical,
    QScrollArea#addItemFaixa QScrollBar::sub-page:vertical {{ background: transparent; }}

    QPushButton#addItemCategoria {{
      padding: 5px 12px;
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      color: {t['texto_fraco']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
    }}
    QPushButton#addItemCategoria:hover {{ color: {t['texto']}; }}
    QPushButton#addItemCategoria[ativa="true"] {{
      background: {t['acento']};
      border-color: {t['acento']};
      color: {t['acento_texto']};
    }}

    /* O contêiner usa a MESMA superfície do cartão de propósito: só a borda
       o delimita, e o degrau para `superficie_2` fica reservado para a linha
       destacada (pintada pelo delegado). Com os dois na mesma cor, o único
       sinal de qual linha o Enter vai lançar seria a barra âmbar. */
    QListWidget#addItemLista {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      padding: 4px;
      outline: none;
    }}
    /* A barra padrao do sistema e larga, cinza e desenha setas nas pontas --
       peso visual que o cartao nao comporta. Aqui ela vira um trilho de 6px
       sem botao, que so aparece quando a lista passa da altura do cartao. */
    QListWidget#addItemLista QScrollBar:vertical {{
      background: transparent;
      width: 6px;
      margin: 4px 2px 4px 0;
    }}
    QListWidget#addItemLista QScrollBar::handle:vertical {{
      background: {t['botao_circular_hover']};
      border-radius: 3px;
      min-height: 24px;
    }}
    QListWidget#addItemLista QScrollBar::add-line:vertical,
    QListWidget#addItemLista QScrollBar::sub-line:vertical {{ height: 0; }}
    QListWidget#addItemLista QScrollBar::add-page:vertical,
    QListWidget#addItemLista QScrollBar::sub-page:vertical {{ background: transparent; }}

    QFrame#addItemRodape {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#addItemRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#addItemQuantidade {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}
    QLineEdit#addItemObservacao {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
      padding: 9px 12px;
      color: {t['texto']};
      font-size: 12px;
    }}
    QLineEdit#addItemObservacao:focus {{ border: 1px solid {t['acento']}; }}
    QLabel#addItemTotal {{
      color: {t['acento']};
      font-size: 20px;
      font-weight: 800;
      background: transparent;
    }}

    /* Uma linha so no rodape, que troca de texto e de cor entre a dica de uso,
       o erro do service e o aviso de item lancado. Tres linhas empilhadas
       mudariam a altura do cartao no meio do lancamento, e cartao que pula de
       tamanho e o que faz o dedo errar o botao. */
    QLabel#addItemAviso {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#addItemAviso[estado="erro"] {{ color: {t['perigo']}; }}
    QLabel#addItemAviso[estado="sucesso"] {{ color: {t['sucesso']}; }}

    QPushButton#subDialogCancelar,
    QPushButton#cpfDialogCancelar,
    QPushButton#addItemCancelar, QPushButton#funcDialogCancelar,
    QPushButton#movCaixaCancelar, QPushButton#turnoCancelar {{
      padding: 9px 20px;
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 18px;
      color: {t['texto']};
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton#subDialogCancelar:hover,
    QPushButton#cpfDialogCancelar:hover,
    QPushButton#addItemCancelar:hover, QPushButton#funcDialogCancelar:hover,
    QPushButton#movCaixaCancelar:hover,
    QPushButton#turnoCancelar:hover {{ background: {t['botao_circular_hover']}; }}

    QPushButton#addItemConfirmar, QPushButton#funcDialogConfirmar,
    QPushButton#subDialogConfirmar,
    QPushButton#cpfDialogConfirmar {{
      padding: 9px 22px;
      background: {t['acento']};
      border: 1px solid {t['acento']};
      border-radius: 18px;
      color: {t['acento_texto']};
      font-size: 12px;
      font-weight: 800;
    }}
    QPushButton#addItemConfirmar:hover, QPushButton#funcDialogConfirmar:hover,
    QPushButton#subDialogConfirmar:hover,
    QPushButton#cpfDialogConfirmar:hover {{
      background: {t['acento_hover']};
      border-color: {t['acento_hover']};
    }}
    QPushButton#addItemConfirmar:disabled, QPushButton#funcDialogConfirmar:disabled,
    QPushButton#subDialogConfirmar:disabled,
    QPushButton#cpfDialogConfirmar:disabled {{
      background: {t['pilula_disabled_bg']};
      border-color: {t['pilula_disabled_bg']};
      color: {t['pilula_disabled_texto']};
    }}

    /* ---------- Modal "Novo funcionario" (`widgets/funcionario_dialog.py`) ----
       Terceiro modal em cartao do app, e por isso o terceiro a NAO poder
       herdar o `QDialog {{ background }}` la de cima: a janela e frameless e
       translucida para os cantos de 16px saírem redondos de verdade. O ✕, o
       Cancelar e o Cadastrar nao aparecem aqui porque ja estao declarados nas
       familias compartilhadas com o modal "Adicionar item". */

    QDialog#funcDialog {{ background: transparent; }}
    QWidget#funcDialogGlifo {{ background: transparent; }}

    QFrame#funcDialogCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    QFrame#funcDialogIcone {{
      background: {t['badge_icone_bg']};
      border: 1px solid {t['badge_icone_borda']};
      border-radius: 21px;
    }}

    QLabel#funcDialogTitulo {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}
    QLabel#funcDialogSubtitulo {{
      color: {t['texto_fraco']};
      font-size: 12px;
      background: transparent;
    }}

    /* Os rotulos de campo e o resumo de acesso do rodape sao o mesmo tipo de
       texto -- caixa alta atenuada, o "carimbo" que o app usa para dizer o que
       vem a seguir. Uma declaracao so para os dois: duas poderiam divergir. */
    QLabel#funcDialogRotulo, QLabel#funcDialogResumo {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    QFrame#funcDialogIdentidade {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    /* Circulo de 48px: o raio e metade do lado, senao o Qt desenha um quadrado
       de cantos arredondados. As iniciais usam o ciano de identidade -- o mesmo
       do badge do cabecalho, porque as duas coisas dizem "e esta pessoa". */
    QLabel#funcDialogAvatar {{
      background: {t['botao_circular_bg']};
      border: 1px solid {t['botao_circular_borda']};
      border-radius: 24px;
      color: {t['badge_icone_glifo']};
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 1px;
    }}

    /* Campo dentro de painel: o inverso da superficie do painel, como o campo
       de observacao do modal "Adicionar item" faz dentro do rodape dele. */
    QLineEdit#funcDialogCampo {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
      padding: 9px 12px;
      color: {t['texto']};
      font-size: 13px;
    }}
    QLineEdit#funcDialogCampo:focus {{ border: 1px solid {t['acento']}; }}

    QFrame#funcDialogCargo {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
    }}
    QFrame#funcDialogCargo:hover {{ border: 1px solid {t['texto_fraquissimo']}; }}
    QFrame#funcDialogCargo[selecionado="true"] {{
      background: {t['badge_icone_bg']};
      border: 1px solid {t['badge_icone_glifo']};
    }}
    QLabel#funcDialogCargoNome {{
      color: {t['texto']};
      font-size: 12px;
      font-weight: 800;
      background: transparent;
    }}
    QFrame#funcDialogCargo[selecionado="true"] QLabel#funcDialogCargoNome {{
      color: {t['badge_icone_glifo']};
    }}
    QLabel#funcDialogCargoDescricao {{
      color: {t['texto_fraco']};
      font-size: 11px;
      background: transparent;
    }}
    /* O ✓ esta SEMPRE no layout e so troca de cor: escondê-lo mudaria a
       largura da linha do titulo a cada clique -- ver `_CartaoCargo`. */
    QLabel#funcDialogCargoMarca {{
      color: transparent;
      font-size: 12px;
      font-weight: 800;
      background: transparent;
    }}
    QFrame#funcDialogCargo[selecionado="true"] QLabel#funcDialogCargoMarca {{
      color: {t['badge_icone_glifo']};
    }}

    QPushButton#funcDialogSituacao {{
      padding: 8px 18px;
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
      color: {t['texto_fraquissimo']};
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton#funcDialogSituacao[papel="ativo"][marcada="true"] {{
      background: {t['pilula_ativo_bg']};
      border: 1px solid {t['pilula_ativo_texto']};
      color: {t['pilula_ativo_texto']};
    }}
    /* Inativo marcado nao ganha cor de alerta: desativar alguem e operacao
       normal de fim de contrato, nao erro. O que ele ganha e o contorno e o
       texto plenos, para a escolha nao ficar invisivel. */
    QPushButton#funcDialogSituacao[papel="inativo"][marcada="true"] {{
      border: 1px solid {t['texto_fraco']};
      color: {t['texto']};
    }}

    QFrame#funcDialogDivisor, QFrame#movCaixaDivisor,
    QFrame#turnoDivisor {{ background: {t['borda']}; border: none; }}

    /* ---------- Modal de sangria/reforco/despesa (`widgets/movimentacao_caixa_dialog.py`)
       Quarto modal em cartao do app, e por isso o quarto a NAO poder herdar o
       `QDialog {{ background }}` la de cima: a janela e frameless e translucida
       para os cantos de 16px sairem redondos de verdade.

       Uma classe so veste as tres operacoes: o que muda entre sangria, reforco
       e despesa entra por `[operacao="..."]` nos DOIS lugares onde a operacao
       tem cor -- o badge do cabecalho e o botao que grava. O resto (visor,
       teclas, chips, rodape) e identico nas tres, e por isso e declarado uma
       vez so. O ✕, o Cancelar, as teclas do numpad e o divisor nem aparecem
       aqui: ja estao nas familias compartilhadas com os outros modais. */

    QDialog#movCaixaDialog {{ background: transparent; }}
    QWidget#movCaixaGlifo {{ background: transparent; }}
    /* As faixas que quebram linha (atalhos de valor e chips de descricao) sao
       QWidget crus, e a regra generica `QWidget {{ background: bg_marca }}` la
       do topo os pintaria de cor de fundo do app por cima do cartao. */
    QWidget#movCaixaFaixa {{ background: transparent; }}
    /* Mesmo motivo para o teclado compartilhado (`widgets/teclado_numerico.py`),
       que também é um QWidget cru servindo de moldura para a grade de teclas. */
    QWidget#tecladoNumerico {{ background: transparent; }}

    QFrame#movCaixaCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    QFrame#movCaixaBadge {{ border-radius: 12px; border: 1px solid transparent; }}
    QFrame#movCaixaBadge[operacao="sangria"] {{
      background: {t['mov_sangria_tinta']};
      border-color: {t['mov_sangria_glifo']};
    }}
    QFrame#movCaixaBadge[operacao="reforco"] {{
      background: {t['mov_reforco_tinta']};
      border-color: {t['mov_reforco_glifo']};
    }}
    QFrame#movCaixaBadge[operacao="despesa"] {{
      background: {t['mov_despesa_tinta']};
      border-color: {t['mov_despesa_glifo']};
    }}

    QLabel#movCaixaTitulo {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}
    QLabel#movCaixaSubtitulo {{
      color: {t['texto_fraco']};
      font-size: 12px;
      background: transparent;
    }}
    QLabel#movCaixaRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    /* O visor e REBAIXADO em relacao ao cartao (ver `visor_valor_bg`): o numero
       e leitura, nao controle, e um degrau para cima o faria parecer botao. */
    QFrame#movCaixaVisor {{
      background: {t['visor_valor_bg']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    /* O anel diz PARA ONDE o dedo no teclado esta indo: aceso, o dígito vai
       para o valor; apagado, ele esta sendo digitado na descricao. Sem esse
       sinal, o operador so descobre a diferenca depois de ler o que saiu. */
    QFrame#movCaixaVisor[foco="true"] {{ border: 1px solid {t['acento']}; }}
    QLabel#movCaixaVisorRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#movCaixaVisorValor {{
      color: {t['texto']};
      font-size: 32px;
      font-weight: 700;
      background: transparent;
    }}

    QPushButton#movCaixaAtalho {{
      padding: 5px 14px;
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      color: {t['texto']};
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton#movCaixaAtalho:hover {{ background: {t['botao_circular_hover']}; }}

    QLineEdit#movCaixaDescricao {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
      padding: 10px 12px;
      color: {t['texto']};
      font-size: 13px;
    }}
    QLineEdit#movCaixaDescricao:focus {{ border: 1px solid {t['acento']}; }}

    QPushButton#movCaixaChip {{
      padding: 5px 12px;
      background: transparent;
      border: 1px solid {t['borda']};
      border-radius: 12px;
      color: {t['texto_fraco']};
      font-size: 11px;
    }}
    QPushButton#movCaixaChip:hover {{
      background: {t['superficie_2']};
      color: {t['texto']};
    }}

    QLabel#movCaixaOperador {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    QPushButton#movCaixaConfirmar {{
      padding: 10px 20px;
      border: 1px solid transparent;
      border-radius: 18px;
      font-size: 12px;
      font-weight: 800;
    }}
    QPushButton#movCaixaConfirmar[operacao="sangria"] {{
      background: {t['mov_sangria_acao']};
      border-color: {t['mov_sangria_acao']};
      color: {t['mov_sangria_acao_texto']};
    }}
    QPushButton#movCaixaConfirmar[operacao="reforco"] {{
      background: {t['mov_reforco_acao']};
      border-color: {t['mov_reforco_acao']};
      color: {t['mov_reforco_acao_texto']};
    }}
    QPushButton#movCaixaConfirmar[operacao="despesa"] {{
      background: {t['mov_despesa_acao']};
      border-color: {t['mov_despesa_acao']};
      color: {t['mov_despesa_acao_texto']};
    }}
    /* Desligado enquanto o visor esta em R$ 0,00 -- e ai a cor da operacao sai
       de cena, senao um botao vivo e colorido continuaria convidando o clique
       que o service recusaria. As tres operacoes aparecem no seletor de
       proposito: `#id:disabled` sozinho empata em especificidade com
       `#id[operacao="..."]`, e empate em QSS e o tipo de regra que funciona
       ate alguem reordenar o arquivo. Com o atributo, ganha sempre. */
    QPushButton#movCaixaConfirmar[operacao="sangria"]:disabled,
    QPushButton#movCaixaConfirmar[operacao="reforco"]:disabled,
    QPushButton#movCaixaConfirmar[operacao="despesa"]:disabled {{
      background: {t['pilula_disabled_bg']};
      border-color: {t['pilula_disabled_bg']};
      color: {t['pilula_disabled_texto']};
    }}


    /* ---------- Modais de abertura e fechamento de turno
       (`widgets/cartao_de_turno.py` + os dois dialogos que herdam dele, §9.7)

       Quinto e sexto modais em cartao do app, e os dois primeiros a dividirem
       UMA familia de estilo: a moldura e literalmente a mesma classe base, e o
       que separa abrir de fechar entra por `[papel="..."]` nos DOIS lugares
       onde a cerimonia tem cor -- o badge do cabecalho e o botao que grava. O
       resto (visor, contagens, diferenca, campo, teclado, rodape) e identico
       nos dois e e declarado uma vez so. O X, o Cancelar, as teclas do numpad e
       o divisor nem aparecem aqui: ja estao nas familias que os quatro modais
       anteriores usam. */

    QDialog#turnoDialog {{ background: transparent; }}
    /* QWidget cru herdaria `QWidget {{ background: bg_marca }}` do topo e
       pintaria a cor de fundo do app por cima do cartao. */
    QWidget#turnoGlifo, QWidget#turnoColuna, QWidget#turnoFaixa {{ background: transparent; }}

    QFrame#turnoCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    QFrame#turnoBadge {{ border-radius: 12px; border: 1px solid transparent; }}
    QFrame#turnoBadge[papel="abertura"] {{
      background: {t['caixa_abertura_tinta']};
      border-color: {t['caixa_abertura_glifo']};
    }}
    QFrame#turnoBadge[papel="fechamento"] {{
      background: {t['caixa_fechamento_tinta']};
      border-color: {t['caixa_fechamento_glifo']};
    }}

    QLabel#turnoTitulo {{
      color: {t['texto']};
      font-size: 18px;
      font-weight: 800;
      background: transparent;
    }}
    QLabel#turnoSubtitulo {{
      color: {t['texto_fraco']};
      font-size: 12px;
      background: transparent;
    }}
    QLabel#turnoRotulo, QLabel#turnoDica {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    /* O visor e REBAIXADO em relacao ao cartao (ver `visor_valor_bg`): o numero
       e leitura, nao controle, e um degrau para cima o faria parecer botao. */
    QFrame#turnoVisor {{
      background: {t['visor_valor_bg']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#turnoVisorRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#turnoVisorValor {{
      color: {t['texto']};
      font-size: 28px;
      font-weight: 700;
      background: transparent;
    }}

    QPushButton#turnoAtalho {{
      padding: 5px 14px;
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      color: {t['texto']};
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton#turnoAtalho:hover {{ background: {t['botao_circular_hover']}; }}

    QFrame#turnoContexto {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#turnoContextoTitulo {{
      color: {t['texto']};
      font-size: 13px;
      font-weight: 700;
      background: transparent;
    }}
    QLabel#turnoContextoTexto {{
      color: {t['texto_fraco']};
      font-size: 11px;
      background: transparent;
    }}

    QLineEdit#turnoCampo {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
      padding: 10px 12px;
      color: {t['texto']};
      font-size: 13px;
    }}

    /* A linha de conferencia e um QFrame clicavel (ver `_LinhaDeContagem`):
       tocar nela e o que aponta o teclado para aquela contagem. */
    QFrame#turnoContagem {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#turnoContagemTitulo {{
      color: {t['texto']};
      font-size: 13px;
      font-weight: 700;
      background: transparent;
    }}
    QLabel#turnoContagemEsperado {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      background: transparent;
    }}
    QLabel#turnoContagemValor {{
      color: {t['texto']};
      font-size: 17px;
      font-weight: 700;
      background: transparent;
    }}

    QFrame#turnoDiferenca {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#turnoDiferencaValor {{
      color: {t['texto']};
      font-size: 17px;
      font-weight: 800;
      background: transparent;
    }}
    /* Falta e a noticia ruim, sobra e um dado a explicar e zero e a noticia boa
       -- tres leituras diferentes, e por isso tres cores e nao um numero com
       sinal. `ciano_metrica` na sobra porque sobra e DADO a conferir (de onde
       veio esse dinheiro?), nao erro. */
    QLabel#turnoDiferencaValor[tom="falta"] {{ color: {t['perigo']}; }}
    QLabel#turnoDiferencaValor[tom="exato"] {{ color: {t['sucesso']}; }}
    QLabel#turnoDiferencaValor[tom="sobra"] {{ color: {t['ciano_metrica']}; }}

    /* Botao fantasma de proposito: ele e o atalho que permite fechar o turno
       sem contar a gaveta. Serve, mas nao convida. */
    QPushButton#turnoPreencher {{
      padding: 7px 10px;
      background: transparent;
      border: 1px solid {t['borda']};
      border-radius: 8px;
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
    }}
    QPushButton#turnoPreencher:hover {{
      background: {t['superficie']};
      color: {t['texto']};
    }}

    /* O anel de foco, nos tres lugares para onde o teclado pode estar
       apontando. E o unico sinal que o operador tem de para onde vai o proximo
       digito. */
    QFrame#turnoVisor[ativa="true"],
    QFrame#turnoContagem[ativa="true"],
    QLineEdit#turnoCampo:focus {{ border: 1px solid {t['foco_teclado_anel']}; }}
    QFrame#turnoContagem[ativa="true"] {{ background: {t['foco_teclado_tinta']}; }}
    QFrame#turnoContagem:hover {{ border-color: {t['foco_teclado_anel']}; }}

    QPushButton#turnoConfirmar {{
      padding: 10px 22px;
      border: 1px solid transparent;
      border-radius: 18px;
      font-size: 12px;
      font-weight: 800;
    }}
    /* Abrir o caixa e a acao PRIMARIA da tela e usa o acento do app; fechar e a
       unica destrutiva e usa vermelho proprio. Nenhum dos dois pede token novo
       de "primario": o acento ja e esse papel em todo botao de confirmar do
       sistema. */
    QPushButton#turnoConfirmar[papel="abertura"] {{
      background: {t['acento']};
      border-color: {t['acento']};
      color: {t['acento_texto']};
    }}
    QPushButton#turnoConfirmar[papel="abertura"]:hover {{
      background: {t['acento_hover']};
      border-color: {t['acento_hover']};
    }}
    QPushButton#turnoConfirmar[papel="fechamento"] {{
      background: {t['caixa_fechamento_acao']};
      border-color: {t['caixa_fechamento_acao']};
      color: {t['caixa_fechamento_acao_texto']};
    }}
    QPushButton#turnoConfirmar[papel="fechamento"]:hover {{
      background: {t['caixa_fechamento_acao_hover']};
      border-color: {t['caixa_fechamento_acao_hover']};
    }}

    /* ---------- Tela de Impressoras ---------- */

    QFrame#impressorasPainel {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QFrame#impressorasIndicador {{ background: transparent; border-radius: 2px; }}
    QFrame#impressorasIndicador[ativo="true"] {{ background: {t['acento']}; }}

    QFrame#impressoraIconeBox {{
      background: {t['superficie_2']};
      border-radius: 8px;
    }}
    QLabel#impressoraIconeGlifo {{ color: {t['acento']}; font-size: 16px; background: transparent; }}
    QLabel#impressoraNomeLabel {{ color: {t['texto']}; font-weight: 600; font-size: 13px; background: transparent; }}
    QLabel#impressoraSubLabel {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#impressoraConexaoIcone {{ font-size: 13px; background: transparent; }}
    QLabel#impressoraConexaoTexto {{ color: {t['texto_fraco']}; font-size: 12px; background: transparent; }}

    QLabel[variante="badgePadrao"] {{
      color: {t['acento']};
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.5px;
      background: transparent;
    }}
    QLabel[variante="badgePadrao"][ativo="false"] {{ color: {t['texto_fraquissimo']}; font-weight: 600; }}

    QLabel[variante="badgeStatusImpressora"] {{
      border-radius: 999px;
      padding: 3px 10px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.5px;
    }}
    QLabel[variante="badgeStatusImpressora"][status="online"] {{
      background: rgba(34, 197, 94, 0.16);
      color: {t['sucesso']};
    }}
    QLabel[variante="badgeStatusImpressora"][status="offline"] {{
      background: rgba(239, 68, 68, 0.16);
      color: {t['perigo_hover']};
    }}

    QLabel#impressorasSelecaoLabel {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    QFrame#impressorasBarraAcoes {{
      background: {t['superficie_2']};
      border-top: 1px solid {t['borda']};
      border-bottom-left-radius: 16px;
      border-bottom-right-radius: 16px;
    }}

    QFrame#categoriaLinha {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
    }}
    QFrame#categoriaLinha:hover {{ border-color: {t['texto_fraco']}; }}
    QFrame#categoriaLinha[marcada="true"] {{ border-color: {t['acento']}; }}
    QLabel#categoriaMarcador {{
      border: 1.5px solid {t['borda']};
      border-radius: 8px;
      background: transparent;
    }}
    QLabel#categoriaMarcador[marcada="true"] {{
      border-color: {t['acento']};
      background: {t['acento']};
    }}
    QLabel#categoriaNomeLabel {{ color: {t['texto']}; font-size: 12px; font-weight: 600; background: transparent; }}

    /* Mesmo empréstimo do badge de despesa: o link de pendências queria ciano. */
    QLabel#impressorasPendentesLink {{ color: {t['ciano_metrica']}; font-size: 11px; font-weight: 700; background: transparent; }}

    /* ---------- Relatórios: Histórico Diário + Dashboard Mensal ---------- */

    QLabel#relatoriosBreadcrumb {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#relatoriosTitulo {{ color: {t['texto']}; font-size: 24px; font-weight: 800; background: transparent; }}
    QLabel#relatoriosSubtitulo {{ color: {t['texto_fraco']}; font-size: 12px; background: transparent; }}

    /* Segmentado Histórico Diário / Dashboard Mensal */
    QFrame#relatoriosSegmentado {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QPushButton[variante="segmento"] {{
      background: transparent;
      color: {t['texto_fraco']};
      border: none;
      border-radius: 11px;
      padding: 8px 16px;
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton[variante="segmento"]:hover {{ color: {t['texto']}; }}
    QPushButton[variante="segmento"][ativo="true"] {{
      background: {t['acento']};
      color: {t['acento_texto']};
    }}

    /* A barra de filtro é um QWidget próprio (`FiltroPeriodoOperador`), e sem
       esta regra ela herdaria o `QWidget {{ background: bg_marca }}` global e
       pintaria um retângulo por trás das pílulas — mesmo caso do
       `#secaoCancelamentos`. */
    QWidget#relatoriosFiltro {{ background: transparent; }}

    /* Pílula do filtro de mês (ícone + combo sem chrome, dentro de um frame com borda) */
    QFrame#relatoriosFiltroMes {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#relatoriosFiltroMesIcone {{ font-size: 12px; background: transparent; }}
    QComboBox#relatoriosComboMes {{
      background: transparent;
      border: none;
      padding: 0 4px;
      color: {t['texto']};
      font-size: 12px;
      font-weight: 700;
    }}
    QComboBox#relatoriosComboMes::drop-down {{ border: none; width: 16px; }}
    QComboBox#relatoriosComboMes QAbstractItemView {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      color: {t['texto']};
      selection-background-color: {t['acento']};
      selection-color: {t['acento_texto']};
    }}

    /* Cards de KPI (grid superior das duas visões) */
    QFrame#relatoriosKpiCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#relatoriosKpiRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#relatoriosKpiValor {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#relatoriosKpiValorPositivo {{ color: {t['sucesso']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#relatoriosKpiValorNegativo {{ color: {t['perigo_hover']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#relatoriosKpiSub {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}

    /* Painel de tabela / gráficos */
    QFrame#relatoriosPainel {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#relatoriosPainelTitulo {{
      color: {t['texto_fraco']};
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: transparent;
    }}
    QLabel#relatoriosPainelIndicador {{ color: {t['sucesso']}; font-size: 12px; font-weight: 700; background: transparent; }}

    QLabel#relatoriosRodapeRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#relatoriosRodapeValor {{ color: {t['texto']}; font-size: 16px; font-weight: 800; background: transparent; }}

    QPushButton[variante="pilula-impressora"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
      border-radius: 13px;
      padding: 4px 12px;
      font-size: 11px;
      font-weight: 700;
    }}
    QPushButton[variante="pilula-impressora"]:hover {{ background: {t['borda']}; }}

    /* Composição por forma de pagamento */
    QLabel#relatoriosFormaNome {{ color: {t['texto']}; font-size: 12px; font-weight: 600; background: transparent; }}
    QLabel#relatoriosFormaValor {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QLabel#relatoriosFormaPercentual {{ color: {t['texto_fraquissimo']}; font-size: 10px; font-weight: 600; background: transparent; }}
    QProgressBar#relatoriosBarraForma {{
      background: {t['borda']};
      border: none;
      border-radius: 2px;
      max-height: 4px;
      min-height: 4px;
    }}
    QProgressBar#relatoriosBarraForma::chunk {{ background: {t['acento']}; border-radius: 2px; }}

    /* Mix de vendas do mês (ranking) */
    QLabel#relatoriosRankIndice {{
      color: {t['texto_fraquissimo']};
      font-size: 13px;
      font-weight: 700;
      font-family: "Consolas", monospace;
      background: transparent;
      min-height: 18px;
    }}
    QLabel#relatoriosRankNome {{
      color: {t['texto']};
      font-size: 14px;
      font-weight: 600;
      background: transparent;
      min-height: 18px;
    }}
    QLabel#relatoriosRankQtd {{
      color: {t['texto_fraco']};
      font-size: 13px;
      background: transparent;
      min-height: 18px;
    }}
    QLabel#relatoriosRankValor {{
      color: {t['texto']};
      font-size: 14px;
      font-weight: 700;
      background: transparent;
      min-height: 18px;
    }}
    QProgressBar#relatoriosBarraRanking {{
      background: {t['ranking_barra_bg']};
      border: none;
      border-radius: 3px;
      max-height: 5px;
      min-height: 5px;
    }}
    QProgressBar#relatoriosBarraRanking::chunk {{ background: {t['ranking_barra_acento']}; border-radius: 3px; }}
    QScrollArea#relatoriosRolagemRanking {{ background: transparent; border: none; }}
    QScrollArea#relatoriosRolagemRanking > QWidget > QWidget {{ background: transparent; }}
    QScrollArea#relatoriosRolagemHistorico {{ background: transparent; border: none; }}
    QScrollArea#relatoriosRolagemHistorico > QWidget > QWidget {{ background: transparent; }}

    /* ---------- Tela de Funcionários (redesign "Concreto", §3.14) ---------- */

    /* Ciano exato do mockup (#22D3EE) para "Dar baixa" no painel de detalhe —
       diferente do variante="ciano" já existente (#0891b2, usado no Cardápio),
       de propósito: são dois tons de ciano coexistindo em telas diferentes. */
    QPushButton[variante="pilula-ciano"] {{
      background: {t['ciano_metrica']};
      color: {t['pilula_ciano2_texto']};
      border: none;
      border-radius: 18px;
      padding: 7px 20px;
      font-size: 13px;
      font-weight: 700;
    }}
    QPushButton[variante="pilula-ciano"]:hover {{ background: {t['pilula_ciano2_hover']}; }}
    QPushButton[variante="pilula-ciano"]:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    QFrame#funcionariosPainel {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}

    QFrame#funcionariosKpiCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QLabel#funcionariosKpiIcone {{ font-size: 18px; background: transparent; }}
    QLabel#funcionariosKpiRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#funcionariosKpiValor {{ color: {t['texto']}; font-size: 24px; font-weight: 800; background: transparent; }}

    QLineEdit#funcionariosBusca {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 10px;
      padding: 7px 12px;
      color: {t['texto']};
      font-size: 12px;
    }}

    QListWidget#funcionariosLista {{
      background: transparent;
      border: none;
    }}
    QListWidget#funcionariosLista::item {{
      border: none;
      padding: 0;
      margin-bottom: 6px;
    }}
    QListWidget#funcionariosLista::item:selected {{ background: transparent; }}

    QFrame#funcionariosLinha {{
      background: transparent;
      border: 1px solid transparent;
      border-left: 3px solid transparent;
      border-radius: 10px;
    }}
    QFrame#funcionariosLinha:hover {{ background: {t['superficie_2']}; }}
    QFrame#funcionariosLinha[selecionado="true"] {{
      background: {t['superficie_2']};
      border-left: 3px solid {t['acento']};
    }}

    QLabel#funcionariosAvatar {{
      background: {t['bg_terminal']};
      color: {t['texto']};
      border-radius: 19px;
      font-size: 13px;
      font-weight: 800;
    }}
    QLabel#funcionariosLinhaNome {{ color: {t['texto']}; font-size: 13px; font-weight: 700; background: transparent; }}
    QLabel#funcionariosLinhaCargo {{
      color: {t['texto_fraco']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: transparent;
    }}
    QLabel#funcionariosLinhaTurno {{
      color: {t['texto_fraco']};
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.3px;
      background: transparent;
    }}
    QLabel#funcionariosLinhaConsumoValor {{ color: {t['texto']}; font-size: 13px; font-weight: 700; background: transparent; }}
    QLabel#funcionariosLinhaConsumoRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: transparent;
    }}

    QLabel#funcionariosAvatarGrande {{
      background: {t['bg_terminal']};
      color: {t['texto']};
      border-radius: 32px;
      font-size: 22px;
      font-weight: 800;
    }}
    QLabel#funcionariosDetalheNome {{ color: {t['texto']}; font-size: 16px; font-weight: 800; background: transparent; }}
    QLabel#funcionariosDetalheCargo {{
      color: {t['texto_fraco']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}

    QFrame#funcionariosCardConsumo {{
      background: {t['superficie_2']};
      border-radius: 12px;
    }}
    QLabel#funcionariosCardConsumoRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#funcionariosCardConsumoValor {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#funcionariosCardConsumoNota {{ color: {t['texto_fraquissimo']}; font-size: 10px; background: transparent; }}

    QLabel#funcionariosMetaRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#funcionariosMetaValor {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    """
