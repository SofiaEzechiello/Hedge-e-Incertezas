"""Testes da análise descritiva (passo 6) com dados simulados."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incerteza import analise, base_hedge  # noqa: E402


def base_simulada(beta_imp, lado="importador", n=300, semente=0):
    """
    Simula futuro e PTAX tais que o resultado do importador seja
    H = 0,01 + beta_imp·(U - 100) + ruído.
    """
    rng = np.random.default_rng(semente)
    meses = pd.period_range("2000-01", periods=n + 3, freq="M")
    incerteza = pd.Series(100 + 10 * rng.standard_normal(n + 3), index=meses)
    ptax = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.03, n + 3))) * 3, index=meses)

    s_venc = ptax.shift(-3).iloc[:n]
    H_imp = 0.01 + beta_imp * (incerteza.iloc[:n] - 100) + rng.normal(0, 0.02, n)
    futuro = pd.DataFrame({"contrato": "DOLX", "futuro": s_venc / np.exp(H_imp)})
    return base_hedge.montar_base(incerteza, ptax, futuro, lado=lado)


def test_cenarios_somam_certo():
    base = base_simulada(0.002)
    cen = analise.cenarios(base)
    assert set(cen.index) == {"Incerteza alta", "Incerteza normal", "Total"}
    assert cen.loc["Total", "meses"] == 300
    partes = cen.drop("Total")
    assert partes["ganho_do_hedge_R$"].sum() == pytest.approx(cen.loc["Total", "ganho_do_hedge_R$"])
    total = cen.loc["Total"]
    # ganho do hedge = o que pagaria sem hedge - o que pagou com hedge
    assert total["ganho_do_hedge_R$"] == pytest.approx(total["sem_hedge_R$"] - total["com_hedge_R$"])
    # com β > 0, o hedge do importador rende mais com incerteza alta
    assert cen.loc["Incerteza alta", "resultado_medio_%"] > cen.loc["Incerteza normal", "resultado_medio_%"]


def test_ultimos_meses_sem_vencimento_ficam_fora_da_analise():
    meses = pd.period_range("2018-01", periods=6, freq="M")
    ptax = pd.Series(3.0, index=meses)
    incerteza = pd.Series(100.0, index=meses)
    futuro = pd.DataFrame({"contrato": "DOLX", "futuro": 3.0}, index=meses)  # todos os meses
    base = base_hedge.montar_base(incerteza, ptax, futuro)
    assert len(base) == 6
    assert len(analise.amostra_completa(base)) == 3   # os 3 últimos ainda não venceram