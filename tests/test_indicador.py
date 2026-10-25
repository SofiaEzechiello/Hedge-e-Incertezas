"""
Testes com dados sintéticos (não precisam de internet).

Rode com:  python -m pytest
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incerteza import config, copom, expectativas, indicador  # noqa: E402


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def test_limpar_html_converte_entidades():
    bruto = "<p>A infla&ccedil;&atilde;o e o <b>risco</b>&nbsp;fiscal</p>"
    assert copom.limpar_html(bruto) == "A inflação e o risco fiscal"


def test_sem_limpeza_termo_com_acento_nao_e_encontrado():
    bruto = "<p>infla&ccedil;&atilde;o alta</p>"
    assert copom.densidade(bruto, config.TERMOS_ECONOMIA) == 0
    assert copom.densidade(copom.limpar_html(bruto), config.TERMOS_ECONOMIA) > 0


def test_densidade_conta_por_palavra():
    texto = "risco risco inflação juros calma calma calma calma calma calma"
    assert copom.densidade(texto, config.TERMOS_INCERTEZA) == pytest.approx(2 / 10)
    assert copom.densidade(texto, config.TERMOS_ECONOMIA) == pytest.approx(2 / 10)


def test_indice_mensal_media_de_atas_no_mesmo_mes():
    df = pd.DataFrame({
        "dataPublicacao": ["2020-03-05", "2020-03-20", "2020-05-10"],
        "indice_copom": [1.0, 3.0, 5.0],
    })
    mensal = copom.indice_texto_mensal(df)
    assert mensal[pd.Period("2020-03", "M")] == 2.0
    assert len(mensal) == 2


def test_ata_de_reuniao_no_fim_do_mes_conta_no_mes_da_publicacao():
    df = pd.DataFrame({
        "dataReferencia": ["2020-03-31"],
        "dataPublicacao": ["2020-04-06"],
        "indice_copom": [1.0],
    })
    assert copom.indice_texto_mensal(df).index[0] == pd.Period("2020-04", "M")


# ---------------------------------------------------------------------------
# Expectativas
# ---------------------------------------------------------------------------
def _focus_cambio():
    """Duas coletas em mar/2020, cada uma com vários horizontes."""
    linhas = []
    for data in ["2020-03-06", "2020-03-13"]:
        for ref, mediana in [("04/2020", 4.5), ("03/2021", 4.8), ("12/2022", 5.0)]:
            linhas.append({"Data": pd.Timestamp(data), "DataReferencia": ref,
                           "Mediana": mediana, "DesvioPadrao": 0.2})
    return pd.DataFrame(linhas)


def test_cambio_corrigido_pega_coleta_do_dia15_e_horizonte_12m():
    mensal = expectativas._mensal_corrigido("cambio", _focus_cambio())
    linha = mensal.loc[pd.Period("2020-03", "M")]
    assert linha["Mediana"] == 4.8  # 03/2021 = 12 meses à frente


def test_data_aproximada_da_reuniao():
    datas = expectativas._data_aprox_reuniao(pd.Series(["R1/2021", "R8/2021"]))
    assert datas.iloc[0].month == 1
    assert datas.iloc[1].month == 12


def test_dispersao_entre_analistas_e_desvio_sobre_mediana():
    idx = pd.period_range("2020-01", periods=2, freq="M")
    mensal = pd.DataFrame({
        "ipca_mediana": [4.0, 4.0], "ipca_desvio": [0.4, 0.8],
        "cambio_mediana": [5.0, 5.0], "cambio_desvio": [0.5, 0.5],
        "selic_mediana": [2.0, 2.0], "selic_desvio": [0.2, 0.2],
    }, index=idx)
    res = expectativas.indice_expectativas(mensal, config.CORRIGIDO)
    assert res["cv_ipca"].tolist() == pytest.approx([0.1, 0.2])
    assert res["expectativas"].iloc[0] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------
def test_padronizar_tem_media_100_e_desvio_10_na_janela():
    idx = pd.period_range("2004-01", "2020-12", freq="M")
    serie = pd.Series(np.random.default_rng(0).normal(5, 2, len(idx)), index=idx)
    p = indicador.padronizar(serie, 100, 10)
    janela = p["2006-01":"2015-12"]
    assert janela.mean() == pytest.approx(100)
    assert janela.std() == pytest.approx(10)


def _componentes_sinteticos():
    idx = pd.period_range("2004-01", "2020-12", freq="M")
    rng = np.random.default_rng(1)
    texto = pd.Series(rng.normal(2e-4, 5e-5, len(idx)), index=idx, name="texto")
    exp = pd.DataFrame({"expectativas": rng.normal(0.05, 0.01, len(idx))}, index=idx)
    return texto, exp


def test_modo_original_texto_quase_nao_pesa():
    texto, exp = _componentes_sinteticos()
    res = indicador.consolidar(texto, exp, config.ORIGINAL)
    assert indicador.contribuicao_texto(res) < 0.01


def test_modo_corrigido_texto_pesa_o_que_os_pesos_dizem():
    texto, exp = _componentes_sinteticos()
    res = indicador.consolidar(texto, exp, config.CORRIGIDO)
    # componentes independentes e com variância 1: 0,8² / (0,8² + 0,2²) ≈ 94%
    assert indicador.contribuicao_texto(res) == pytest.approx(0.94, abs=0.05)
    assert res["iiebr"]["2006-01":"2015-12"].mean() == pytest.approx(100)
