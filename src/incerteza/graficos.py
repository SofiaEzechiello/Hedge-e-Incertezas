"""
Gráficos do indicador. Cada função recebe séries mensais (PeriodIndex) e salva um PNG.
"""

import matplotlib

matplotlib.use("Agg")  # salva sem abrir janela (funciona em qualquer terminal)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from . import config

FONTE_PADRAO = "Fonte: Banco Central (atas do COPOM e Focus). Elaboração própria."


def _estilo(ax, titulo, ylabel):
    ax.set_title(titulo, loc="left", fontsize=13, fontweight="bold", color=config.COR_TEXTO)
    ax.set_ylabel(ylabel, color=config.COR_TEXTO)
    ax.set_xlabel("")
    ax.grid(axis="y", color=config.COR_GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(config.COR_GRADE)
    ax.tick_params(colors=config.COR_TEXTO)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def _salvar(fig, nome, fonte):
    fig.text(0.01, -0.02, fonte, fontsize=8, color="#6b6b6b")
    config.FIGURAS.mkdir(parents=True, exist_ok=True)
    caminho = config.FIGURAS / nome
    fig.savefig(caminho, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return caminho


def _linha_base(ax, valor=100):
    ax.axhline(valor, color="#8c8c8c", linewidth=0.8, linestyle="--")


def grafico_indicador(serie, titulo, nome="iiebr.png"):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(serie.index.to_timestamp(), serie, color=config.COR_PRINCIPAL, linewidth=2)
    _linha_base(ax)
    _estilo(ax, titulo, "Índice (100 = média 2006-2015)")
    return _salvar(fig, nome, FONTE_PADRAO)


def grafico_comparacao(series, titulo, nome, fonte=FONTE_PADRAO):
    """series: dicionário {rótulo: série}. Até 3 séries."""
    cores = [config.COR_PRINCIPAL, config.COR_SECUNDARIA, config.COR_TERCIARIA]
    fig, ax = plt.subplots(figsize=(10, 5))
    for (rotulo, serie), cor in zip(series.items(), cores):
        serie = serie.dropna()
        ax.plot(serie.index.to_timestamp(), serie, color=cor, linewidth=2, label=rotulo)
    _linha_base(ax)
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="none", framealpha=0.9)
    _estilo(ax, titulo, "Índice (100 = média 2006-2015)")
    return _salvar(fig, nome, fonte)


def grafico_futuro_vs_spot(base, horizonte, nome="futuro_vs_ptax.png"):
    """
    Em cada mês t: o preço do futuro contratado em t e a PTAX que de fato
    ocorreu no vencimento (t + horizonte). A distância entre as linhas é o
    "erro" do futuro. Os últimos meses só têm futuro: o vencimento ainda não chegou.
    """
    x = base.index.to_timestamp()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(x, base["futuro"], color=config.COR_PRINCIPAL, linewidth=2,
            label=f"Dólar futuro em t (vence em {horizonte} meses)")
    ax.plot(x, base["ptax_liquidacao"], color=config.COR_SECUNDARIA, linewidth=2,
            label=f"PTAX efetiva {horizonte} meses depois")
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="none", framealpha=0.9)
    _estilo(ax, "Dólar futuro vs. dólar que de fato ocorreu no vencimento", r"R\$ por US\$")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.set_xlabel("Mês em que o hedge é contratado (t)", color=config.COR_TEXTO)
    return _salvar(fig, nome, "Fontes: B3 (preço de ajuste do DOL) e Banco Central (PTAX). "
                              "Elaboração própria.")


FONTE_HEDGE = ("Fontes: B3 (dólar futuro), Banco Central (PTAX) e Baker, Bloom e Davis "
               "(EPU Brasil). Elaboração própria.")
COR_ALTA = config.COR_SECUNDARIA      # laranja: incerteza alta
COR_NORMAL = config.COR_PRINCIPAL     # azul: incerteza normal
COR_SOMBRA = "#f3d9c4"                # faixa clara dos meses de incerteza alta


def _sombrear_incerteza_alta(ax, base):
    """Pinta de fundo os meses em que a incerteza estava acima do limiar."""
    alta = base["incerteza_alta"].fillna(False).astype(bool)
    for mes in base.index[alta]:
        ax.axvspan(mes.to_timestamp(), (mes + 1).to_timestamp(),
                   color=COR_SOMBRA, linewidth=0, zorder=0)


def grafico_resultado_hedge(base, lado, nome="5_resultado_hedge.png"):
    """
    Dois painéis com o mesmo eixo de tempo (em vez de dois eixos y):
    em cima a incerteza em t, embaixo o resultado do hedge contratado em t.
    """
    dados = base.dropna(subset=["resultado"])
    x = dados.index.to_timestamp()
    cores = [COR_ALTA if a else COR_NORMAL for a in dados["incerteza_alta"].fillna(False)]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.4], "hspace": 0.15})
    ax1.plot(x, dados["incerteza"], color=config.COR_TEXTO, linewidth=1.8)
    ax1.axhline(config.LIMIAR_INCERTEZA, color=COR_ALTA, linewidth=1, linestyle="--")
    ax1.text(1.0, config.LIMIAR_INCERTEZA, f" limiar\n {config.LIMIAR_INCERTEZA}",
             transform=ax1.get_yaxis_transform(), va="center", ha="left",
             fontsize=8, color=COR_ALTA)
    _estilo(ax1, f"Resultado do hedge do {lado} e incerteza no mês da contratação",
            "Incerteza (U_t)")

    ax2.bar(x, 100 * dados["resultado"], width=25, color=cores)
    ax2.axhline(0, color=config.COR_TEXTO, linewidth=0.8)
    _estilo(ax2, "", f"Resultado do hedge (%)\nln(s_t+{config.HORIZONTE_HEDGE} / f_t)"
            if lado == "importador" else
            f"Resultado do hedge (%)\nln(f_t / s_t+{config.HORIZONTE_HEDGE})")
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.set_xlabel("Mês em que o hedge é contratado (t)", color=config.COR_TEXTO)

    from matplotlib.patches import Patch
    ax2.legend(handles=[Patch(color=COR_ALTA, label="Incerteza alta em t"),
                        Patch(color=COR_NORMAL, label="Incerteza normal em t")],
               loc="upper left", frameon=True, facecolor="white", edgecolor="none",
               framealpha=0.9)
    return _salvar(fig, nome, FONTE_HEDGE)


def grafico_dispersao(base, reg, lado, nome="6_incerteza_vs_resultado.png"):
    """Cada ponto é um mês: incerteza em t no eixo x, resultado do hedge no eixo y."""
    import numpy as np

    dados = base.dropna(subset=["resultado", "incerteza"])
    p = reg.loc["Principal"]
    cores = [COR_ALTA if a else COR_NORMAL for a in dados["incerteza_alta"]]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(dados["incerteza"], 100 * dados["resultado"], c=cores, s=40,
               edgecolor="white", linewidth=1, zorder=3)
    xs = np.linspace(dados["incerteza"].min(), dados["incerteza"].max(), 50)
    ys = 100 * (p["alfa"] + p["beta"] * (xs - config.MEDIA_BASE))
    ax.plot(xs, ys, color=config.COR_TEXTO, linewidth=2)
    ax.axhline(0, color="#8c8c8c", linewidth=0.8)
    ax.axvline(config.LIMIAR_INCERTEZA, color=COR_ALTA, linewidth=1, linestyle="--")

    ax.set_title(f"O resultado do hedge do {lado} depende da incerteza?", loc="left",
                 fontsize=13, fontweight="bold", color=config.COR_TEXTO, pad=28)
    ax.text(0, 1.02, f"Reta: β = {100 * p['beta']:.3f} p.p. por ponto de incerteza "
                     f"(p = {p['beta_p']:.3f}, Newey-West).  Laranja: incerteza acima de "
                     f"{config.LIMIAR_INCERTEZA}.",
            transform=ax.transAxes, fontsize=9, color="#6b6b6b")
    ax.set_xlabel("Incerteza no mês da contratação (U_t)", color=config.COR_TEXTO)
    ax.set_ylabel("Resultado do hedge (%)", color=config.COR_TEXTO)
    ax.grid(color=config.COR_GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado_ax in ("top", "right"):
        ax.spines[lado_ax].set_visible(False)
    return _salvar(fig, nome, FONTE_HEDGE)


def grafico_acumulado(base, lado, nome="7_resultado_acumulado.png"):
    """Ganho acumulado (R$) de fazer hedge todo mês em vez de nunca fazer."""
    dados = base.dropna(subset=["resultado_reais"])
    acumulado = dados["resultado_reais"].cumsum() / 1e6

    fig, ax = plt.subplots(figsize=(10, 5))
    _sombrear_incerteza_alta(ax, dados)
    ax.plot(acumulado.index.to_timestamp(), acumulado, color=config.COR_PRINCIPAL, linewidth=2.2)
    ax.axhline(0, color=config.COR_TEXTO, linewidth=0.8)
    _estilo(ax, f"Quanto o {lado} ganhou (ou perdeu) por fazer hedge todo mês",
            r"Ganho acumulado (R\$ milhões)")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.set_xlabel("Mês em que o hedge é contratado (t)", color=config.COR_TEXTO)

    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=COR_SOMBRA, label="Meses de incerteza alta")],
              loc="upper left", frameon=True, facecolor="white", edgecolor="none",
              framealpha=0.9)
    exposicao = f"US$ {config.EXPOSICAO_USD:,.0f}".replace(",", ".")
    return _salvar(fig, nome, f"Empresa simulada: {exposicao} por mês, hedge de "
                              f"{config.HORIZONTE_HEDGE} meses. {FONTE_HEDGE}")


def grafico_componentes(resultado, nome="componentes.png"):
    """Os dois componentes lado a lado, ambos em desvios-padrão (z-score)."""
    from .indicador import padronizar  # import local evita ciclo

    texto = padronizar(resultado["componente_texto"])
    exp = padronizar(resultado["componente_expectativas"])
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(texto.index.to_timestamp(), texto, color=config.COR_PRINCIPAL,
            linewidth=2, label="Texto (atas do COPOM)")
    ax.plot(exp.index.to_timestamp(), exp, color=config.COR_SECUNDARIA,
            linewidth=2, label="Expectativas (Focus)")
    ax.axhline(0, color="#8c8c8c", linewidth=0.8, linestyle="--")
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="none", framealpha=0.9)
    _estilo(ax, "Os dois componentes do indicador", "Desvios-padrão (z-score, 2006-2015)")
    return _salvar(fig, nome, FONTE_PADRAO)


# ---------------------------------------------------------------------------
# Gráficos da análise descritiva (EPU, alta x normal, crises, por ano)
# ---------------------------------------------------------------------------
COR_GANHO, COR_PERDA = "#1b998b", "#b22200"


def _rotulo_barra(ax, barras, textos):
    for barra, texto in zip(barras, textos):
        altura = barra.get_height()
        ax.annotate(texto, (barra.get_x() + barra.get_width() / 2, altura),
                    xytext=(0, 4 if altura >= 0 else -12), textcoords="offset points",
                    ha="center", fontsize=10, color=config.COR_TEXTO, fontweight="bold")


def grafico_epu(base, nome="1_incerteza_epu.png"):
    """O índice EPU nos meses do trabalho, com o limiar e as crises marcadas."""
    dados = base.dropna(subset=["incerteza"])
    limiar = dados["limiar_incerteza"].iloc[0]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for nome_crise, (ini, fim) in config.CRISES.items():
        x0, x1 = pd.Period(ini, "M").to_timestamp(), (pd.Period(fim, "M") + 1).to_timestamp()
        ax.axvspan(x0, x1, color="#e6e6e6", linewidth=0, zorder=0)
        ax.text(x0, 0.97, " " + nome_crise, transform=ax.get_xaxis_transform(),
                fontsize=7.5, color="#6b6b6b", va="top")
    ax.plot(dados.index.to_timestamp(), dados["incerteza"], color=config.COR_TEXTO, linewidth=1.5)
    ax.axhline(limiar, color=config.COR_SECUNDARIA, linewidth=1.2, linestyle="--")
    ax.text(1.0, limiar, f" incerteza\n alta > {limiar:.0f}", transform=ax.get_yaxis_transform(),
            va="center", fontsize=8, color=config.COR_SECUNDARIA)
    _estilo(ax, "Incerteza de política econômica no Brasil (EPU)", "Índice EPU")
    return _salvar(fig, nome, "Fonte: Baker, Bloom e Davis, www.PolicyUncertainty.com. "
                              "Faixas cinza: crises.")


def grafico_alta_vs_normal(cen, nome="6_alta_vs_normal.png"):
    """Três números lado a lado para incerteza normal e alta."""
    grupos = ["Incerteza normal", "Incerteza alta"]
    cen = cen.loc[grupos]
    cores = [config.COR_PRINCIPAL, config.COR_SECUNDARIA]
    paineis = [
        ("Resultado médio por operação", cen["resultado_medio_%"], "%", "{:+.1f}%"),
        ("Meses em que o hedge compensou", cen["hedge_compensou_%"], "% dos meses", "{:.0f}%"),
        ("Resultado total (1 contrato/mês)", cen["ganho_do_hedge_R$"] / 1000, "R$ mil", "{:+,.0f} mil"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5))
    for ax, (titulo, valores, ylabel, fmt) in zip(axes, paineis):
        barras = ax.bar(["Normal", "Alta"], valores, color=cores, width=0.6)
        _rotulo_barra(ax, barras, [fmt.format(v).replace(",", ".") for v in valores])
        ax.axhline(0, color=config.COR_TEXTO, linewidth=0.8)
        ax.margins(y=0.2)
        ax.set_title(titulo, loc="left", fontsize=11, fontweight="bold", color=config.COR_TEXTO)
        ax.set_ylabel(ylabel, color=config.COR_TEXTO)
        ax.grid(axis="y", color=config.COR_GRADE, linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
    n_alta, n_normal = int(cen.loc["Incerteza alta", "meses"]), int(cen.loc["Incerteza normal", "meses"])
    fig.suptitle(f"Hedge da importadora: incerteza normal ({n_normal} meses) x alta ({n_alta} meses)",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=config.COR_TEXTO)
    fig.tight_layout()
    return _salvar(fig, nome, "Incerteza alta: os 20% de meses com o EPU mais alto. " + FONTE_HEDGE)


def grafico_crises(crises, nome="6_crises.png"):
    """Resultado médio do hedge contratado em cada crise e fora delas."""
    tabela = crises.drop("Total")
    valores = tabela["resultado_medio_%"]
    meses_pt = "jan fev mar abr mai jun jul ago set out nov dez".split()

    def periodo(nome):
        if nome not in config.CRISES:
            return ""
        i, f = (pd.Period(d, "M") for d in config.CRISES[nome])
        return f"{meses_pt[i.month - 1]}/{i.year % 100:02d} a {meses_pt[f.month - 1]}/{f.year % 100:02d}, "

    rotulos = [f"{n}\n({periodo(n)}{m} meses)" for n, m in zip(tabela.index, tabela["meses"])]
    fig, ax = plt.subplots(figsize=(10, 4))
    y = range(len(tabela))[::-1]
    barras = ax.barh(list(y), valores, color=[COR_GANHO if v > 0 else COR_PERDA for v in valores],
                     height=0.6)
    ax.set_yticks(list(y), rotulos)
    for barra, v, r in zip(barras, valores, tabela["resultado_total_R$"]):
        ax.annotate(f"{v:+.1f}%  (R$ {r / 1000:+,.0f} mil)".replace(",", "."),
                    (v, barra.get_y() + barra.get_height() / 2),
                    xytext=(6 if v >= 0 else -6, 0), textcoords="offset points",
                    ha="left" if v >= 0 else "right", va="center", fontsize=9,
                    color=config.COR_TEXTO)
    ax.axvline(0, color=config.COR_TEXTO, linewidth=0.8)
    ax.margins(x=0.45)
    ax.set_title("Resultado médio do hedge contratado em cada crise (% por operação)", loc="left",
                 fontsize=13, fontweight="bold", color=config.COR_TEXTO)
    ax.grid(axis="x", color=config.COR_GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    return _salvar(fig, nome, "Pelo mês em que o hedge foi contratado. Verde: o hedge compensou "
                              "em média. " + FONTE_HEDGE)


def grafico_por_ano(anos, nome="6_por_ano.png"):
    """Incerteza média e resultado do hedge, ano a ano."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.3], "hspace": 0.3})
    ax1.bar(anos.index, anos["incerteza_media"], color=config.COR_TEXTO, width=0.7)
    ax1.set_title("Incerteza média do ano (EPU)", loc="left", fontsize=12,
                  fontweight="bold", color=config.COR_TEXTO)
    resultado = anos["resultado_total_R$"] / 1000
    ax2.bar(anos.index, resultado, width=0.7,
            color=[COR_GANHO if v > 0 else COR_PERDA for v in resultado])
    ax2.axhline(0, color=config.COR_TEXTO, linewidth=0.8)
    ax2.set_title("Resultado do hedge contratado no ano (1 contrato por mês)", loc="left",
                  fontsize=12, fontweight="bold", color=config.COR_TEXTO)
    ax2.set_ylabel(r"R\$ mil  (verde = compensou)", color=config.COR_TEXTO)
    ax1.set_ylabel("Índice EPU", color=config.COR_TEXTO)
    for ax in (ax1, ax2):
        ax.grid(axis="y", color=config.COR_GRADE, linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
    ax2.set_xticks(anos.index)
    ax2.tick_params(axis="x", rotation=45)
    return _salvar(fig, nome, FONTE_HEDGE)


def graficos_descritivos(base, cen, crises, anos):
    """Gera todos os gráficos da análise descritiva de uma vez."""
    grafico_epu(base)
    grafico_alta_vs_normal(cen)
    grafico_crises(crises)
    grafico_por_ano(anos)