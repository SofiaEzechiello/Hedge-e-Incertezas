"""
Testes com recortes REAIS das APIs (baixados em out/2026 e salvos em tests/dados/).
Garantem que o código entende o formato de verdade, não só dados simulados.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incerteza import config, expectativas  # noqa: E402

DADOS = Path(__file__).parent / "dados"


def _focus():
    return {nome: expectativas.ler_csv_focus((DADOS / f"focus_{nome}.csv").read_text())
            for nome in ("ipca", "cambio", "selic")}


def test_url_igual_a_que_funcionou_no_navegador():
    # Esta URL devolveu status 200 na API Olinda; com "+" no lugar de %20 dá erro 400
    esperado = ("ExpectativasMercadoInflacao12Meses?$filter=Indicador%20eq%20'IPCA'%20and%20"
                "Suavizada%20eq%20'S'%20and%20baseCalculo%20eq%200&$select=Data%2CMediana%2C"
                "DesvioPadrao&$format=text%2Fcsv")
    assert expectativas.url_focus("ipca") == config.URL_OLINDA + esperado
    assert "C%C3%A2mbio" in expectativas.url_focus("cambio")
    assert "+" not in expectativas.url_focus("cambio")


def test_le_decimais_com_virgula():
    ipca = _focus()["ipca"]
    assert ipca["Mediana"].iloc[0] == pytest.approx(4.5146)
    assert pd.api.types.is_datetime64_any_dtype(ipca["Data"])


def test_selecao_mensal_corrigida_com_dados_reais():
    mensal = expectativas.series_mensais(_focus(), config.CORRIGIDO)
    out = mensal.loc[pd.Period("2026-10", "M")]
    # Coleta mais próxima do dia 15 = 15/10/2026
    assert out["ipca_mediana"] == pytest.approx(4.4997)
    # Câmbio: horizonte de 12 meses = 10/2027
    assert out["cambio_mediana"] == pytest.approx(5.2135)
    assert out["cambio_desvio"] == pytest.approx(0.1854)
    # Selic: reunião mais próxima de out/2027 = R7/2027
    assert out["selic_mediana"] == pytest.approx(12.0)
    assert out["selic_desvio"] == pytest.approx(0.755)


def test_modo_original_roda_com_dados_reais():
    mensal = expectativas.series_mensais(_focus(), config.ORIGINAL)
    assert pd.Period("2026-10", "M") in mensal.index
