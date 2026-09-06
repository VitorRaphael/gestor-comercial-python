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
    QFrame[variante="mesa"][ocupada="true"] QLabel#mesaCartaoTag {{ color: {t['mesa_ocupada_borda']}; }}
    QFrame[variante="mesa"][fechando="true"] QLabel#mesaCartaoTag {{ color: {t['mesa_fechando_borda']}; }}
    QLabel#mesaCartaoValor {{ color: {t['texto']}; font-size: 13px; font-weight: 800; background: transparent; }}
    QLabel#mesaCartaoNome {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}
    /* Ciano, não roxo/vermelho: "ocupada" é estado normal (mesa em
       atendimento), não um alerta — vermelho fica reservado pra ações
       destrutivas (perigo). */
    QFrame[variante="mesa"][ocupada="true"] {{
      background: {t['mesa_ocupada_bg']};
      border: 1px solid {t['mesa_ocupada_borda']};
      border-top: 3px solid {t['mesa_ocupada_borda']};
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
    QLabel[variante="badgeMovimento"][tipo="despesa"] {{ color: {t['mesa_ocupada_borda']}; border-color: {t['mesa_ocupada_borda']}; }}

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

    /* ---------- Modais ---------- */

    QDialog {{ background: {t['superficie']}; }}

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

    QLabel#impressorasPendentesLink {{ color: {t['mesa_ocupada_borda']}; font-size: 11px; font-weight: 700; background: transparent; }}

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
