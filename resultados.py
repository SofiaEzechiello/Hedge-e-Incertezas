# %% [markdown]
# # Hedge cambial e incerteza
#
# **Trabalho de Derivativos e Riscos (UFRGS)**
#
# **Pergunta:** uma empresa **importadora** que todo mês compra mercadoria em dólar e
# paga 3 meses depois faz hedge com dólar futuro. O hedge compensa financeiramente?
# E compensa mais quando a **incerteza econômica** está alta?
#
# **Dados (mensais, fechamento do mês):**
# - $U_t$: indicador de incerteza (réplica do IIE-Br da FGV com atas do COPOM e Focus)
# - $F_t$: preço de ajuste do dólar futuro (DOL) que liquida pela PTAX de fim de $t+3$
#   (planilha a partir dos Boletins Diários da B3, desde jul/2006)
# - $S_{t+3}$: PTAX do dia da liquidação desse contrato (Banco Central)
#
# Este notebook só lê as tabelas que o `main.py` gera em `data/processed/`.
# Não baixa nada.

# %%
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from IPython.display import display
except ImportError:
    def display(obj=None, *args, **kwargs):
        if obj is not None:
            print(obj)

# Acha a pasta do projeto (onde fica a pasta src/) e importa o nosso código
RAIZ = Path.cwd()
while not (RAIZ / "src" / "incerteza").exists() and RAIZ != RAIZ.parent:
    RAIZ = RAIZ.parent
sys.path.insert(0, str(RAIZ / "src"))
from incerteza import analise, config  # noqa: E402

pd.set_option("display.float_format", lambda x: f"{x:,.4f}")
AZUL, LARANJA, CINZA = config.COR_PRINCIPAL, config.COR_SECUNDARIA, config.COR_TEXTO

base = pd.read_csv(RAIZ / "data" / "processed" / "base_hedge.csv", index_col="mes")
base.index = pd.PeriodIndex(base.index, freq="M")
dados = analise.amostra_completa(base)  # só operações que já venceram

print(f"Base: {base.index.min()} a {base.index.max()} ({len(base)} meses)")
print(f"Operações já vencidas e com incerteza: {len(dados)}")


def estilo(ax, titulo="", ylabel=""):
    ax.set_title(titulo, loc="left", fontsize=12, fontweight="bold", color=CINZA)
    ax.set_ylabel(ylabel, color=CINZA)
    ax.grid(axis="y", color=config.COR_GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)


# %% [markdown]
# ## 1. As séries
#
# Em cada mês $t$ a empresa trava o dólar a $F_t$. Três meses depois, o dólar de fato
# vale $S_{t+3}$. Os três painéis de baixo estão alinhados pelo mês em que o hedge é
# **contratado**: a PTAX mostrada em janeiro é a de fim de abril, a que liquida o
# contrato comprado em janeiro.

# %%
x = dados.index.to_timestamp()
fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True,
                         gridspec_kw={"hspace": 0.35})

axes[0].plot(x, dados["incerteza"], color=CINZA, linewidth=1.6)
axes[0].axhline(config.LIMIAR_INCERTEZA, color=LARANJA, linestyle="--", linewidth=1)
estilo(axes[0], "Incerteza no mês da contratação ($U_t$)", "Índice (100 = média 2006-15)")

axes[1].plot(x, dados["futuro"], color=AZUL, linewidth=1.6)
estilo(axes[1], "Dólar futuro contratado em t ($F_t$)", r"R\$ por US\$")

axes[2].plot(x, dados["ptax_liquidacao"], color=LARANJA, linewidth=1.6)
estilo(axes[2], "PTAX no vencimento ($S_{t+3}$)", r"R\$ por US\$")

cores = [LARANJA if a else AZUL for a in dados["incerteza_alta"]]
axes[3].bar(x, 100 * dados["resultado"], width=25, color=cores)
axes[3].axhline(0, color=CINZA, linewidth=0.8)
estilo(axes[3], "Resultado do hedge do importador ($H_t$, em %)",
       "%  (laranja = incerteza alta)")
plt.show()

# %% [markdown]
# ## 2. O resultado do hedge
#
# Para o **exportador** (vende dólar futuro), a medida baseada em Fama (1984) é
# $H_t = \ln(F_t / S_{t+3})$. A **importadora** está do outro lado e ganha o espelho:
#
# $$H^{imp}_t = \ln\left(\frac{S_{t+3}}{F_t}\right) = -H_t$$
#
# - $H^{imp}_t > 0$: o dólar subiu mais do que o futuro previa e **o hedge compensou**.
# - $H^{imp}_t < 0$: a empresa pagou mais do que pagaria sem hedge.
#
# Em reais, com **1 contrato por mês (US\$ 50 mil)**:
# resultado $= (S_{t+3} - F_t) \times 50.000$. Os ajustes diários da B3 somam
# exatamente esse valor até o vencimento.

# %%
dados["resultado_por_contrato"] = (
    (dados["ptax_liquidacao"] - dados["futuro"]) * config.TAMANHO_CONTRATO_USD
)
print(f"Resultado médio do hedge: {100 * dados['resultado'].mean():+.2f}% por operação de 3 meses")
print(f"O hedge compensou em {100 * dados['hedge_compensou'].astype(float).mean():.0f}% dos meses")
print(f"Resultado médio por contrato: R$ {dados['resultado_por_contrato'].mean():,.0f}")
print(f"Resultado acumulado (1 contrato/mês): R$ {dados['resultado_por_contrato'].sum():,.0f}")

colunas = ["contrato", "futuro", "ptax_liquidacao", "incerteza", "resultado_por_contrato"]
print("\nMelhores meses para ter feito hedge:")
display(dados.nlargest(5, "resultado_por_contrato")[colunas])
print("Piores meses:")
display(dados.nsmallest(5, "resultado_por_contrato")[colunas])

# %%
acumulado = dados["resultado_por_contrato"].cumsum() / 1000
fig, ax = plt.subplots(figsize=(11, 4.5))
for mes in dados.index[dados["incerteza_alta"].astype(bool)]:
    ax.axvspan(mes.to_timestamp(), (mes + 1).to_timestamp(), color="#f3d9c4", linewidth=0)
ax.plot(acumulado.index.to_timestamp(), acumulado, color=AZUL, linewidth=2)
ax.axhline(0, color=CINZA, linewidth=0.8)
estilo(ax, "Resultado acumulado de fazer hedge todo mês (1 contrato por mês)",
       "R$ mil  (faixas = incerteza alta)")
plt.show()

# %% [markdown]
# ## 3. Cenários: com e sem hedge, com incerteza alta e normal
#
# Meses de **incerteza alta**: índice acima de 110, ou seja, 1 desvio-padrão acima da
# média de referência (2006-2015). Valores em R$ somados no período, com 1 contrato
# por mês.

# %%
cenarios = analise.cenarios(base)
display(cenarios.style.format({
    "meses": "{:.0f}",
    "sem_hedge_R$": "R$ {:,.0f}", "com_hedge_R$": "R$ {:,.0f}",
    "ganho_do_hedge_R$": "R$ {:,.0f}",
    "resultado_medio_%": "{:+.2f}%", "hedge_compensou_%": "{:.0f}%",
}))

# %% [markdown]
# ## 4. A incerteza explica o resultado do hedge?
#
# $$H^{imp}_t = \alpha + \beta\,(U_t - 100) + \varepsilon_t$$
#
# - $\alpha$: resultado médio do hedge com incerteza normal (índice = 100).
# - $\beta > 0$: o hedge do importador rende **mais** quando a incerteza está alta.
#   $\beta < 0$: rende **menos**. Para o exportador os sinais se invertem.
# - Erros-padrão de **Newey-West** (3 defasagens): cada operação dura 3 meses e começa
#   uma nova todo mês, então operações vizinhas compartilham meses e os erros ficam
#   autocorrelacionados (Hansen e Hodrick, 1980).
# - Robustez: com dummy de incerteza alta, sem 2020 e só com operações que não se
#   sobrepõem (contratadas em jan, abr, jul e out).

# %%
reg = analise.regressoes(base)
display(reg[["n", "alfa", "alfa_p", "beta", "beta_ep", "beta_t", "beta_p", "r2"]])
print(analise.texto_conclusao(reg))

# %%
p = reg.loc["Principal"]
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(dados["incerteza"], 100 * dados["resultado"], c=cores, s=35,
           edgecolor="white", linewidth=0.8, zorder=3)
xs = np.linspace(dados["incerteza"].min(), dados["incerteza"].max(), 50)
ax.plot(xs, 100 * (p["alfa"] + p["beta"] * (xs - config.MEDIA_BASE)), color=CINZA, linewidth=2)
ax.axhline(0, color="#8c8c8c", linewidth=0.8)
ax.axvline(config.LIMIAR_INCERTEZA, color=LARANJA, linestyle="--", linewidth=1)
estilo(ax, "Incerteza em t × resultado do hedge do importador", "Resultado do hedge (%)")
ax.set_xlabel("Incerteza no mês da contratação ($U_t$)", color=CINZA)
ax.text(0, 1.01, f"β = {100 * p['beta']:.3f} p.p. por ponto (p = {p['beta_p']:.3f}, Newey-West)",
        transform=ax.transAxes, fontsize=9, color="#6b6b6b")
plt.show()

# %% [markdown]
# ## 5. Leitura e limitações
#
# **Conclusão:** *(precisamos escrever depois de olhar os resultados!!)*
#
# **Limitações:**
# - Tudo que se lê como "prêmio" depende da hipótese de expectativas racionais (Fama, 1984):
#   só observamos o prêmio somado ao erro de previsão.
# - Em vários meses o vencimento usado teve pouquíssimos contratos em aberto; nesses casos
#   o preço de ajuste é calculado pela B3, não negociado.
# - Hedge ratio de 1, sem custos de corretagem, margem ou financiamento dos ajustes diários.
# - O índice de incerteza é uma réplica com fontes públicas (atas do COPOM no lugar de
#   jornais), não o IIE-Br oficial.
# - Poucos episódios de incerteza extrema (2008, 2015-16, 2020): o poder dos testes é baixo.