"""
Índice de Incerteza de Política Econômica do Brasil (EPU), de Baker, Bloom e Davis.

Mensal, desde 1991, construído a partir de notícias da Folha de S.Paulo.
Fonte: www.PolicyUncertainty.com (uso livre, citando os autores e o site).
Referência: Baker, S., Bloom, N. e Davis, S. (2016). Measuring Economic Policy
Uncertainty. Quarterly Journal of Economics 131(4).
"""

import pandas as pd
import requests

from . import config


def baixar_epu(forcar=False):
    """EPU Brasil mensal, como Series com PeriodIndex. Guarda a planilha em data/raw."""
    arquivo = config.ARQUIVO_EPU
    if not arquivo.exists() or forcar:
        print("Baixando o EPU Brasil...")
        resposta = requests.get(config.URL_EPU, timeout=60,
                                headers={"User-Agent": "Mozilla/5.0 (trabalho academico UFRGS)"})
        resposta.raise_for_status()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(resposta.content)

    df = pd.read_excel(arquivo)
    df.columns = ["ano", "mes", "epu"]
    # lembrar que a última linha da planilha é uma nota de fonte, não um dado
    df = df[pd.to_numeric(df["mes"], errors="coerce").notna()]
    meses = pd.PeriodIndex(
        [pd.Period(year=int(a), month=int(m), freq="M") for a, m in zip(df["ano"], df["mes"])]
    )
    return pd.Series(df["epu"].astype(float).to_numpy(), index=meses, name="epu").sort_index()