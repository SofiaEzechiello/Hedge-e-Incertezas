"""
Trabalho de Derivativos e Riscos: hedge cambial e incerteza.

Pergunta: para uma empresa IMPORTADORA que faz hedge cambial todo mês,
o hedge compensa financeiramente? E compensa mais quando a incerteza está alta?

Passos:
    1. Série mensal de incerteza (EPU Brasil, de Baker, Bloom e Davis)
    2. Dólar futuro: ajuste de fim de mês do contrato que liquida em t + 3
       (planilha do Bernardo (em data/raw)
    3. PTAX: fechamento do mês e a do dia exato da liquidação (Banco Central)
    4. Base casada: futuro em t  x  PTAX efetiva em t + 3
    5. Resultado do hedge: ln(f_t / s_t+3) e o espelho do importador, em % e em R$
    6. Análise descritiva: incerteza alta x normal, por ano e nas crises
    7. Regressão: H_t = b0 + b1·U_t + b2·ln(F_t/S_t), com ADF e Newey-West

Uso:
    python main.py                  # roda tudo (usa o cache de data/raw)
    python main.py --atualizar      # baixa tudo de novo
    python main.py --ate 2024-12    # regressão só com hedges contratados até dez/2024

Saídas:
    data/processed/base_hedge.csv   <- a base do trabalho (um mês por linha)
    data/processed/cenarios.csv     <- com/sem hedge x incerteza alta/normal
    data/processed/por_ano.csv      <- resultado do hedge por ano
    data/processed/por_crise.csv    <- resultado do hedge nas crises e fora delas
    data/processed/regressao_*.csv  <- tabelas da regressão (passo 7)
    figuras/*.png
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Permite "import incerteza" sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from incerteza import analise, base_hedge, cambio, config, epu, graficos, regressao  # noqa: E402


def titulo(texto):
    print(f"\n{'=' * 60}\n{texto}\n{'=' * 60}")


# Passo 1: incerteza
def passo1_incerteza(atualizar):
    titulo("1. Série de incerteza (EPU Brasil, Baker, Bloom e Davis)")
    serie = epu.baixar_epu(forcar=atualizar)
    print(f"{len(serie)} meses, de {serie.index.min()} a {serie.index.max()}")
    return serie


# Passos 2 e 3: câmbio
def passo2_futuro(atualizar):
    if config.ARQUIVO_FUTUROS_PLANILHA.exists():
        # Planilha do Bernardo (2006+): não precisa baixar nada da B3
        titulo(f"2. Dólar futuro (planilha, contrato que liquida em {config.HORIZONTE_HEDGE} meses)")
        dol = None
        futuro = cambio.ler_futuros_planilha()
    else:
        titulo(f"2. Dólar futuro (B3, contrato que liquida em {config.HORIZONTE_HEDGE} meses)")
        dol = cambio.baixar_futuros_mensais(forcar=atualizar)
        futuro = cambio.serie_futuro(dol)
    print(f"{len(futuro)} meses, de {futuro.index.min()} a {futuro.index.max()}")
    print(futuro.head(3).to_string())
    return dol, futuro


def passo3_ptax(atualizar, dol, futuro):
    titulo("3. PTAX de fechamento do mês")
    ptax = cambio.baixar_ptax_mensal(forcar=atualizar)
    print(f"{len(ptax)} meses, de {ptax.index.min()} a {ptax.index.max()}")

    if dol is not None:
        maior_dif, n = base_hedge.checar_convergencia(dol, ptax)
        print(f"Validação: o contrato que vence no dia seguinte bate com a PTAX "
              f"em {n} meses (maior diferença: R$ {maior_dif:.4f})")

    ptax_liq = None
    if "data_liquidacao" in futuro.columns:
        ptax_diaria = cambio.baixar_ptax_diaria(forcar=atualizar)
        ptax_liq = cambio.ptax_na_liquidacao(futuro, ptax_diaria)
        print(f"PTAX do dia da liquidação encontrada em {ptax_liq.notna().sum()} de "
              f"{len(ptax_liq)} meses (os que faltam ainda não venceram)")
    return ptax, ptax_liq


# Passo 4: base casada
def passo4_base(incerteza, ptax, futuro, ptax_liq=None):
    titulo("4. Base casada: futuro em t x PTAX em t + 3")
    # Incerteza alta = acima do percentil escolhido, nos meses da amostra do hedge
    # (percentil da amostra inteira: não é uma regra ex ante)
    amostra = incerteza.reindex(futuro.index).dropna()
    config.LIMIAR_INCERTEZA = round(amostra.quantile(config.PERCENTIL_INCERTEZA_ALTA))
    print(f"Incerteza alta: índice acima de {config.LIMIAR_INCERTEZA} "
          f"(percentil {config.PERCENTIL_INCERTEZA_ALTA:.0%} da amostra)")
    base = base_hedge.montar_base(incerteza, ptax, futuro, ptax_liquidacao=ptax_liq)
    base["limiar_incerteza"] = config.LIMIAR_INCERTEZA
    base.to_csv(config.DADOS_PROCESSADOS / "base_hedge.csv")

    completos = base.dropna(subset=["ptax_liquidacao"])
    print(f"{len(base)} meses com futuro; {len(completos)} já com a PTAX do vencimento")
    colunas = ["incerteza", "ptax", "contrato", "futuro", "ptax_liquidacao", "resultado"]
    print(completos[colunas].tail(5).round(4).to_string())

    graficos.grafico_futuro_vs_spot(base, config.HORIZONTE_HEDGE, nome="4_futuro_vs_ptax.png")
    return base