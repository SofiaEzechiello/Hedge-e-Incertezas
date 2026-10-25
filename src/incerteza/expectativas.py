"""
Componente de expectativas: dispersão das projeções do Focus (IPCA, câmbio, Selic).

Fluxo:
    baixar_expectativas()  ->  series_mensais()  ->  indice_expectativas()
"""

import io
from urllib.parse import quote

import pandas as pd
import requests

from . import config

# Cada série: endpoint da API Olinda, filtro OData e colunas que interessam.
SERIES = {
    "ipca": {
        "endpoint": "ExpectativasMercadoInflacao12Meses",
        "filtro": "Indicador eq 'IPCA' and Suavizada eq 'S' and baseCalculo eq 0",
        "colunas": "Data,Mediana,DesvioPadrao",
    },
    "cambio": {
        "endpoint": "ExpectativaMercadoMensais",
        "filtro": "Indicador eq 'Câmbio' and baseCalculo eq 0",
        "colunas": "Data,DataReferencia,Mediana,DesvioPadrao",
    },
    "selic": {
        "endpoint": "ExpectativasMercadoSelic",
        "filtro": "baseCalculo eq 0",
        "colunas": "Data,Reuniao,Mediana,DesvioPadrao",
    },
}


# Download (com cache em data/raw/focus_<serie>.csv)
def url_focus(nome):
    """
    Monta a URL da API Olinda com os espaços codificados como %20.

    Atenção: não usar requests.get(url, params=...), porque ele codifica os
    espaços como "+", e a API devolve erro 400 ("types not compatible").
    """
    spec = SERIES[nome]
    params = {"$filter": spec["filtro"], "$select": spec["colunas"], "$format": "text/csv"}
    seguros = "!*'()"  # mesmos caracteres que o navegador deixa sem codificar
    query = "&".join(k + "=" + quote(v, safe=seguros) for k, v in params.items())
    return config.URL_OLINDA + spec["endpoint"] + "?" + query


def ler_csv_focus(texto):
    """CSV da Olinda: separador vírgula, decimais com vírgula entre aspas ("4,51")."""
    return pd.read_csv(io.StringIO(texto), decimal=",", parse_dates=["Data"])


def _baixar_serie(nome, forcar=False):
    arquivo = config.DADOS_BRUTOS / f"focus_{nome}.csv"
    if arquivo.exists() and not forcar:
        return pd.read_csv(arquivo, parse_dates=["Data"])

    print(f"Baixando expectativas de {nome}...")
    resposta = requests.get(url_focus(nome), timeout=300)
    resposta.raise_for_status()
    df = ler_csv_focus(resposta.text)

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(arquivo, index=False)
    return df


def baixar_expectativas(forcar=False):
    """Dicionário {nome: DataFrame bruto} para IPCA, câmbio e Selic."""
    return {nome: _baixar_serie(nome, forcar) for nome in SERIES}


# Escolha de uma observação por mês
def _distancia_dia_coleta(df):
    """Adiciona o mês da coleta e a distância (em dias) até o dia 15 desse mês."""
    mes = df["Data"].dt.to_period("M")
    alvo = mes.dt.to_timestamp() + pd.Timedelta(days=config.DIA_COLETA - 1)
    return df.assign(mes=mes, distancia=(df["Data"] - alvo).abs())


def _coleta_mais_proxima(df):
    """Mantém TODAS as linhas da data de coleta mais próxima do dia 15 de cada mês."""
    df = _distancia_dia_coleta(df)
    melhor_data = df.loc[df.groupby("mes")["distancia"].idxmin(), ["mes", "Data"]]
    return df.merge(melhor_data, on=["mes", "Data"])


def _data_aprox_reuniao(reuniao):
    """'R6/2028' -> data aproximada da 6ª reunião de 2028 (8 reuniões por ano)."""
    partes = reuniao.str.extract(r"R(\d+)/(\d{4})").astype(int)
    numero, ano = partes[0], partes[1]
    dias = ((numero - 0.5) * 365 / 8).round().astype(int)
    return pd.to_datetime(ano.astype(str) + "-01-01") + pd.to_timedelta(dias, unit="D")


def _escolher_horizonte(df, data_alvo):
    """Em cada mês, fica a linha cujo horizonte é o mais próximo de 12 meses à frente."""
    alvo = df["Data"] + pd.DateOffset(months=config.HORIZONTE_MESES)
    df = df.assign(erro_horizonte=(data_alvo - alvo).abs())
    return df.loc[df.groupby("mes")["erro_horizonte"].idxmin()]


def _mensal_corrigido(nome, df):
    df = _coleta_mais_proxima(df)
    if nome == "cambio":
        referencia = pd.to_datetime(df["DataReferencia"], format="%m/%Y")
        df = _escolher_horizonte(df, referencia)
    elif nome == "selic":
        df = _escolher_horizonte(df, _data_aprox_reuniao(df["Reuniao"]))
    return df.set_index("mes")[["Mediana", "DesvioPadrao"]].sort_index()


def _mensal_original(nome, df):
    """
    Reproduz a seleção do notebook original.

    Atenção: no câmbio, o primeiro .first() já deixa uma linha por mês, então o
    passo que deveria escolher o horizonte de 12 meses não tem efeito; e na
    Selic, "R6/2028" vira só 2028, então a reunião escolhida dentro do ano é
    arbitrária. É por isso que o modo corrigido existe.
    """
    df = _distancia_dia_coleta(df)
    if nome == "cambio":
        df = (
            df.assign(DataReferencia=pd.to_datetime(df["DataReferencia"], format="%m/%Y"))
            .sort_values("distancia")
            .groupby("mes", as_index=False).first()
            .assign(diff=lambda x: x["DataReferencia"] - x["Data"])
            .sort_values("diff")
            .groupby("mes", as_index=False).last()
        )
    else:
        if nome == "selic":
            ano = df["Reuniao"].str.replace(r"^R\d/", "", regex=True).astype(int)
            df = df[ano == ano.groupby(df["mes"]).transform("max")]
        df = df.sort_values("distancia").groupby("mes", as_index=False).first()
    return df.set_index("mes")[["Mediana", "DesvioPadrao"]].sort_index()


def series_mensais(brutos, opcoes):
    """Uma linha por mês com mediana e desvio-padrão de cada variável."""
    seletor = _mensal_corrigido if opcoes.horizonte_fixo else _mensal_original
    partes = []
    for nome, df in brutos.items():
        mensal = seletor(nome, df)
        mensal.columns = [f"{nome}_mediana", f"{nome}_desvio"]
        partes.append(mensal)
    return pd.concat(partes, axis=1).sort_index()


# Dispersão -> índice de expectativas
def indice_expectativas(mensal, opcoes):
    """
    Coeficiente de variação (desvio / média) de cada variável, e a média dos três.

    - "temporal" (original): CV da MEDIANA numa janela móvel de 12 meses.
      Mede o quanto o consenso oscilou ao longo do ano.
    - "entre_analistas" (corrigido): DesvioPadrao / Mediana de cada coleta.
      Mede o quanto os analistas DISCORDAM entre si naquele mês, que é o
      conceito do IIE-Br Expectativa.
    """
    variaveis = list(SERIES)
    medianas = mensal[[f"{v}_mediana" for v in variaveis]].set_axis(variaveis, axis=1)

    if opcoes.dispersao == "temporal":
        janela = config.JANELA_CV_MESES
        cv = medianas.rolling(janela).std() / medianas.rolling(janela).mean()
    elif opcoes.dispersao == "entre_analistas":
        desvios = mensal[[f"{v}_desvio" for v in variaveis]].set_axis(variaveis, axis=1)
        cv = desvios / medianas.abs()
    else:
        raise ValueError(f"dispersao desconhecida: {opcoes.dispersao}")

    return cv.add_prefix("cv_").assign(expectativas=lambda d: d.mean(axis=1))
