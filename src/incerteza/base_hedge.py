"""
Passos 5 e 6: base mensal casada e resultado do hedge.

Cada linha é um mês t (fechamento do último dia útil). A empresa simulada
fecha em t uma compra de US$ que paga em t + 3 e trava o câmbio comprando
dólar futuro.

    incerteza          U_t: indicador de incerteza conhecido no fechamento de t
    ptax               s_t: dólar à vista no fim de t
    contrato, futuro   f_t: DOL que liquida na PTAX de t + 3, preço de ajuste em t (R$/US$)
    ptax_liquidacao    s_t+3: PTAX de fim de t + 3, o dólar que de fato ocorreu

    H_exportador       ln(f_t / s_t+3)  ganho do hedge de quem VENDE dólar futuro (Fama)
    H_importador       ln(s_t+3 / f_t)  ganho do hedge de quem COMPRA dólar futuro = -H_exportador
    resultado          H do lado da empresa (config.LADO_EMPRESA)
    hedge_compensou    True se o hedge deixou a empresa melhor do que sem hedge

    custo_sem_hedge    R$ pagos sem hedge:  N x s_t+3     (importador)
    custo_com_hedge    R$ pagos com hedge:  N x f_t       (conhecido já em t)
    resultado_reais    custo_sem_hedge - custo_com_hedge  (> 0: o hedge economizou)
"""

import numpy as np
import pandas as pd

from . import config


def montar_base(incerteza, ptax, futuro, horizonte=config.HORIZONTE_HEDGE,
                lado=config.LADO_EMPRESA, exposicao=config.EXPOSICAO_USD,
                ptax_liquidacao=None):
    """
    ptax_liquidacao: PTAX do dia exato em que cada contrato liquida (Series por
    mês t). Se não for passada, usa a PTAX de fim do mês t + horizonte.
    """
    if lado not in ("importador", "exportador"):
        raise ValueError(f"lado deve ser 'importador' ou 'exportador', não {lado!r}")

    base = pd.concat(
        [incerteza.rename("incerteza"), ptax.rename("ptax"), futuro],
        axis=1,
    ).sort_index()
    base.index.name = "mes"
    if ptax_liquidacao is None:
        base["ptax_liquidacao"] = base["ptax"].shift(-horizonte)
    else:
        base["ptax_liquidacao"] = ptax_liquidacao.reindex(base.index)

    # Passo 6: resultado do hedge em log (variável de Fama com horizonte t + 3)
    base["H_exportador"] = np.log(base["futuro"] / base["ptax_liquidacao"])
    base["H_importador"] = -base["H_exportador"]
    base["resultado"] = base[f"H_{lado}"]
    base["hedge_compensou"] = (base["resultado"] > 0).where(base["resultado"].notna())

    # Mesmo resultado em reais, para uma empresa com exposição de N dólares
    sinal = 1 if lado == "importador" else -1
    base["custo_sem_hedge"] = exposicao * base["ptax_liquidacao"]
    base["custo_com_hedge"] = exposicao * base["futuro"]
    base["resultado_reais"] = sinal * (base["custo_sem_hedge"] - base["custo_com_hedge"])
    if lado == "exportador":
        base = base.rename(columns={"custo_sem_hedge": "receita_sem_hedge",
                                    "custo_com_hedge": "receita_com_hedge"})

    # Regime de incerteza (conhecido em t)
    base["incerteza_alta"] = (base["incerteza"] > config.LIMIAR_INCERTEZA).where(
        base["incerteza"].notna())

    colunas = ["incerteza", "incerteza_alta", "ptax", "contrato", "futuro",
               "data_liquidacao", "ptax_liquidacao",
               "H_importador", "H_exportador", "resultado", "hedge_compensou",
               "custo_sem_hedge", "custo_com_hedge", "receita_sem_hedge", "receita_com_hedge",
               "resultado_reais", "data", "contratos_abertos", "negocios"]
    colunas = [c for c in colunas if c in base.columns]
    # Só os meses em que existe preço do futuro
    return base.dropna(subset=["futuro"])[colunas].rename(columns={"data": "data_pregao"})


def checar_convergencia(dol, ptax):
    """
    Validação: no último pregão do mês, o contrato que vence no dia útil
    seguinte tem ajuste igual à PTAX daquele dia. Devolve a maior diferença.
    """
    from .cambio import serie_futuro  # import local evita ciclo

    vencendo = serie_futuro(dol, horizonte=0)["futuro"]
    dif = (vencendo - ptax.reindex(vencendo.index)).abs().dropna()
    return dif.max(), len(dif)