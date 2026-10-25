"""
Passo 7: o resultado do hedge depende da incerteza?

    1. Regressão contínua:  H_t = α + β·U_t + ε_t
    2. Regressão com dummy: H_t = α + δ·D_t + ε_t,  D_t = 1 se U_t > limiar
    3. Cenários: custo com e sem hedge em meses de incerteza alta e normal
    4. Robustez: sem a pandemia e só com cohorts que não se sobrepõem

Erros-padrão de Newey-West (HAC) com 3 defasagens, porque cada cohort olha
3 meses à frente e cohorts vizinhos compartilham meses (Hansen e Hodrick, 1980).

Leitura (resumo do Bernardo, item 4), sempre condicional à hipótese de
expectativas racionais:
    α  ~ resultado médio do hedge (para o exportador, o prêmio médio de Fama)
    β > 0  o hedge rende mais quando a incerteza está alta
    β < 0  o hedge rende menos quando a incerteza está alta
Para o importador, α e β trocam de sinal; erros-padrão, t e R² são idênticos.
"""

import pandas as pd
import statsmodels.api as sm

from . import config


def amostra_completa(base):
    """Só os cohorts que já venceram e têm incerteza no mês t."""
    return base.dropna(subset=["resultado", "incerteza"]).copy()


def _ols(y, x, lags):
    X = sm.add_constant(x.astype(float))
    if lags > 0:
        return sm.OLS(y.astype(float), X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return sm.OLS(y.astype(float), X).fit(cov_type="HC1")


def regressao(dados, x="incerteza_c", y="resultado", lags=config.LAGS_NEWEY_WEST, nome=""):
    """Regressão de y em x. Devolve um dicionário com os números para a tabela."""
    modelo = _ols(dados[y], dados[x], lags)
    return {
        "especificacao": nome,
        "x": x,
        "n": int(modelo.nobs),
        "alfa": modelo.params["const"],
        "alfa_p": modelo.pvalues["const"],
        "beta": modelo.params[x],
        "beta_ep": modelo.bse[x],
        "beta_t": modelo.tvalues[x],
        "beta_p": modelo.pvalues[x],
        "r2": modelo.rsquared,
        "lags_nw": lags,
    }


def regressoes(base):
    """Todas as especificações (principal + robustez) numa tabela só."""
    dados = amostra_completa(base)
    dados["incerteza_alta"] = dados["incerteza_alta"].astype(float)
    # Índice centrado na média histórica (100): o α passa a ser o resultado
    # esperado do hedge com incerteza "normal", e não com incerteza zero.
    dados["incerteza_c"] = dados["incerteza"] - config.MEDIA_BASE

    inicio, fim = (pd.Period(p, "M") for p in config.PERIODO_PANDEMIA)
    sem_pandemia = dados[(dados.index < inicio) | (dados.index > fim)]
    # Cohorts sem sobreposição: contratados em jan, abr, jul e out
    sem_sobreposicao = dados[dados.index.month % config.HORIZONTE_HEDGE == 1]

    linhas = [
        regressao(dados, nome="Principal"),
        regressao(dados, x="incerteza_alta", nome=f"Dummy (U > {config.LIMIAR_INCERTEZA})"),
        regressao(sem_pandemia, nome="Sem 2020"),
        regressao(sem_sobreposicao, lags=0, nome="Sem sobreposição (jan/abr/jul/out)"),
    ]
    return pd.DataFrame(linhas).set_index("especificacao")


def cenarios(base):
    """
    A tabela dos cenários: com e sem hedge, em incerteza alta e normal.

    Para cada regime: quantos meses, quanto a empresa pagaria sem hedge,
    quanto pagou com hedge, a diferença em R$, o resultado médio do hedge em %
    e em quantos meses o hedge compensou.
    """
    dados = amostra_completa(base)
    dados["regime"] = dados["incerteza_alta"].map({True: "Incerteza alta",
                                                   False: "Incerteza normal"})
    col_sem = "custo_sem_hedge" if "custo_sem_hedge" in dados else "receita_sem_hedge"
    col_com = "custo_com_hedge" if "custo_com_hedge" in dados else "receita_com_hedge"

    def resumo(g):
        return pd.Series({
            "meses": len(g),
            "sem_hedge_R$": g[col_sem].sum(),
            "com_hedge_R$": g[col_com].sum(),
            "ganho_do_hedge_R$": g["resultado_reais"].sum(),
            "resultado_medio_%": 100 * g["resultado"].mean(),
            "hedge_compensou_%": 100 * g["hedge_compensou"].astype(float).mean(),
        })

    tabela = dados.groupby("regime").apply(resumo, include_groups=False)
    tabela.loc["Total"] = resumo(dados)
    return tabela


def texto_conclusao(reg, lado=config.LADO_EMPRESA):
    """Uma frase em português para cada número da regressão principal."""
    p = reg.loc["Principal"]
    efeito = 100 * p["beta"] * config.DESVIO_BASE  # efeito de +10 pontos (1 desvio) em %
    sinal = "mais" if p["beta"] > 0 else "menos"
    signif = "é" if p["beta_p"] < 0.05 else "NÃO é"
    return (
        f"Para o {lado}, com incerteza normal (índice = {config.MEDIA_BASE}) o hedge rende "
        f"em média {100 * p['alfa']:+.2f}% por operação de {config.HORIZONTE_HEDGE} meses. "
        f"Cada +{config.DESVIO_BASE} pontos de incerteza (1 desvio) mudam o resultado do hedge em "
        f"{efeito:+.2f} ponto percentual: o hedge rende {sinal} com incerteza alta. "
        f"Esse efeito {signif} estatisticamente diferente de zero a 5% "
        f"(p = {p['beta_p']:.3f}, Newey-West, n = {p['n']:.0f})."
    )



# ---------------------------------------------------------------------------
# Análise descritiva (sem regressão)
# ---------------------------------------------------------------------------
def _resumo_descritivo(g):
    return pd.Series({
        "meses": len(g),
        "incerteza_media": g["incerteza"].mean(),
        "resultado_medio_%": 100 * g["resultado"].mean(),
        "hedge_compensou_%": 100 * g["hedge_compensou"].astype(float).mean(),
        "resultado_total_R$": g["resultado_reais"].sum(),
    })


def por_ano(base):
    """Resultado do hedge por ano em que foi contratado."""
    dados = amostra_completa(base)
    tabela = dados.groupby(dados.index.year).apply(_resumo_descritivo, include_groups=False)
    tabela.index.name = "ano"
    return tabela.astype({"meses": int})


def por_episodio(base, crises=None):
    """Resultado do hedge contratado durante cada crise e fora delas."""
    crises = config.CRISES if crises is None else crises
    dados = amostra_completa(base)
    dados["episodio"] = "Fora das crises"
    for nome, (inicio, fim) in crises.items():
        dentro = (dados.index >= pd.Period(inicio, "M")) & (dados.index <= pd.Period(fim, "M"))
        dados.loc[dentro, "episodio"] = nome
    tabela = dados.groupby("episodio").apply(_resumo_descritivo, include_groups=False)
    ordem = [n for n in crises if n in tabela.index] + ["Fora das crises"]
    tabela = tabela.loc[[n for n in ordem if n in tabela.index]]
    tabela.loc["Total"] = _resumo_descritivo(dados)
    return tabela.astype({"meses": int})
