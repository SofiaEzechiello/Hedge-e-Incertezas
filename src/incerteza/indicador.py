"""
Consolidação: junta texto + expectativas na fórmula do IIE-Br e padroniza (base 100).
"""

import pandas as pd

from . import config


def padronizar(serie, media=0.0, desvio=1.0):
    """
    Reescala a série para ter a média e o desvio pedidos na janela de referência.

    Com os padrões (0 e 1) é um z-score; com (100, 10) é a escala do IIE-Br.
    """
    inicio, fim = (pd.Period(p, "M") for p in config.JANELA_REFERENCIA)
    janela = serie[(serie.index >= inicio) & (serie.index <= fim)]
    if janela.dropna().empty:
        raise ValueError("A série não tem dados na janela de referência (2006-2015).")
    z = (serie - janela.mean()) / janela.std()
    return media + desvio * z


def consolidar(texto_mensal, indice_exp, opcoes):
    """
    IIE-Br = 0,8 x componente textual + 0,2 x componente de expectativas.

    Modo original: soma o índice textual BRUTO (ordem de 0,0001) com as
    expectativas já em base 100 (ordem de 100). Como as escalas são tão
    diferentes, o texto praticamente some e o resultado final é quase só
    expectativas.

    Modo corrigido: põe os dois componentes na mesma escala (z-score na
    janela de referência) antes de ponderar, para que os pesos 0,8/0,2
    signifiquem de fato 80% e 20%.
    """
    base = (
        pd.concat([texto_mensal, indice_exp["expectativas"]], axis=1)
        .sort_index()
        .ffill()            # meses sem reunião do COPOM repetem a última ata
        .dropna()
    )
    # Meses completos de ponta a ponta (sem buracos no PeriodIndex)
    base = base.reindex(pd.period_range(base.index.min(), base.index.max(), freq="M")).ffill()

    if opcoes.padronizar_componentes:
        comp_texto = padronizar(base["texto"])
        comp_exp = padronizar(base["expectativas"])
    else:
        comp_texto = base["texto"]
        comp_exp = padronizar(base["expectativas"], config.MEDIA_BASE, config.DESVIO_BASE)

    bruto = config.PESO_TEXTO * comp_texto + config.PESO_EXPECTATIVAS * comp_exp

    return pd.DataFrame({
        "componente_texto": comp_texto,
        "componente_expectativas": comp_exp,
        "iiebr_bruto": bruto,
        "iiebr": padronizar(bruto, config.MEDIA_BASE, config.DESVIO_BASE),
    })


def contribuicao_texto(resultado):
    """
    Fração da variância do índice final explicada pela parte textual.

    Serve de diagnóstico: no modo original fica perto de 0 (o texto não pesa
    nada), no corrigido fica perto do que os pesos prometem.
    """
    parte_texto = config.PESO_TEXTO * resultado["componente_texto"]
    parte_exp = config.PESO_EXPECTATIVAS * resultado["componente_expectativas"]
    cov = pd.concat([parte_texto, parte_exp], axis=1).cov().to_numpy()
    total = cov.sum()
    return (cov[0, 0] + cov[0, 1]) / total


def ler_fgv():
    """Lê a série oficial do IIE-Br exportada do FGV Data, se o arquivo existir."""
    if not config.ARQUIVO_FGV.exists():
        return None
    fgv = pd.read_csv(
        config.ARQUIVO_FGV, sep=";", decimal=",",
        names=["Data", "FGV"], skiprows=1,
    )
    fgv.index = pd.to_datetime(fgv["Data"], format="%m/%Y").dt.to_period("M")
    return fgv["FGV"]


def comparar_com_fgv(iiebr, fgv):
    """Correlação com o índice oficial, em nível e em variação mensal."""
    dados = pd.concat([iiebr.rename("replica"), fgv], axis=1).dropna()
    return {
        "meses_em_comum": len(dados),
        "correlacao_nivel": dados["replica"].corr(dados["FGV"]),
        "correlacao_variacao": dados["replica"].diff().corr(dados["FGV"].diff()),
    }
