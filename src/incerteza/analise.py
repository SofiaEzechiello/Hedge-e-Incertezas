"""
Passo 6: análise descritiva do resultado do hedge.

    cenarios      custo com e sem hedge em meses de incerteza alta e normal
    por_ano       resultado do hedge por ano de contratação
    por_episodio  resultado nas crises (config.CRISES) e fora delas

A regressão (passo 7) fica em regressao.py.
"""

import pandas as pd

from . import config


def amostra_completa(base):
    """Só os cohorts que já venceram e têm incerteza no mês t."""
    return base.dropna(subset=["resultado", "incerteza"]).copy()


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