# %% [markdown]
# # Hedge cambial e incerteza
#
# **Trabalho de Derivativos e Riscos (UFRGS)**
#
# **Pergunta:** uma empresa **importadora** compra mercadoria em dólar todo mês e paga
# 3 meses depois. Para não correr o risco de o dólar subir, ela trava o câmbio comprando
# dólar futuro. **O hedge compensou financeiramente? E o que aconteceu nos períodos de
# incerteza alta?**
#
# **Dados (mensais, fechamento do mês, jul/2006 em diante):**
# - $U_t$: índice de incerteza de política econômica do Brasil (EPU), de Baker, Bloom e
#   Davis, construído com notícias da Folha de S.Paulo (www.PolicyUncertainty.com)
# - $F_t$: preço de ajuste do dólar futuro (DOL) que liquida pela PTAX de fim de $t+3$
#   (Boletins Diários da B3)
# - $S_{t+3}$: PTAX do dia da liquidação desse contrato (Banco Central)
#
# Nesta etapa a análise é **descritiva**: olhamos o que aconteceu, sem regressão.

# %%
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from IPython.display import display
except ImportError:  # pragma: no cover
    def display(obj):
        if hasattr(obj, "to_string"):
            print(obj.to_string())
        else:
            print(obj)

# Acha a pasta do projeto (onde fica a pasta src/) e importa o nosso código
RAIZ = Path.cwd()
while not (RAIZ / "src" / "incerteza").exists() and RAIZ != RAIZ.parent:
    RAIZ = RAIZ.parent
sys.path.insert(0, str(RAIZ / "src"))
from incerteza import analise, config  # noqa: E402

AZUL, LARANJA, CINZA = config.COR_PRINCIPAL, config.COR_SECUNDARIA, config.COR_TEXTO
VERDE, VERMELHO = "#1b998b", "#b22200"

base = pd.read_csv(RAIZ / "data" / "processed" / "base_hedge.csv", index_col="mes")
base.index = pd.PeriodIndex(base.index, freq="M")
dados = analise.amostra_completa(base)  # só operações que já venceram
LIMIAR = base["limiar_incerteza"].iloc[0]

print(f"Base: {base.index.min()} a {base.index.max()} ({len(base)} meses)")
print(f"Operações já vencidas: {len(dados)}")
print(f"Incerteza alta: EPU acima de {LIMIAR:.0f} (os 20% de meses mais incertos)")


def estilo(ax, titulo="", ylabel=""):
    ax.set_title(titulo, loc="left", fontsize=12, fontweight="bold", color=CINZA)
    ax.set_ylabel(ylabel, color=CINZA)
    ax.grid(axis="y", color=config.COR_GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)


def reais(x):
    return f"R$ {x:,.0f}".replace(",", ".")


# %% [markdown]
# ## 1. As séries
#
# Em cada mês $t$ a empresa trava o dólar a $F_t$. Três meses depois, o dólar de fato
# vale $S_{t+3}$. Todos os painéis estão alinhados pelo mês em que o hedge é
# **contratado**: a PTAX mostrada em janeiro é a de fim de abril, a que liquida o
# contrato comprado em janeiro.

# %%
x = dados.index.to_timestamp()
cores = [LARANJA if a else AZUL for a in dados["incerteza_alta"]]

fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True, gridspec_kw={"hspace": 0.35})
axes[0].plot(x, dados["incerteza"], color=CINZA, linewidth=1.4)
axes[0].axhline(LIMIAR, color=LARANJA, linestyle="--", linewidth=1)
estilo(axes[0], "Incerteza no mês da contratação ($U_t$, EPU Brasil)", "Índice EPU")

axes[1].plot(x, dados["futuro"], color=AZUL, linewidth=1.6)
estilo(axes[1], "Dólar futuro contratado em t ($F_t$)", r"R\$ por US\$")

axes[2].plot(x, dados["ptax_liquidacao"], color=LARANJA, linewidth=1.6)
estilo(axes[2], "PTAX no vencimento ($S_{t+3}$)", r"R\$ por US\$")

axes[3].bar(x, 100 * dados["resultado"], width=25, color=cores)
axes[3].axhline(0, color=CINZA, linewidth=0.8)
estilo(axes[3], "Resultado do hedge do importador ($H_t$, em %)", "%  (laranja = incerteza alta)")
plt.show()

# %% [markdown]
# ## 2. O hedge compensou?
#
# A importadora compra dólar futuro, então ganha quando o dólar sobe além do preço travado:
#
# $$H_t = \ln\left(\frac{S_{t+3}}{F_t}\right)
# \qquad\text{e, em reais, com 1 contrato (US\$ 50 mil):}\qquad (S_{t+3} - F_t)\times 50.000$$
#
# - $H_t > 0$: o dólar subiu mais do que o futuro previa e **o hedge compensou**.
# - $H_t < 0$: a empresa pagou mais do que pagaria sem hedge.
#
# (Para o exportador, que vende dólar futuro, o resultado é o espelho: $\ln(F_t/S_{t+3})$,
# a medida usada por Fama, 1984.)

# %%
print(f"Resultado médio por operação de 3 meses: {100 * dados['resultado'].mean():+.2f}%")
print(f"O hedge compensou em {100 * dados['hedge_compensou'].astype(float).mean():.0f}% dos meses")
print(f"Resultado médio por contrato: {reais(dados['resultado_reais'].mean())}")
print(f"Resultado acumulado (1 contrato por mês): {reais(dados['resultado_reais'].sum())}")

colunas = ["contrato", "futuro", "ptax_liquidacao", "incerteza", "resultado_reais"]
print("\nOs 5 meses em que o hedge mais compensou:")
display(dados.nlargest(5, "resultado_reais")[colunas].round(4))
print("Os 5 meses em que o hedge mais custou:")
display(dados.nsmallest(5, "resultado_reais")[colunas].round(4))

# %%
acumulado = dados["resultado_reais"].cumsum() / 1000
fig, ax = plt.subplots(figsize=(11, 4.5))
for mes in dados.index[dados["incerteza_alta"].astype(bool)]:
    ax.axvspan(mes.to_timestamp(), (mes + 1).to_timestamp(), color="#f3d9c4", linewidth=0)
ax.plot(acumulado.index.to_timestamp(), acumulado, color=AZUL, linewidth=2)
ax.axhline(0, color=CINZA, linewidth=0.8)
estilo(ax, "Resultado acumulado de fazer hedge todo mês (1 contrato por mês)",
       "R$ mil  (faixas = incerteza alta)")
plt.show()

# %% [markdown]
# ## 3. Incerteza alta × normal
#
# **Incerteza alta** = os 20% de meses com o EPU mais alto na amostra. Para cada grupo:
# quanto a empresa pagaria sem hedge, quanto pagou com hedge, a diferença e em quantos
# meses o hedge compensou.

# %%
cenarios = analise.cenarios(base)
display(cenarios.style.format({
    "meses": "{:.0f}",
    "sem_hedge_R$": "R$ {:,.0f}", "com_hedge_R$": "R$ {:,.0f}",
    "ganho_do_hedge_R$": "R$ {:,.0f}",
    "resultado_medio_%": "{:+.2f}%", "hedge_compensou_%": "{:.0f}%",
}))

fig, ax = plt.subplots(figsize=(7, 4.5))
grupos = [100 * dados.loc[~dados["incerteza_alta"].astype(bool), "resultado"],
          100 * dados.loc[dados["incerteza_alta"].astype(bool), "resultado"]]
caixas = ax.boxplot(grupos, patch_artist=True, widths=0.5,
                    medianprops={"color": "white", "linewidth": 2})
for caixa, cor in zip(caixas["boxes"], [AZUL, LARANJA]):
    caixa.set_facecolor(cor)
ax.set_xticks([1, 2], ["Incerteza normal", "Incerteza alta"])
ax.axhline(0, color=CINZA, linewidth=0.8)
estilo(ax, "Distribuição do resultado do hedge", "Resultado do hedge (%)")
plt.show()

# %% [markdown]
# ## 4. Ano a ano
#
# Resultado do hedge pelo ano em que foi contratado, com a incerteza média do ano.

# %%
anos = analise.por_ano(base)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                               gridspec_kw={"height_ratios": [1, 1.3], "hspace": 0.3})
ax1.bar(anos.index, anos["incerteza_media"], color=CINZA, width=0.7)
estilo(ax1, "Incerteza média do ano (EPU)", "Índice EPU")

ax2.bar(anos.index, anos["resultado_total_R$"] / 1000, width=0.7,
        color=[VERDE if v > 0 else VERMELHO for v in anos["resultado_total_R$"]])
ax2.axhline(0, color=CINZA, linewidth=0.8)
estilo(ax2, "Resultado do hedge no ano (1 contrato por mês)",
       "R$ mil  (verde = compensou)")
ax2.set_xticks(anos.index)
ax2.tick_params(axis="x", rotation=45)
plt.show()

display(anos.style.format({
    "meses": "{:.0f}", "incerteza_media": "{:.0f}",
    "resultado_medio_%": "{:+.2f}%", "hedge_compensou_%": "{:.0f}%",
    "resultado_total_R$": "R$ {:,.0f}",
}))

# %% [markdown]
# ## 5. Nas crises
#
# Resultado do hedge contratado durante três crises conhecidas, comparado com o resto do
# período. As datas vêm da história, não do índice, então esta tabela não depende do EPU.

# %%
crises = analise.por_episodio(base)
display(crises.style.format({
    "meses": "{:.0f}", "incerteza_media": "{:.0f}",
    "resultado_medio_%": "{:+.2f}%", "hedge_compensou_%": "{:.0f}%",
    "resultado_total_R$": "R$ {:,.0f}",
}))
for nome, (inicio, fim) in config.CRISES.items():
    print(f"{nome}: hedge contratado entre {inicio} e {fim}")

# %% [markdown]
# ## 6. Leitura e próximos passos
#
# **O que os dados mostram:** *(escrever depois de olhar os resultados acima)*
#
# **Cuidados:**
# - O EPU mede incerteza de **política econômica** a partir de notícias; a crise de 2008,
#   que foi mais financeira e externa, aparece menos nele do que em 2015-16.
# - "Incerteza alta" é definida pelos 20% de meses mais altos da amostra; outro corte
#   pode mudar a divisão dos meses.
# - Em vários meses o vencimento usado teve poucos contratos em aberto; nesses casos o
#   preço de ajuste é calculado pela B3, não negociado.
# - Hedge de 1 contrato por mês, sem custos de corretagem e margem.
#
# **Próximo passo:** análise estatística (regressão do resultado do hedge no índice de
# incerteza, com erros-padrão de Newey-West), já pronta no código em `analise.py`.