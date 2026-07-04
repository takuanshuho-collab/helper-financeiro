"""
Interface gráfica (tkinter) do Helper Financeiro.

Organização em abas:
  1. Perfil          -> renda, despesas, reservas e dados pessoais
  2. Dívidas         -> cadastro/edição da lista de dívidas
  3. Contrato PDF    -> extrai dados de um contrato e pré-preenche uma dívida
  4. Análise         -> roda o diagnóstico e gera as saídas (.xlsx / .docx)
  5. Carta ao credor -> gera a proposta de negociação (.docx)

A janela é só a "casca": toda conta vem do pacote `core`, e todo arquivo
gerado vem do pacote `outputs`.
"""
from __future__ import annotations

import contextlib
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from agent.exibicao import (
    ROTULOS_EXTRACAO,
    campos_para_formulario,
    formatar_secao_ia,
    preparar_exibicao,
)
from contracts import SecaoIA
from core.calculos import taxa_anual_para_mensal
from core.diagnostico import resumo_diagnostico
from core.estrategias import comparar_estrategias, gerar_recomendacoes
from core.extrator_pdf import extrair_contrato, extrair_texto_pdf
from core.models import (
    TIPOS_DIVIDA,
    ComposicaoRenda,
    DespesasFixas,
    DespesasVariaveis,
    Divida,
    PerfilFinanceiro,
)
from core.utils import (
    formatar_brl,
    formatar_pct,
    parse_taxa,
    parse_valor,
    texto_numerico_valido,
)
from outputs.planilha import gerar_planilha
from outputs.proposta import gerar_proposta
from outputs.relatorio import gerar_relatorio

# Cores de status do painel de IA (T-304).
COR_OK = "#1E7B34"
COR_ALERTA = "#B45309"
COR_ERRO = "#C00000"
COR_NEUTRA = "#777777"

COR_PRIMARIA = "#1F4E79"
COR_FUNDO = "#F5F7FA"
TIPOS_PROPOSTA = {
    "Quitação à vista com desconto": "quitacao",
    "Portabilidade / contraproposta": "portabilidade",
    "Redução de taxa / renegociação": "reducao",
}


class HelperFinanceiroApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Helper Financeiro")
        self.geometry("940x720")
        self.minsize(880, 640)
        self.configure(bg=COR_FUNDO)

        self.dividas: list[Divida] = []
        # Última análise da IA aprovada (M3): entra no .docx quando existir.
        self.secao_ia: SecaoIA | None = None

        self._configurar_estilo()
        self._montar_cabecalho()

        # T-604: barra de status com dica contextual da aba ativa.
        self.barra_status = tk.Label(self, text="", anchor="w", bg="#E8EDF3",
                                     fg="#555555", font=("Segoe UI", 9),
                                     padx=12, pady=3)
        self.barra_status.pack(side="bottom", fill="x")

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._aba_perfil()
        self._aba_dividas()
        self._aba_contrato()
        self._aba_analise()
        self._aba_carta()
        self.abas.bind("<<NotebookTabChanged>>", self._ao_trocar_aba)
        self._ao_trocar_aba()

    _DICAS_ABAS = (
        "Preencha o orçamento por categoria — os totais e o resumo são "
        "calculados na hora.",
        "Cadastre cada dívida. Dica: Enter adiciona, duplo clique edita e "
        "Delete remove a selecionada.",
        "Extraia os dados de um contrato PDF e confira antes de usar.",
        "Rode o diagnóstico determinístico e, se quiser, a análise sênior "
        "assistida por IA.",
        "Gere a carta de proposta para o credor escolhido.",
    )

    def _ao_trocar_aba(self, _evento=None):
        indice = self.abas.index("current") if self.abas.tabs() else 0
        self.barra_status.config(text=self._DICAS_ABAS[indice])

    # ------------------------------------------------------------------ estilo
    def _configurar_estilo(self):
        s = ttk.Style(self)
        with contextlib.suppress(tk.TclError):  # tema "clam" pode não existir na plataforma
            s.theme_use("clam")
        s.configure("TNotebook", background=COR_FUNDO, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10))
        s.configure("TFrame", background=COR_FUNDO)
        s.configure("TLabel", background=COR_FUNDO, font=("Segoe UI", 10))
        s.configure("Titulo.TLabel", font=("Segoe UI", 11, "bold"),
                    foreground=COR_PRIMARIA)
        s.configure("TButton", font=("Segoe UI", 10), padding=6)
        s.configure("Primario.TButton", font=("Segoe UI", 10, "bold"))
        # T-606: tema consistente nas molduras e na lista de dívidas.
        s.configure("TLabelframe", background=COR_FUNDO)
        s.configure("TLabelframe.Label", background=COR_FUNDO,
                    foreground=COR_PRIMARIA, font=("Segoe UI", 10, "bold"))
        s.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        # T-602: campo numérico com texto não interpretável fica rosado.
        s.configure("Invalido.TEntry", fieldbackground="#F6D5D3")

    def _montar_cabecalho(self):
        barra = tk.Frame(self, bg=COR_PRIMARIA, height=54)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Label(barra, text="💰  Helper Financeiro", bg=COR_PRIMARIA, fg="white",
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=16)
        tk.Label(barra, text="Diagnóstico • Estratégias • Propostas",
                 bg=COR_PRIMARIA, fg="#CFE0F5",
                 font=("Segoe UI", 9)).pack(side="right", padx=16)

    # ------------------------------------------------------ util de formulário
    def _campo(self, parent, rotulo, linha, valor_inicial="",
               numerico=False, ao_enter=None):
        ttk.Label(parent, text=rotulo).grid(row=linha, column=0, sticky="w",
                                            padx=8, pady=6)
        var = tk.StringVar(value=valor_inicial)
        ent = ttk.Entry(parent, textvariable=var, width=24)
        ent.grid(row=linha, column=1, sticky="w", padx=8, pady=6)
        if numerico:
            self._vincular_validacao(ent, var)
        if ao_enter is not None:
            ent.bind("<Return>", lambda _e: ao_enter())
        return var

    # T-602 (REQ-F-009): texto não interpretável nunca vira zero em silêncio —
    # o campo é sinalizado em rosa enquanto o texto não fizer sentido.
    def _vincular_validacao(self, entry: ttk.Entry, var: tk.StringVar):
        def validar(*_):
            valido = texto_numerico_valido(var.get())
            entry.configure(style="TEntry" if valido else "Invalido.TEntry")
        var.trace_add("write", validar)

    # T-603: conteúdo rolável para a aba Perfil não cortar campos em janelas
    # menores (minsize 880x640). Roda do mouse funciona com o cursor em cima.
    def _frame_rolavel(self, externo: ttk.Frame) -> ttk.Frame:
        canvas = tk.Canvas(externo, bg=COR_FUNDO, highlightthickness=0)
        barra = ttk.Scrollbar(externo, orient="vertical",
                              command=canvas.yview)
        canvas.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        interno = ttk.Frame(canvas)
        janela = canvas.create_window((0, 0), window=interno, anchor="nw")
        interno.bind("<Configure>", lambda _e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
            janela, width=e.width))

        def rolar(evento):
            canvas.yview_scroll(-(evento.delta // 120), "units")
        canvas.bind("<Enter>",
                    lambda _e: canvas.bind_all("<MouseWheel>", rolar))
        canvas.bind("<Leave>",
                    lambda _e: canvas.unbind_all("<MouseWheel>"))
        return interno

    # -------------------------------------------------------------- aba perfil
    # M5 (ADR-0008, REQ-F-006/007/008): o perfil é um orçamento doméstico
    # completo — renda e despesas entram POR CATEGORIA, os totais e o resumo
    # são recalculados ao vivo, e o roll-up vem do core (com_orcamento).
    def _aba_perfil(self):
        externo = ttk.Frame(self.abas)
        self.abas.add(externo, text="  1. Perfil  ")
        frame = self._frame_rolavel(externo)  # T-603: conteúdo rolável
        frame.grid_columnconfigure(0, weight=1, uniform="perfil")
        frame.grid_columnconfigure(1, weight=1, uniform="perfil")

        ttk.Label(frame, text="Dados pessoais e orçamento mensal completo",
                  style="Titulo.TLabel").grid(row=0, column=0, columnspan=2,
                                              sticky="w", padx=8, pady=(10, 0))
        ttk.Label(frame,
                  text="Preencha cada categoria (média mensal): os totais e o "
                       "resumo são calculados na hora. Use vírgula para "
                       "centavos; campos vazios contam como zero.",
                  foreground="#777").grid(row=1, column=0, columnspan=2,
                                          sticky="w", padx=8, pady=(0, 6))

        ident = ttk.Frame(frame)
        ident.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8)
        ttk.Label(ident, text="Nome").pack(side="left")
        self.var_nome = tk.StringVar()
        ttk.Entry(ident, textvariable=self.var_nome,
                  width=32).pack(side="left", padx=(6, 18))
        ttk.Label(ident, text="CPF").pack(side="left")
        self.var_cpf = tk.StringVar()
        ttk.Entry(ident, textvariable=self.var_cpf,
                  width=18).pack(side="left", padx=6)

        self.vars_renda, self.lbl_total_renda = self._secao_orcamento(
            frame, "Renda líquida mensal (R$)", linha=3, coluna=0, campos=[
                ("salario_liquido", "Salário / benefício líquido"),
                ("renda_extra", "Renda extra ou autônoma"),
                ("outras_rendas", "Outras rendas (aluguel, pensão)"),
            ])
        self.vars_fixas, self.lbl_total_fixas = self._secao_orcamento(
            frame, "Despesas fixas (R$)", linha=3, coluna=1, rowspan=2,
            campos=[
                ("moradia", "Moradia (aluguel, condomínio)"),
                ("contas_casa", "Contas da casa (luz, água, internet)"),
                ("transporte", "Transporte"),
                ("saude", "Saúde (plano, remédios contínuos)"),
                ("educacao", "Educação"),
                ("assinaturas", "Assinaturas e academia"),
                ("outras_fixas", "Outras despesas fixas"),
            ])
        self.vars_variaveis, self.lbl_total_variaveis = self._secao_orcamento(
            frame, "Despesas variáveis (R$)", linha=4, coluna=0, campos=[
                ("mercado", "Mercado e alimentação"),
                ("lazer", "Lazer e delivery"),
                ("vestuario", "Vestuário e cuidados pessoais"),
                ("imprevistos", "Imprevistos"),
                ("outras_variaveis", "Outras despesas variáveis"),
            ])

        patrimonio = ttk.LabelFrame(frame, text="Reserva e FGTS (R$)")
        patrimonio.grid(row=5, column=0, columnspan=2, sticky="ew",
                        padx=8, pady=4)
        ttk.Label(patrimonio,
                  text="Reserva de emergência").grid(row=0, column=0,
                                                     sticky="w", padx=8,
                                                     pady=2)
        self.var_reserva = self._var_orcamento()
        ent_reserva = ttk.Entry(patrimonio, textvariable=self.var_reserva,
                                width=14, justify="right")
        ent_reserva.grid(row=0, column=1, padx=8, pady=2)
        self._vincular_validacao(ent_reserva, self.var_reserva)
        ttk.Label(patrimonio, text="Saldo de FGTS").grid(row=0, column=2,
                                                         sticky="w",
                                                         padx=(24, 8), pady=2)
        self.var_fgts = self._var_orcamento()
        ent_fgts = ttk.Entry(patrimonio, textvariable=self.var_fgts,
                             width=14, justify="right")
        ent_fgts.grid(row=0, column=3, padx=8, pady=2)
        self._vincular_validacao(ent_fgts, self.var_fgts)
        self.lbl_reserva = tk.Label(patrimonio, text="", bg=COR_FUNDO,
                                    fg=COR_NEUTRA, font=("Segoe UI", 9))
        self.lbl_reserva.grid(row=0, column=4, sticky="w", padx=(24, 8),
                              pady=2)

        resumo = ttk.LabelFrame(frame, text="Resumo ao vivo")
        resumo.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8,
                    pady=(4, 8))
        self.lbl_fluxo = tk.Label(resumo, text="", bg=COR_FUNDO,
                                  font=("Segoe UI", 10, "bold"))
        self.lbl_fluxo.pack(side="left", padx=12, pady=6)
        self.lbl_comprometimento = tk.Label(resumo, text="", bg=COR_FUNDO,
                                            font=("Segoe UI", 10))
        self.lbl_comprometimento.pack(side="left", padx=12, pady=6)

        self._perfil_pronto = True
        self._atualizar_resumo_perfil()

    def _var_orcamento(self) -> tk.StringVar:
        """StringVar que dispara o recálculo do resumo a cada digitação."""
        var = tk.StringVar()
        var.trace_add("write", lambda *_: self._atualizar_resumo_perfil())
        return var

    def _secao_orcamento(self, parent, titulo, linha, coluna, campos,
                         rowspan=1):
        """LabelFrame com um campo por categoria e um rótulo de total vivo."""
        lf = ttk.LabelFrame(parent, text=titulo)
        lf.grid(row=linha, column=coluna, rowspan=rowspan, sticky="nsew",
                padx=8, pady=4)
        lf.grid_columnconfigure(0, weight=1)
        vars_: dict[str, tk.StringVar] = {}
        for i, (chave, rotulo) in enumerate(campos):
            ttk.Label(lf, text=rotulo).grid(row=i, column=0, sticky="w",
                                            padx=8, pady=2)
            var = self._var_orcamento()
            ent = ttk.Entry(lf, textvariable=var, width=12, justify="right")
            ent.grid(row=i, column=1, sticky="e", padx=8, pady=2)
            self._vincular_validacao(ent, var)  # T-602
            vars_[chave] = var
        total = tk.Label(lf, text="Total: R$ 0,00", bg=COR_FUNDO,
                         fg=COR_PRIMARIA, font=("Segoe UI", 9, "bold"))
        total.grid(row=len(campos), column=0, columnspan=2, sticky="e",
                   padx=8, pady=(4, 6))
        return vars_, total

    def _atualizar_resumo_perfil(self):
        """Recalcula totais, cobertura da reserva e fluxo de caixa ao vivo."""
        if not getattr(self, "_perfil_pronto", False):
            return  # widgets do resumo ainda em construção
        perfil = self._ler_perfil()
        self.lbl_total_renda.config(
            text=f"Total: {formatar_brl(perfil.renda_liquida)}")
        self.lbl_total_fixas.config(
            text=f"Total: {formatar_brl(perfil.despesas_fixas)}")
        self.lbl_total_variaveis.config(
            text=f"Total: {formatar_brl(perfil.despesas_variaveis)}")

        meses = perfil.meses_reserva
        if meses is None:
            self.lbl_reserva.config(
                text="Cobertura: informe as despesas", fg=COR_NEUTRA)
        else:
            cor = (COR_OK if meses >= 3
                   else COR_ALERTA if meses >= 1 else COR_ERRO)
            txt_meses = f"{meses:.1f}".replace(".", ",")
            self.lbl_reserva.config(
                text=f"Cobertura: {txt_meses} mês(es) de despesas", fg=cor)

        fluxo = perfil.fluxo_caixa
        cor_fluxo = (COR_OK if fluxo > 0
                     else COR_ALERTA if fluxo == 0 else COR_ERRO)
        self.lbl_fluxo.config(
            text=f"Fluxo de caixa livre: {formatar_brl(fluxo)}",
            fg=cor_fluxo)

        if perfil.renda_liquida <= 0:
            self.lbl_comprometimento.config(
                text="Comprometimento com dívidas: — (informe a renda)",
                fg=COR_NEUTRA)
        else:
            comp = perfil.comprometimento_renda
            cor_comp = (COR_OK if comp <= 0.30
                        else COR_ALERTA if comp <= 0.50 else COR_ERRO)
            self.lbl_comprometimento.config(
                text=f"Comprometimento com dívidas: {formatar_pct(comp)}",
                fg=cor_comp)

    def _ler_perfil(self) -> PerfilFinanceiro:
        return PerfilFinanceiro.com_orcamento(
            renda=ComposicaoRenda(
                **{k: parse_valor(v.get()) for k, v in
                   self.vars_renda.items()}),
            fixas=DespesasFixas(
                **{k: parse_valor(v.get()) for k, v in
                   self.vars_fixas.items()}),
            variaveis=DespesasVariaveis(
                **{k: parse_valor(v.get()) for k, v in
                   self.vars_variaveis.items()}),
            reserva_emergencia=parse_valor(self.var_reserva.get()),
            saldo_fgts=parse_valor(self.var_fgts.get()),
            dividas=self.dividas,
        )

    # ------------------------------------------------------------- aba dívidas
    def _aba_dividas(self):
        frame = ttk.Frame(self.abas)
        self.abas.add(frame, text="  2. Dívidas  ")

        # Lista (Treeview)
        colunas = ("credor", "tipo", "saldo", "taxa", "parcela", "restantes")
        self.tree = ttk.Treeview(frame, columns=colunas, show="headings",
                                 height=8)
        titulos = {"credor": "Credor", "tipo": "Tipo", "saldo": "Saldo",
                   "taxa": "Taxa a.m.", "parcela": "Parcela",
                   "restantes": "Parc. rest."}
        larguras = {"credor": 160, "tipo": 200, "saldo": 100, "taxa": 80,
                    "parcela": 100, "restantes": 80}
        for c in colunas:
            self.tree.heading(c, text=titulos[c])
            self.tree.column(c, width=larguras[c], anchor="center")
        # T-606: linhas zebradas para leitura mais fácil da lista.
        self.tree.tag_configure("par", background="#FFFFFF")
        self.tree.tag_configure("impar", background="#EEF3F9")
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew",
                       padx=8, pady=8)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(3, weight=1)
        # T-605: duplo clique edita; Delete remove a dívida selecionada.
        self.tree.bind("<Double-1>", lambda _e: self._editar_divida())
        self.tree.bind("<Delete>", lambda _e: self._remover_divida())

        acoes = ttk.Frame(frame)
        acoes.grid(row=1, column=0, columnspan=4, sticky="w", padx=8,
                   pady=(0, 8))
        ttk.Button(acoes, text="✏ Editar selecionada",
                   command=self._editar_divida).pack(side="left")
        ttk.Button(acoes, text="🗑 Remover selecionada",
                   command=self._remover_divida).pack(side="left", padx=8)

        # Formulário de cadastro (Enter em qualquer campo adiciona).
        form = ttk.LabelFrame(frame, text="Adicionar / editar dívida")
        form.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=8)

        add = self._adicionar_divida
        self.d_credor = self._campo(form, "Credor", 0, ao_enter=add)
        ttk.Label(form, text="Tipo").grid(row=1, column=0, sticky="w",
                                          padx=8, pady=6)
        self.d_tipo = tk.StringVar(value=TIPOS_DIVIDA[0])
        ttk.Combobox(form, textvariable=self.d_tipo, values=TIPOS_DIVIDA,
                     width=34, state="readonly").grid(row=1, column=1,
                                                      sticky="w", padx=8,
                                                      pady=6)
        self.d_saldo = self._campo(form, "Saldo devedor (R$)", 2,
                                   numerico=True, ao_enter=add)
        self.d_taxa = self._campo(form, "Taxa mensal (%)", 3,
                                  numerico=True, ao_enter=add)
        self.d_parcela = self._campo(form, "Parcela (R$)", 4,
                                     numerico=True, ao_enter=add)
        self.d_restantes = self._campo(form, "Parcelas restantes", 5,
                                       numerico=True, ao_enter=add)

        ttk.Button(form, text="➕ Adicionar dívida", style="Primario.TButton",
                   command=add).grid(row=6, column=0, columnspan=2, pady=10)

    def _adicionar_divida(self, prefill: dict | None = None):
        credor = self.d_credor.get().strip()
        if not credor:
            messagebox.showwarning("Campo obrigatório",
                                   "Informe o nome do credor.")
            return
        divida = Divida(
            credor=credor,
            tipo=self.d_tipo.get(),
            saldo_devedor=parse_valor(self.d_saldo.get()),
            taxa_mensal=parse_taxa(self.d_taxa.get()),
            parcela=parse_valor(self.d_parcela.get()),
            parcelas_restantes=int(parse_valor(self.d_restantes.get())),
        )
        self.dividas.append(divida)
        self._atualizar_tree()
        self._atualizar_combo_dividas()
        # Limpa o formulário
        for var in (self.d_credor, self.d_saldo, self.d_taxa,
                    self.d_parcela, self.d_restantes):
            var.set("")

    def _remover_divida(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        del self.dividas[idx]
        self._atualizar_tree()
        self._atualizar_combo_dividas()

    def _editar_divida(self):
        """T-605: joga a dívida selecionada no formulário para edição.

        Remove da lista e devolve os campos ao formulário; o usuário revisa e
        clica em Adicionar para gravar de volta (fluxo simples, sem modo de
        edição separado).
        """
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        d = self.dividas[idx]
        self.d_credor.set(d.credor)
        self.d_tipo.set(d.tipo if d.tipo in TIPOS_DIVIDA else "Outro")
        self.d_saldo.set(f"{d.saldo_devedor:.2f}".replace(".", ","))
        self.d_taxa.set(f"{d.taxa_mensal * 100:.2f}".replace(".", ","))
        self.d_parcela.set(f"{d.parcela:.2f}".replace(".", ","))
        self.d_restantes.set(str(d.parcelas_restantes))
        del self.dividas[idx]
        self._atualizar_tree()
        self._atualizar_combo_dividas()
        self._status_transitorio("Dívida carregada no formulário — ajuste e "
                                 "clique em Adicionar para gravar.")

    def _atualizar_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.dividas):
            tag = "par" if i % 2 == 0 else "impar"
            self.tree.insert("", "end", tags=(tag,), values=(
                d.credor, d.tipo, formatar_brl(d.saldo_devedor),
                formatar_pct(d.taxa_mensal), formatar_brl(d.parcela),
                d.parcelas_restantes))
        # T-604: contador de dívidas no rótulo da aba.
        rotulo = (f"  2. Dívidas ({len(self.dividas)})  " if self.dividas
                  else "  2. Dívidas  ")
        with contextlib.suppress(tk.TclError):
            self.abas.tab(1, text=rotulo)
        # Parcelas mudam o fluxo de caixa e o comprometimento do resumo.
        self._atualizar_resumo_perfil()

    def _status_transitorio(self, texto: str, ms: int = 6000):
        """Mostra uma mensagem na barra de status e depois volta à dica da aba."""
        self.barra_status.config(text=texto)
        self.after(ms, self._ao_trocar_aba)

    # ------------------------------------------------------------ aba contrato
    def _aba_contrato(self):
        frame = ttk.Frame(self.abas)
        self.abas.add(frame, text="  3. Contrato PDF  ")

        ttk.Label(frame, text="Extração automática de contrato (PDF)",
                  style="Titulo.TLabel").pack(anchor="w", padx=8, pady=(12, 4))
        ttk.Label(frame, text="Selecione o PDF do contrato. Os dados extraídos "
                              "serão jogados no formulário da aba Dívidas para "
                              "você conferir antes de adicionar.",
                  foreground="#555", wraplength=800).pack(anchor="w", padx=8)

        botoes = ttk.Frame(frame)
        botoes.pack(anchor="w", fill="x", padx=8, pady=12)
        ttk.Button(botoes, text="📄 Selecionar contrato PDF...",
                   style="Primario.TButton",
                   command=self._extrair_pdf).pack(side="left")
        # T-305: extração Code-First (M2.5) — o modelo extrai com citação, o
        # código verifica, e VOCÊ confirma numa janela antes de qualquer uso.
        self.btn_extrair_ia = ttk.Button(
            botoes, text="🧠 Extrair com IA local (confira antes de usar)",
            command=self._extrair_pdf_ia)
        self.btn_extrair_ia.pack(side="left", padx=(12, 0))
        self.barra_extracao = ttk.Progressbar(botoes, mode="indeterminate",
                                              length=130)
        self.barra_extracao.pack(side="left", padx=10)
        self.lbl_extracao = tk.Label(botoes, text="", bg=COR_FUNDO, fg=COR_NEUTRA,
                                     font=("Segoe UI", 9), anchor="w")
        self.lbl_extracao.pack(side="left", fill="x", expand=True)

        self.txt_extracao = scrolledtext.ScrolledText(frame, height=16, width=100,
                                                       font=("Consolas", 9))
        self.txt_extracao.pack(fill="both", expand=True, padx=8, pady=8)

    def _extrair_pdf(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o contrato em PDF",
            filetypes=[("PDF", "*.pdf")])
        if not caminho:
            return
        try:
            dados = extrair_contrato(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro ao ler PDF",
                                 f"Não foi possível ler o PDF:\n{e}")
            return

        self.txt_extracao.delete("1.0", "end")
        self.txt_extracao.insert("end",
                                 f"Arquivo: {os.path.basename(caminho)}\n\n")
        if dados.get("aviso"):
            self.txt_extracao.insert("end", "⚠ " + dados["aviso"] + "\n\n")

        rotulos = {
            "tipo": "Tipo", "valor_financiado": "Valor financiado",
            "valor_liberado": "Valor liberado", "taxa_mensal": "Taxa mensal",
            "taxa_anual": "Taxa anual", "cet_anual": "CET anual",
            "num_parcelas": "Nº de parcelas", "valor_parcela": "Valor da parcela",
        }
        self.txt_extracao.insert("end", "Campos encontrados:\n")
        for chave, rot in rotulos.items():
            v = dados.get(chave)
            if v is None:
                mostrado = "(não encontrado)"
            elif chave in ("taxa_mensal", "taxa_anual", "cet_anual"):
                mostrado = formatar_pct(v)
            elif chave in ("valor_financiado", "valor_liberado", "valor_parcela"):
                mostrado = formatar_brl(v)
            else:
                mostrado = str(v)
            self.txt_extracao.insert("end", f"  • {rot}: {mostrado}\n")

        # Pré-preenche o formulário de dívida
        taxa_mensal = dados.get("taxa_mensal")
        if taxa_mensal is None and dados.get("taxa_anual"):
            taxa_mensal = taxa_anual_para_mensal(dados["taxa_anual"])

        self.d_tipo.set(dados.get("tipo") or TIPOS_DIVIDA[0])
        # Saldo devedor inicial: melhor estimativa = valor financiado (o usuário ajusta)
        if dados.get("valor_financiado"):
            self.d_saldo.set(f"{dados['valor_financiado']:.2f}".replace(".", ","))
        if taxa_mensal is not None:
            self.d_taxa.set(f"{taxa_mensal*100:.2f}".replace(".", ","))
        if dados.get("valor_parcela"):
            self.d_parcela.set(f"{dados['valor_parcela']:.2f}".replace(".", ","))
        if dados.get("num_parcelas"):
            self.d_restantes.set(str(dados["num_parcelas"]))

        self.txt_extracao.insert("end",
            "\n➡ Formulário da aba 'Dívidas' pré-preenchido. "
            "Ajuste o SALDO DEVEDOR atual e as PARCELAS RESTANTES "
            "(o contrato traz os valores originais) e clique em Adicionar.")
        messagebox.showinfo("Extração concluída",
                            "Dados extraídos. Vá à aba 'Dívidas', confira o "
                            "saldo devedor atual e adicione.")

    # ---------------------------------------------- extração por IA (T-305)
    def _status_extracao(self, texto: str, cor: str):
        self.lbl_extracao.config(text=texto, fg=cor)

    def _extrair_pdf_ia(self):
        """Extração Code-First (M2.5): o modelo extrai com citação obrigatória,
        o código verifica (quote-check + cruzada Price), o grafo PAUSA e você
        confirma numa janela antes de qualquer uso (interrupt → resume)."""
        caminho = filedialog.askopenfilename(
            title="Selecione o contrato ou extrato em PDF",
            filetypes=[("PDF", "*.pdf")])
        if not caminho:
            return
        self.btn_extrair_ia.config(state="disabled")
        self.barra_extracao.start(12)
        self._status_extracao("Lendo o documento e consultando o modelo local... "
                              "isso pode levar alguns minutos.", "#555555")
        fila: queue.Queue = queue.Queue()

        def trabalho():
            try:
                # Import preguiçoso: langgraph/llama-index só carregam aqui.
                from agent.config import carregar_config
                from agent.extracao import iniciar_extracao
                from agent.ingestao import LIMITE_DIRETO_CHARS, preparar_contexto
                texto = extrair_texto_pdf(caminho)
                if len(texto.strip()) < 40:
                    raise RuntimeError(
                        "O PDF parece não conter texto selecionável "
                        "(provavelmente é digitalização). Preencha manualmente.")
                cfg = carregar_config()
                try:
                    contexto = preparar_contexto(texto, cfg)
                except Exception:  # noqa: BLE001 — sem embeddings ⇒ melhor esforço
                    contexto = texto[:LIMITE_DIRETO_CHARS]
                fila.put(("ok", iniciar_extracao(contexto, cfg)))
            except Exception as e:  # noqa: BLE001 — erro vira status na GUI
                fila.put(("erro", e))

        threading.Thread(target=trabalho, daemon=True).start()
        self._aguardar_extracao(fila)

    def _aguardar_extracao(self, fila: queue.Queue):
        try:
            status, carga = fila.get_nowait()
        except queue.Empty:
            self.after(200, lambda: self._aguardar_extracao(fila))
            return
        self.barra_extracao.stop()
        self.btn_extrair_ia.config(state="normal")
        if status == "erro":
            self._status_extracao(f"Erro na extração por IA: {carga}", COR_ERRO)
            return

        thread_id, estado = carga
        if "__interrupt__" in estado:   # o grafo pausou para a confirmação humana
            payload = estado["__interrupt__"][0].value
            self._status_extracao("Aguardando a sua confirmação dos campos...",
                                  "#555555")
            self._dialogo_confirmacao(thread_id, payload)
        else:                            # P8 na entrada: caiu no nó `falhar`
            motivos = ", ".join(estado.get("motivos") or []) or "desconhecido"
            self._status_extracao(
                f"⚠ Extração por IA indisponível ({motivos}). Use o botão "
                "'Selecionar contrato PDF' (extração clássica).", COR_ALERTA)

    def _dialogo_confirmacao(self, thread_id: str, payload: dict):
        """Tela "confira antes de usar": campos + citação de origem + alertas
        do verificador. Confirmar retoma o checkpoint do grafo (ADR-0006)."""
        form = campos_para_formulario(payload["campos"])
        if not form:
            self._status_extracao(
                "⚠ O modelo não encontrou nenhum campo com fonte verificável "
                "no documento. Use a extração clássica ou preencha manualmente.",
                COR_ALERTA)
            return

        dlg = tk.Toplevel(self)
        dlg.title("Confirme os campos extraídos — conteúdo assistido por IA")
        dlg.configure(bg=COR_FUNDO)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="O modelo extraiu os campos abaixo, cada um com a "
                           "citação do documento de onde saiu.\nConfira e ajuste "
                           "antes de usar — nada entra sem a sua confirmação.",
                 bg=COR_FUNDO, justify="left",
                 font=("Segoe UI", 10)).grid(row=0, column=0, columnspan=2,
                                             sticky="w", padx=12, pady=(12, 6))
        linha = 1
        if payload.get("descartados"):
            tk.Label(dlg, text="Descartados por falta de fonte verificável: "
                               + ", ".join(payload["descartados"]),
                     bg=COR_FUNDO, fg=COR_ALERTA, justify="left",
                     font=("Segoe UI", 9)).grid(row=linha, column=0, columnspan=2,
                                                sticky="w", padx=12)
            linha += 1
        if payload.get("inconsistencias"):
            tk.Label(dlg, text="⚠ A parcela não bate com o recálculo Price "
                               "(saldo, taxa, prazo) — confira os valores.",
                     bg=COR_FUNDO, fg=COR_ALERTA, justify="left",
                     font=("Segoe UI", 9)).grid(row=linha, column=0, columnspan=2,
                                                sticky="w", padx=12)
            linha += 1

        entradas: dict[str, tk.StringVar] = {}
        for chave, rotulo in ROTULOS_EXTRACAO.items():
            if chave not in form:
                continue
            campo = form[chave]
            tk.Label(dlg, text=rotulo, bg=COR_FUNDO,
                     font=("Segoe UI", 10, "bold")).grid(row=linha, column=0,
                                                         sticky="nw", padx=12,
                                                         pady=(8, 0))
            var = tk.StringVar(value=campo["valor"])
            entradas[chave] = var
            ttk.Entry(dlg, textvariable=var, width=36).grid(row=linha, column=1,
                                                            sticky="w", padx=8,
                                                            pady=(8, 0))
            linha += 1
            tk.Label(dlg, text=f'fonte: "{campo["fonte"]}"  ·  confiança: '
                               f'{campo["confianca"]}',
                     bg=COR_FUNDO, fg=COR_NEUTRA, wraplength=520, justify="left",
                     font=("Segoe UI", 8)).grid(row=linha, column=1, sticky="w",
                                                padx=8)
            linha += 1

        def cancelar():
            dlg.destroy()
            self._status_extracao("Extração cancelada — nada foi usado.",
                                  COR_NEUTRA)

        botoes = ttk.Frame(dlg)
        botoes.grid(row=linha, column=0, columnspan=2, pady=14)
        ttk.Button(botoes, text="✔ Confirmar e preencher a aba Dívidas",
                   style="Primario.TButton",
                   command=lambda: self._confirmar_extracao_ia(
                       dlg, thread_id, entradas)).pack(side="left", padx=6)
        ttk.Button(botoes, text="Cancelar",
                   command=cancelar).pack(side="left", padx=6)

    def _confirmar_extracao_ia(self, dlg: tk.Toplevel, thread_id: str,
                               entradas: dict[str, tk.StringVar]):
        confirmacao = {chave: var.get().strip()
                       for chave, var in entradas.items() if var.get().strip()}
        # Retoma o checkpoint pausado (Command(resume=...)); o registro no
        # grafo não pode travar o fluxo do usuário.
        with contextlib.suppress(Exception):
            from agent.extracao import confirmar_extracao
            confirmar_extracao(thread_id, confirmacao)

        if v := confirmacao.get("credor"):
            self.d_credor.set(v)
        if v := confirmacao.get("tipo"):
            self.d_tipo.set(v if v in TIPOS_DIVIDA else "Outro")
        for chave, var_form in (("saldo", self.d_saldo), ("taxa", self.d_taxa),
                                ("parcela", self.d_parcela),
                                ("restantes", self.d_restantes)):
            if v := confirmacao.get(chave):
                var_form.set(v)
        dlg.destroy()
        self._status_extracao("✔ Campos confirmados e enviados à aba Dívidas — "
                              "ajuste o saldo atual e as parcelas restantes.",
                              COR_OK)
        self.txt_extracao.delete("1.0", "end")
        self.txt_extracao.insert(
            "end", "Extração assistida por IA confirmada.\n\nCampos usados:\n"
            + "\n".join(f"  • {ROTULOS_EXTRACAO[c]}: {v}"
                        for c, v in confirmacao.items())
            + "\n\n➡ Formulário da aba 'Dívidas' pré-preenchido. Ajuste o "
              "SALDO DEVEDOR atual e as PARCELAS RESTANTES (o contrato traz "
              "os valores originais) e clique em Adicionar.")
        self.abas.select(1)  # leva o usuário direto à aba Dívidas

    # ------------------------------------------------------------- aba análise
    def _aba_analise(self):
        frame = ttk.Frame(self.abas)
        self.abas.add(frame, text="  4. Análise  ")

        params = ttk.Frame(frame)
        params.pack(fill="x", padx=8, pady=10)
        ttk.Label(params, text="Pagamento extra por mês (R$):").grid(
            row=0, column=0, sticky="w", padx=4)
        self.var_extra = tk.StringVar(value="0")
        ent_extra = ttk.Entry(params, textvariable=self.var_extra, width=12)
        ent_extra.grid(row=0, column=1, padx=4)
        self._vincular_validacao(ent_extra, self.var_extra)
        ttk.Label(params, text="Taxa-alvo p/ portabilidade (% a.m.):").grid(
            row=0, column=2, sticky="w", padx=(20, 4))
        self.var_alvo = tk.StringVar(value="1,8")
        ent_alvo = ttk.Entry(params, textvariable=self.var_alvo, width=8)
        ent_alvo.grid(row=0, column=3, padx=4)
        self._vincular_validacao(ent_alvo, self.var_alvo)
        ttk.Button(params, text="🔍 Analisar", style="Primario.TButton",
                   command=self._analisar).grid(row=0, column=4, padx=16)

        self.txt_resultado = scrolledtext.ScrolledText(
            frame, height=9, font=("Consolas", 10))
        self.txt_resultado.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        # --- Painel da análise sênior (T-302/T-303/T-304) -------------------
        painel = ttk.LabelFrame(frame,
                                text="Análise sênior — conteúdo assistido por IA")
        painel.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        linha_ia = ttk.Frame(painel)
        linha_ia.pack(fill="x", padx=6, pady=(6, 4))
        self.btn_ia = ttk.Button(linha_ia, text="🧠 Gerar análise sênior",
                                 style="Primario.TButton",
                                 command=self._gerar_analise_ia)
        self.btn_ia.pack(side="left")
        self.barra_ia = ttk.Progressbar(linha_ia, mode="indeterminate", length=150)
        self.barra_ia.pack(side="left", padx=10)
        self.lbl_ia = tk.Label(linha_ia, text="IA ainda não executada nesta sessão.",
                               bg=COR_FUNDO, fg=COR_NEUTRA, font=("Segoe UI", 9),
                               anchor="w", justify="left")
        self.lbl_ia.pack(side="left", fill="x", expand=True, padx=6)

        self.txt_ia = scrolledtext.ScrolledText(painel, height=9,
                                                font=("Consolas", 9))
        self.txt_ia.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        botoes = ttk.Frame(frame)
        botoes.pack(fill="x", padx=8, pady=(0, 10))
        ttk.Button(botoes, text="📊 Gerar planilha (.xlsx)",
                   command=self._gerar_xlsx).pack(side="left", padx=4)
        ttk.Button(botoes, text="📄 Gerar relatório (.docx)",
                   command=self._gerar_docx).pack(side="left", padx=4)
        ttk.Label(botoes, text="O relatório inclui a última análise da IA, "
                               "quando houver.",
                  foreground="#777").pack(side="left", padx=12)

    def _validar_dados(self) -> PerfilFinanceiro | None:
        perfil = self._ler_perfil()
        if perfil.renda_liquida <= 0:
            messagebox.showwarning("Dados incompletos",
                                   "Informe a renda líquida na aba Perfil.")
            return None
        if not perfil.dividas:
            messagebox.showwarning("Sem dívidas",
                                   "Cadastre ao menos uma dívida na aba Dívidas.")
            return None
        return perfil

    def _analisar(self):
        perfil = self._validar_dados()
        if not perfil:
            return
        extra = parse_valor(self.var_extra.get())
        diag = resumo_diagnostico(perfil)
        comp = comparar_estrategias(perfil, extra)

        L = []
        L.append("=" * 60)
        L.append("  DIAGNÓSTICO")
        L.append("=" * 60)
        L.append(f"Classificação: {diag['classificacao']} — "
                 f"{diag['classificacao_explicacao']}")
        L.append(f"Comprometimento de renda: "
                 f"{formatar_pct(diag['comprometimento_renda'])}")
        L.append(f"Fluxo de caixa mensal:    {formatar_brl(diag['fluxo_caixa'])}")
        L.append(f"Saldo devedor total:      "
                 f"{formatar_brl(diag['saldo_devedor_total'])}")
        L.append(f"Juros futuros embutidos:  "
                 f"{formatar_brl(diag['juros_totais_futuros'])}")
        L.append("")
        L.append("-" * 60)
        L.append("  ESTRATÉGIAS (com extra de "
                 f"{formatar_brl(extra)}/mês)")
        L.append("-" * 60)
        for nome, chave in (("Avalanche", "avalanche"),
                            ("Bola de neve", "bola_de_neve")):
            r = comp[chave]
            if r["quitavel"]:
                L.append(f"{nome:14s}: quita em {r['meses']} meses | "
                         f"juros {formatar_brl(r['juros_pagos'])}")
            else:
                L.append(f"{nome:14s}: não quita com esse valor extra")
        L.append("")
        L.append("-" * 60)
        L.append("  RECOMENDAÇÕES")
        L.append("-" * 60)
        for i, rec in enumerate(gerar_recomendacoes(perfil, diag), 1):
            L.append(f"{i}. {rec}")

        self.txt_resultado.delete("1.0", "end")
        self.txt_resultado.insert("end", "\n".join(L))
        self.abas.select(self.abas.index("current"))

    # ----------------------------------------------- análise sênior (IA, M3)
    def _status_ia(self, texto: str, cor: str):
        self.lbl_ia.config(text=texto, fg=cor)

    def _gerar_analise_ia(self):
        """T-303: roda o CONSELHEIRO numa thread — a janela não congela.

        tkinter não é thread-safe: a thread só deposita o resultado numa fila;
        quem toca nos widgets é o laço `_aguardar_ia` (via `after`).
        """
        perfil = self._validar_dados()
        if not perfil:
            return
        extra = parse_valor(self.var_extra.get())
        self.btn_ia.config(state="disabled")
        self.barra_ia.start(12)
        self._status_ia("Consultando o modelo local... isso pode levar alguns "
                        "minutos (o programa continua utilizável).", "#555555")
        fila: queue.Queue = queue.Queue()

        def trabalho():
            try:
                # Import preguiçoso: langgraph só carrega no primeiro uso.
                from agent.agente import analisar
                from guardrails.pii import anonimizar_credores
                resultado = analisar(perfil, extra_mensal=extra)
                # O mapa é reconstruível: tokens CREDOR_n seguem a ordem das dívidas.
                _, mapa = anonimizar_credores([d.credor for d in perfil.dividas])
                fila.put(("ok", (resultado, mapa)))
            except Exception as e:  # noqa: BLE001 — erro vira status na GUI
                fila.put(("erro", e))

        threading.Thread(target=trabalho, daemon=True).start()
        self._aguardar_ia(fila)

    def _aguardar_ia(self, fila: queue.Queue):
        try:
            status, carga = fila.get_nowait()
        except queue.Empty:
            self.after(200, lambda: self._aguardar_ia(fila))
            return
        self.barra_ia.stop()
        self.btn_ia.config(state="normal")
        if status == "erro":
            self._status_ia(f"Erro ao gerar a análise: {carga}", COR_ERRO)
            return

        resultado, mapa = carga
        self.secao_ia = preparar_exibicao(resultado, mapa)
        self.txt_ia.delete("1.0", "end")
        self.txt_ia.insert("end", formatar_secao_ia(self.secao_ia))
        if self.secao_ia.modo == "completo":
            self._status_ia("✔ Análise concluída — conteúdo assistido por IA; "
                            "revise antes de agir. Será incluída no relatório .docx.",
                            COR_OK)
        else:  # T-304: indicador visual de modo degradado (P8)
            motivos = ", ".join(self.secao_ia.motivos) or "motivo não informado"
            self._status_ia("⚠ MODO DEGRADADO — IA indisponível; valendo o "
                            f"diagnóstico determinístico. Motivos: {motivos}",
                            COR_ALERTA)

    def _params_saida(self):
        return (parse_valor(self.var_extra.get()),
                parse_taxa(self.var_alvo.get()))

    def _gerar_xlsx(self):
        perfil = self._validar_dados()
        if not perfil:
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile="diagnostico_financeiro.xlsx")
        if not caminho:
            return
        extra, alvo = self._params_saida()
        try:
            gerar_planilha(perfil, caminho, extra_mensal=extra, taxa_alvo_mensal=alvo)
            messagebox.showinfo("Pronto", f"Planilha salva em:\n{caminho}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao gerar planilha:\n{e}")

    def _gerar_docx(self):
        perfil = self._validar_dados()
        if not perfil:
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".docx", filetypes=[("Word", "*.docx")],
            initialfile="relatorio_financeiro.docx")
        if not caminho:
            return
        extra, alvo = self._params_saida()
        try:
            gerar_relatorio(perfil, caminho, extra_mensal=extra,
                            taxa_alvo_mensal=alvo, nome_usuario=self.var_nome.get(),
                            secao_ia=self.secao_ia)
            messagebox.showinfo("Pronto", f"Relatório salvo em:\n{caminho}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao gerar relatório:\n{e}")

    # ---------------------------------------------------------------- aba carta
    def _aba_carta(self):
        frame = ttk.Frame(self.abas)
        self.abas.add(frame, text="  5. Carta ao credor  ")

        ttk.Label(frame, text="Gerar proposta de negociação",
                  style="Titulo.TLabel").grid(row=0, column=0, columnspan=2,
                                              sticky="w", padx=8, pady=(12, 6))

        ttk.Label(frame, text="Dívida (credor)").grid(row=1, column=0, sticky="w",
                                                      padx=8, pady=6)
        self.var_carta_divida = tk.StringVar()
        self.combo_dividas = ttk.Combobox(frame, textvariable=self.var_carta_divida,
                                          width=40, state="readonly")
        self.combo_dividas.grid(row=1, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(frame, text="Tipo de proposta").grid(row=2, column=0, sticky="w",
                                                       padx=8, pady=6)
        self.var_carta_tipo = tk.StringVar(value=list(TIPOS_PROPOSTA)[0])
        ttk.Combobox(frame, textvariable=self.var_carta_tipo,
                     values=list(TIPOS_PROPOSTA), width=40,
                     state="readonly").grid(row=2, column=1, sticky="w",
                                            padx=8, pady=6)

        self.c_contrato = self._campo(frame, "Nº do contrato (opcional)", 3)
        self.c_valor = self._campo(frame, "Valor proposto à vista (R$)", 4,
                                   numerico=True)
        self.c_banco = self._campo(frame, "Banco concorrente (portabilidade)",
                                   5)
        self.c_taxa = self._campo(frame, "Taxa do concorrente (% a.m.)", 6,
                                  numerico=True)

        ttk.Button(frame, text="✉ Gerar carta (.docx)", style="Primario.TButton",
                   command=self._gerar_proposta).grid(row=7, column=0,
                                                      columnspan=2, pady=14)

        ttk.Label(frame, text="Os campos de valor/banco/taxa só são usados "
                              "conforme o tipo de proposta escolhido.",
                  foreground="#777").grid(row=8, column=0, columnspan=2,
                                          sticky="w", padx=8)

    def _atualizar_combo_dividas(self):
        if hasattr(self, "combo_dividas"):
            nomes = [d.credor for d in self.dividas]
            self.combo_dividas["values"] = nomes
            if nomes and not self.var_carta_divida.get():
                self.var_carta_divida.set(nomes[0])

    def _gerar_proposta(self):
        if not self.dividas:
            messagebox.showwarning("Sem dívidas",
                                   "Cadastre uma dívida antes de gerar a carta.")
            return
        nome_sel = self.var_carta_divida.get()
        divida = next((d for d in self.dividas if d.credor == nome_sel),
                      self.dividas[0])
        tipo = TIPOS_PROPOSTA[self.var_carta_tipo.get()]

        dados = {
            "valor_proposto": parse_valor(self.c_valor.get()) or None,
            "banco_concorrente": self.c_banco.get().strip() or None,
            "taxa_concorrente_mensal": parse_taxa(self.c_taxa.get()) or None,
        }
        caminho = filedialog.asksaveasfilename(
            defaultextension=".docx", filetypes=[("Word", "*.docx")],
            initialfile=f"proposta_{tipo}.docx")
        if not caminho:
            return
        try:
            gerar_proposta(divida, caminho, tipo=tipo, dados=dados,
                           nome_usuario=self.var_nome.get(),
                           cpf=self.var_cpf.get(), contrato=self.c_contrato.get())
            messagebox.showinfo("Pronto", f"Carta salva em:\n{caminho}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao gerar carta:\n{e}")


def main():
    app = HelperFinanceiroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
