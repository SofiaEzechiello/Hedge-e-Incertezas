"""
Componente textual: atas do COPOM -> índice de incerteza por ata e por mês.

Fluxo:
    listar_atas()  ->  baixar_atas()  ->  indice_texto()  ->  indice_texto_mensal()
"""

import html
import re
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
from pypdf import PdfReader

from . import config


# Download

def _get(url, tentativas=3, espera=2.0):
    """GET com timeout e algumas novas tentativas (a API do BCB às vezes oscila)."""
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, timeout=60)
            resposta.raise_for_status()
            return resposta
        except requests.RequestException:
            if tentativa == tentativas:
                raise
            time.sleep(espera * tentativa)


def listar_atas():
    """Catálogo de todas as reuniões do COPOM (número, data da reunião, data da ata)."""
    return pd.DataFrame(_get(config.URL_LISTA_ATAS).json()["conteudo"])


def _detalhe(nro):
    return _get(config.URL_DETALHE_ATA.format(nro)).json()["conteudo"][0]


def _texto_html(nro):
    """Atas até a 199 e a partir da 232: o texto vem direto no JSON."""
    return _detalhe(nro)["textoAta"]


def _texto_pdf(nro):
    """Atas 200 a 231: baixa o PDF num arquivo temporário e extrai o texto."""
    url_pdf = _detalhe(nro)["urlPdfAta"]
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / "ata.pdf"
        caminho.write_bytes(_get(url_pdf).content)
        leitor = PdfReader(caminho)
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)


def _baixar_texto(nro):
    if config.ATA_PDF_INICIO <= nro <= config.ATA_PDF_FIM:
        return _texto_pdf(nro)
    return _texto_html(nro)


def baixar_atas(forcar=False):
    """
    Devolve um DataFrame com o texto de todas as atas.

    Usa cache em data/raw/atas_copom.csv: na primeira vez baixa tudo (alguns
    minutos); nas próximas, só baixa as atas novas. Use forcar=True para
    baixar tudo de novo.
    """
    catalogo = listar_atas()

    if config.ARQUIVO_ATAS.exists() and not forcar:
        cache = pd.read_csv(config.ARQUIVO_ATAS)
    else:
        cache = pd.DataFrame(columns=["nroReuniao", "texto"])

    faltando = sorted(set(catalogo["nroReuniao"]) - set(cache["nroReuniao"]))
    if faltando:
        print(f"Baixando {len(faltando)} atas do COPOM...")
        novas = []
        for i, nro in enumerate(faltando, start=1):
            novas.append({"nroReuniao": nro, "texto": _baixar_texto(nro)})
            if i % 25 == 0 or i == len(faltando):
                print(f"  {i}/{len(faltando)}")
        cache = pd.concat([cache, pd.DataFrame(novas)], ignore_index=True)
        config.ARQUIVO_ATAS.parent.mkdir(parents=True, exist_ok=True)
        cache.to_csv(config.ARQUIVO_ATAS, index=False)

    return (
        catalogo
        .merge(cache, on="nroReuniao", how="inner")
        .sort_values("nroReuniao")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Do texto ao índice
# ---------------------------------------------------------------------------
def limpar_html(texto):
    """
    Remove tags HTML e converte entidades (&ccedil; -> ç, &nbsp; -> espaço).

    Sem isso, as atas antigas escrevem "infla&ccedil;&atilde;o" e o termo
    "inflação" nunca é encontrado; e as tags entram na contagem de palavras.
    """
    sem_tags = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html.unescape(sem_tags)).strip()


def densidade(texto, regex):
    """Ocorrências dos termos dividido pelo total de palavras da ata."""
    palavras = len(texto.split())
    if palavras == 0:
        return float("nan")
    return len(re.findall(regex, texto.lower())) / palavras


def indice_texto(df_atas, opcoes):
    """
    Índice textual de cada ata = densidade(incerteza) x densidade(economia).

    Multiplicar (em vez de somar) faz o índice só ser alto quando os dois
    temas aparecem juntos: risco econômico, não risco em abstrato.
    """
    textos = df_atas["texto"].fillna("").astype(str)
    if opcoes.limpar_html:
        textos = textos.apply(limpar_html)

    return df_atas.assign(
        dens_inc=textos.apply(lambda t: densidade(t, config.TERMOS_INCERTEZA)),
        dens_eco=textos.apply(lambda t: densidade(t, config.TERMOS_ECONOMIA)),
    ).assign(
        indice_copom=lambda d: d["dens_inc"] * d["dens_eco"],
    )[["nroReuniao", "dataReferencia", "dataPublicacao", "dens_inc", "dens_eco", "indice_copom"]]


def indice_texto_mensal(df_indice, coluna_data="dataPublicacao"):
    """
    Passa o índice por ata para frequência mensal (PeriodIndex).

    Usa a data de PUBLICAÇÃO da ata (cerca de 6 dias depois da reunião): uma
    reunião no fim do mês só tem a ata conhecida no mês seguinte. Assim o
    índice do mês t só usa informação disponível no fechamento de t.

    Se houver duas atas no mesmo mês, fica a média. Os meses sem ata são
    preenchidos depois, na consolidação (ffill).
    """
    return (
        df_indice
        .assign(mes=lambda d: pd.to_datetime(d[coluna_data]).dt.to_period("M"))
        .groupby("mes")["indice_copom"]
        .mean()
        .rename("texto")
    )
