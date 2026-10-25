"""
Testes do módulo de câmbio, com um arquivo da B3 sintético no mesmo formato
do real (zip dentro de zip, XML BVBG.086 com namespaces).
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incerteza import base_hedge, cambio  # noqa: E402

BLOCO = """<BizGrp><Document xmlns="urn:bvmf.217.01.xsd"><PricRpt>
  <TradDt><Dt>{data}</Dt></TradDt>
  <SctyId><TckrSymb>{ticker}</TckrSymb></SctyId>
  <FinInstrmId><OthrId><Id>100000084102</Id></OthrId></FinInstrmId>
  <TradDtls><TradQty>53475</TradQty></TradDtls>
  <FinInstrmAttrbts>
    <OpnIntrst>399375</OpnIntrst>
    <LastPric Ccy="BRL">3195.5</LastPric>
    <AdjstdQt Ccy="BRL">{ajuste}</AdjstdQt>
  </FinInstrmAttrbts>
</PricRpt></Document></BizGrp>"""


def arquivo_b3(data, contratos):
    """Monta um PRaammdd.zip sintético. contratos: {ticker: ajuste}."""
    # Inclui uma opção de dólar (ticker longo), que NÃO deve entrar
    contratos = {**contratos, "DOLH18C004200": 1.0}
    blocos = "".join(BLOCO.format(data=data, ticker=t, ajuste=a) for t, a in contratos.items())
    xml = ('<?xml version="1.0" encoding="utf-8"?>'
           f'<Document xmlns="urn:bvmf.052.01.xsd"><BizFileHdr><Xchg>{blocos}'
           "</Xchg></BizFileHdr></Document>")

    interno = io.BytesIO()
    with zipfile.ZipFile(interno, "w") as z:
        z.writestr("BVBG.086.01_BV0001.xml", "<Raiz/>")  # versão antiga, ignorada
        z.writestr("BVBG.086.01_BV0002.xml", xml)
    externo = io.BytesIO()
    with zipfile.ZipFile(externo, "w") as z:
        z.writestr("PR180131.zip", interno.getvalue())
    return externo.getvalue()


def test_ptax_e_pedida_em_blocos_de_no_maximo_10_anos():
    blocos = list(cambio._blocos_de_anos("2000-01-01"))
    assert blocos[0] == ("01/01/2000", "31/12/2004")
    assert blocos[1][0] == "01/01/2005"
    for ini, fim in blocos:
        anos = (pd.to_datetime(fim, dayfirst=True) - pd.to_datetime(ini, dayfirst=True)).days / 365
        assert anos < 10


def test_codigos_de_vencimento():
    assert cambio.codigo_contrato(pd.Period("2018-05", "M")) == "DOLK18"
    assert cambio.vencimento_do_codigo("DOLZ26") == pd.Period("2026-12", "M")


def test_contrato_que_liquida_na_ptax_de_abril_e_o_de_maio():
    assert cambio.contrato_que_liquida_em(pd.Period("2018-04", "M")) == "DOLK18"
    assert cambio.contrato_que_liquida_em(pd.Period("2018-12", "M")) == "DOLF19"


def test_ler_dol_pega_so_futuros_da_versao_mais_recente():
    conteudo = arquivo_b3("2018-01-31", {"DOLG18": 3160.0, "DOLK18": 3196.971})
    df = cambio.ler_dol(conteudo)
    assert set(df["contrato"]) == {"DOLG18", "DOLK18"}
    assert df.loc[df["contrato"] == "DOLK18", "ajuste"].item() == pytest.approx(3196.971)
    assert df["contratos_abertos"].iloc[0] == 399375


def test_serie_futuro_escolhe_contrato_e_converte_para_reais_por_dolar():
    dol = pd.DataFrame({
        "data": ["2018-01-31"] * 3,
        "contrato": ["DOLG18", "DOLJ18", "DOLK18"],
        "ajuste": [3160.0, 3180.0, 3196.971],
        "contratos_abertos": [1, 1, 1],
        "negocios": [1, 1, 1],
        "mes": pd.Period("2018-01", "M"),
    })
    serie = cambio.serie_futuro(dol, horizonte=3)
    linha = serie.loc[pd.Period("2018-01", "M")]
    assert linha["contrato"] == "DOLK18"
    assert linha["futuro"] == pytest.approx(3.196971)
    # horizonte 0: o contrato que vence amanhã (fevereiro)
    assert cambio.serie_futuro(dol, horizonte=0)["contrato"].item() == "DOLG18"


def _base_simples(lado="importador"):
    meses = pd.period_range("2018-01", periods=5, freq="M")
    ptax = pd.Series([3.0, 3.1, 3.2, 3.3, 3.4], index=meses)
    incerteza = pd.Series(100.0, index=meses)
    futuro = pd.DataFrame({"contrato": ["DOLK18"], "futuro": [3.05]}, index=meses[:1])
    return base_hedge.montar_base(incerteza, ptax, futuro, horizonte=3,
                                  lado=lado, exposicao=1_000_000)


def test_montar_base_casa_futuro_com_ptax_tres_meses_depois():
    base = _base_simples()
    linha = base.loc[pd.Period("2018-01", "M")]
    assert linha["ptax_liquidacao"] == 3.3          # PTAX de abril
    assert len(base) == 1


def test_resultado_do_importador_quando_o_dolar_sobe_alem_do_futuro():
    # Travou a 3,05 e o dólar foi a 3,30: o hedge do importador ganhou
    linha = _base_simples("importador").iloc[0]
    assert linha["H_importador"] == pytest.approx(np.log(3.30 / 3.05))
    assert linha["H_exportador"] == pytest.approx(-linha["H_importador"])
    assert linha["resultado"] == linha["H_importador"]
    assert linha["hedge_compensou"]
    assert linha["custo_sem_hedge"] == pytest.approx(3_300_000)
    assert linha["custo_com_hedge"] == pytest.approx(3_050_000)
    assert linha["resultado_reais"] == pytest.approx(250_000)   # economizou R$ 250 mil


def test_exportador_e_o_espelho():
    linha = _base_simples("exportador").iloc[0]
    assert linha["resultado"] == pytest.approx(np.log(3.05 / 3.30))
    assert not linha["hedge_compensou"]
    assert linha["resultado_reais"] == pytest.approx(-250_000)
