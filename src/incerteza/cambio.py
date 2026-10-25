"""
Câmbio: PTAX de fim de mês (Banco Central) e dólar futuro DOL (B3).

Fluxo:
    baixar_ptax_mensal()     -> PTAX venda do último dia útil de cada mês
    baixar_futuros_mensais() -> ajuste de todos os contratos DOL no último pregão de cada mês
    serie_futuro()           -> em cada mês, o contrato que liquida na PTAX de t + horizonte
"""

import io
import re
import time
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
import requests

from . import config

CODIGO_MES = "FGHJKMNQUVXZ"  # F = jan, G = fev, ..., Z = dez
PADRAO_DOL = re.compile(r"^DOL([FGHJKMNQUVXZ])(\d{2})$")
CABECALHO = {"User-Agent": "Mozilla/5.0 (trabalho academico UFRGS)"}


# ---------------------------------------------------------------------------
# Códigos de vencimento
# ---------------------------------------------------------------------------
def codigo_contrato(vencimento):
    """Period('2018-05') -> 'DOLK18'."""
    return f"DOL{CODIGO_MES[vencimento.month - 1]}{vencimento.year % 100:02d}"


def vencimento_do_codigo(ticker):
    """'DOLK18' -> Period('2018-05')."""
    letra, ano = PADRAO_DOL.match(ticker).groups()
    return pd.Period(year=2000 + int(ano), month=CODIGO_MES.index(letra) + 1, freq="M")


def contrato_que_liquida_em(mes_liquidacao):
    """
    O DOL vence no 1º dia útil do mês de vencimento e paga a PTAX do último
    dia útil do mês anterior. Logo, para liquidar na PTAX de fim de abril,
    o contrato é o de maio.
    """
    return codigo_contrato(mes_liquidacao + 1)


# ---------------------------------------------------------------------------
# PTAX
# ---------------------------------------------------------------------------
def _blocos_de_anos(inicio="2000-01-01", anos=5):
    """
    A API do SGS recusa consultas com mais de 10 anos (erro 502 ou
    "Requisição inválida"), então o período é pedido em blocos de 5 anos.
    """
    hoje = pd.Timestamp.today().normalize()
    ini = pd.Timestamp(inicio)
    while ini <= hoje:
        fim = min(ini + pd.DateOffset(years=anos) - pd.Timedelta(days=1), hoje)
        yield ini.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")
        ini = fim + pd.Timedelta(days=1)


def _sgs(codigo, inicio, fim):
    url = config.URL_SGS.format(codigo, inicio, fim)
    for tentativa in range(1, 4):
        try:
            resposta = requests.get(url, timeout=60)
            resposta.raise_for_status()
            return resposta.json()
        except requests.RequestException:
            if tentativa == 3:
                raise
            time.sleep(3 * tentativa)


def baixar_ptax_mensal(forcar=False):
    """PTAX venda de fim de mês (SGS 3696), como Series com PeriodIndex mensal."""
    arquivo = config.DADOS_BRUTOS / "ptax_mensal.csv"
    if arquivo.exists() and not forcar:
        df = pd.read_csv(arquivo)
    else:
        print("Baixando PTAX mensal...")
        df = pd.concat(
            [pd.DataFrame(_sgs(config.SGS_PTAX_MENSAL, ini, fim)) for ini, fim in _blocos_de_anos()],
            ignore_index=True,
        ).drop_duplicates("data")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(arquivo, index=False)

    datas = pd.to_datetime(df["data"], format="%d/%m/%Y")
    return pd.Series(df["valor"].astype(float).to_numpy(),
                     index=datas.dt.to_period("M"), name="ptax").sort_index()


# ---------------------------------------------------------------------------
# Dólar futuro (arquivo de preços da B3)
# ---------------------------------------------------------------------------
def _baixar_arquivo_b3(data):
    """Baixa o arquivo de preços do pregão. Devolve None se não houve pregão."""
    url = config.URL_B3_PRECOS.format(data.strftime("%y%m%d"))
    for tentativa in range(1, 4):
        try:
            resposta = requests.get(url, headers=CABECALHO, timeout=120)
            resposta.raise_for_status()
            break
        except requests.RequestException:
            if tentativa == 3:
                raise
            time.sleep(3 * tentativa)
    # Dia sem pregão (feriado/fim de semana) devolve um zip vazio de ~22 bytes
    return resposta.content if len(resposta.content) > 1000 else None


def ler_dol(conteudo_zip):
    """
    Extrai os contratos futuros de dólar (DOLxNN) de um arquivo PR da B3.

    O arquivo é um zip com outro zip dentro, que traz um ou mais XML
    (versões do mesmo relatório); usamos o mais recente, como o rb3.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as externo:
        interno_nome = next((n for n in externo.namelist() if n.lower().endswith(".zip")), None)
        if interno_nome:
            arquivos = zipfile.ZipFile(io.BytesIO(externo.read(interno_nome)))
        else:
            arquivos = externo
        xml_nome = sorted(n for n in arquivos.namelist() if n.lower().endswith(".xml"))[-1]
        xml = arquivos.read(xml_nome)

    linhas = []
    for _, elem in ET.iterparse(io.BytesIO(xml), events=("end",)):
        if elem.tag.rsplit("}", 1)[-1] != "PricRpt":
            continue
        campos = {filho.tag.rsplit("}", 1)[-1]: filho.text for filho in elem.iter()}
        ticker = (campos.get("TckrSymb") or "").strip()
        if PADRAO_DOL.match(ticker) and campos.get("AdjstdQt"):
            linhas.append({
                "data": campos.get("Dt"),
                "contrato": ticker,
                "ajuste": float(campos["AdjstdQt"]),
                "contratos_abertos": float(campos.get("OpnIntrst") or 0),
                "negocios": float(campos.get("TradQty") or 0),
            })
        elem.clear()
    return pd.DataFrame(linhas)


def _ultimo_pregao_do_mes(mes):
    """Procura, do último dia do mês para trás, o primeiro dia com arquivo da B3."""
    dia = mes.to_timestamp(how="end").normalize()
    for _ in range(10):
        if dia.weekday() < 5:
            conteudo = _baixar_arquivo_b3(dia)
            if conteudo is not None:
                return dia, conteudo
        dia -= pd.Timedelta(days=1)
    raise RuntimeError(f"Não achei pregão no fim de {mes}.")


def baixar_futuros_mensais(inicio=config.INICIO_FUTUROS, forcar=False):
    """
    Ajuste de todos os contratos DOL no último pregão de cada mês.

    Cache: um CSV pequeno por mês em data/raw/b3_dol/ (só as linhas do DOL).
    A primeira execução baixa um arquivo por mês desde 2018 (uns 10 minutos).
    """
    config.PASTA_FUTUROS.mkdir(parents=True, exist_ok=True)
    ultimo_mes_fechado = pd.Timestamp.today().to_period("M") - 1
    meses = pd.period_range(inicio, ultimo_mes_fechado, freq="M")

    partes = []
    for mes in meses:
        arquivo = config.PASTA_FUTUROS / f"DOL_{mes}.csv"
        if arquivo.exists() and not forcar:
            partes.append(pd.read_csv(arquivo))
            continue
        print(f"  B3: baixando fim de {mes}...")
        dia, conteudo = _ultimo_pregao_do_mes(mes)
        df = ler_dol(conteudo)
        df["data"] = dia.strftime("%Y-%m-%d")
        df.to_csv(arquivo, index=False)
        partes.append(df)

    dol = pd.concat(partes, ignore_index=True)
    dol["mes"] = pd.to_datetime(dol["data"]).dt.to_period("M")
    return dol


def serie_futuro(dol, horizonte=config.HORIZONTE_HEDGE):
    """
    Uma linha por mês t: o contrato que liquida na PTAX de fim de t + horizonte.

    O preço vem em R$ por US$ 1.000; dividimos para ficar em R$ por US$,
    na mesma unidade da PTAX.
    """
    alvo = dol["mes"].apply(lambda m: contrato_que_liquida_em(m + horizonte))
    escolhidos = dol[dol["contrato"] == alvo]
    return (
        escolhidos
        .assign(futuro=lambda d: d["ajuste"] / config.COTACAO_POR)
        .set_index("mes")[["data", "contrato", "futuro", "contratos_abertos", "negocios"]]
        .sort_index()
    )



# ---------------------------------------------------------------------------
# Planilha do Bernardo (2006 em diante) e PTAX do dia da liquidação
# ---------------------------------------------------------------------------
def ler_futuros_planilha(arquivo=config.ARQUIVO_FUTUROS_PLANILHA):
    """
    Lê a planilha do Bernardo: em cada fim de mês t, o preço de ajuste do DOL
    que vence em t + 4 e liquida pela PTAX de fim de t + 3 (coluna data_liquidacao).
    Devolve no mesmo formato de serie_futuro(), com o preço em R$ por US$.
    """
    df = pd.read_excel(arquivo)
    data_ref = pd.to_datetime(df["data_referencia"])
    return (
        pd.DataFrame({
            "mes": data_ref.dt.to_period("M"),
            "data": data_ref.dt.strftime("%Y-%m-%d"),
            "contrato": df["contrato"],
            "futuro": df["preco_ajuste"] / config.COTACAO_POR,
            "data_liquidacao": pd.to_datetime(df["data_liquidacao"]),
            "contratos_abertos": df["contratos_em_aberto"],
        })
        .set_index("mes")
        .sort_index()
    )


def baixar_ptax_diaria(inicio="2006-01-01", forcar=False):
    """PTAX venda diária (SGS 1), como Series indexada pela data."""
    arquivo = config.DADOS_BRUTOS / "ptax_diaria.csv"
    if arquivo.exists() and not forcar:
        df = pd.read_csv(arquivo)
    else:
        print("Baixando PTAX diária...")
        df = pd.concat(
            [pd.DataFrame(_sgs(config.SGS_PTAX_DIARIA, ini, fim))
             for ini, fim in _blocos_de_anos(inicio)],
            ignore_index=True,
        ).drop_duplicates("data")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(arquivo, index=False)

    datas = pd.to_datetime(df["data"], format="%d/%m/%Y")
    return pd.Series(df["valor"].astype(float).to_numpy(), index=datas, name="ptax").sort_index()




# ---------------------------------------------------------------------------
# Planilha do Bernardo (2006 em diante) e PTAX do dia da liquidação
# ---------------------------------------------------------------------------
def ler_futuros_planilha(arquivo=config.ARQUIVO_FUTUROS_PLANILHA):
    """
    Lê a planilha do Bernardo: em cada fim de mês t, o preço de ajuste do DOL
    que vence em t + 4 e liquida pela PTAX de fim de t + 3 (coluna data_liquidacao).
    Devolve no mesmo formato de serie_futuro(), com o preço em R$ por US$.
    """
    df = pd.read_excel(arquivo)
    data_ref = pd.to_datetime(df["data_referencia"])
    return (
        pd.DataFrame({
            "mes": data_ref.dt.to_period("M"),
            "data": data_ref.dt.strftime("%Y-%m-%d"),
            "contrato": df["contrato"],
            "futuro": df["preco_ajuste"] / config.COTACAO_POR,
            "data_liquidacao": pd.to_datetime(df["data_liquidacao"]),
            "contratos_abertos": df["contratos_em_aberto"],
        })
        .set_index("mes")
        .sort_index()
    )


def baixar_ptax_diaria(inicio="2006-01-01", forcar=False):
    """PTAX venda diária (SGS 1), como Series indexada pela data."""
    arquivo = config.DADOS_BRUTOS / "ptax_diaria.csv"
    if arquivo.exists() and not forcar:
        df = pd.read_csv(arquivo)
    else:
        print("Baixando PTAX diária...")
        df = pd.concat(
            [pd.DataFrame(_sgs(config.SGS_PTAX_DIARIA, ini, fim))
             for ini, fim in _blocos_de_anos(inicio)],
            ignore_index=True,
        ).drop_duplicates("data")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(arquivo, index=False)

    datas = pd.to_datetime(df["data"], format="%d/%m/%Y")
    return pd.Series(df["valor"].astype(float).to_numpy(), index=datas, name="ptax").sort_index()


def ptax_na_liquidacao(futuro, ptax_diaria):
    """
    PTAX do dia em que cada contrato liquida (coluna data_liquidacao).

    Se não houver PTAX naquele dia (feriado), usa a do dia útil anterior, até
    5 dias para trás. Vencimentos que ainda não aconteceram ficam vazios.
    """
    datas = pd.DatetimeIndex(futuro["data_liquidacao"])
    valores = ptax_diaria.reindex(datas, method="ffill", tolerance=pd.Timedelta(days=5))
    valores[datas > ptax_diaria.index.max()] = float("nan")
    return pd.Series(valores.to_numpy(), index=futuro.index, name="ptax_liquidacao")