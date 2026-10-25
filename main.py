"""
Trabalho de Derivativos e Riscos: hedge cambial e incerteza.

Pergunta: para uma empresa IMPORTADORA que faz hedge cambial todo mês,
o hedge compensa financeiramente? E compensa mais quando a incerteza está alta?

Passos:
    1. Série mensal de incerteza (réplica do IIE-Br com dados do Banco Central)
    2. Dólar futuro: ajuste de fim de mês do contrato que vence em 3 meses (B3)
    3. PTAX de fechamento do mês (Banco Central)
    4. Base casada: futuro em t  x  PTAX efetiva em t + 3
    5. Resultado do hedge: ln(f_t / s_t+3) e o espelho do importador, em % e em R$
    6. Análise: regressão do resultado na incerteza e cenários com/sem hedge

Uso:
    python main.py              # roda tudo (usa o cache de data/raw)
    python main.py --atualizar  # baixa tudo de novo

Saídas:
    data/processed/base_hedge.csv   <- a base do trabalho (um mês por linha)
    data/processed/regressoes.csv   <- α, β, erros-padrão de Newey-West, p-valores
    data/processed/cenarios.csv     <- com/sem hedge x incerteza alta/normal
    data/processed/iiebr_*.csv      <- o indicador de incerteza (original e corrigido)
    figuras/*.png
"""

import argparse
import sys
from pathlib import Path

# Permite "import incerteza" sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from incerteza import (  # noqa: E402
    analise, base_hedge, cambio, config, copom, expectativas, graficos, indicador,
)


def titulo(texto):
    print(f"\n{'=' * 60}\n{texto}\n{'=' * 60}")


# ---------------------------------------------------------------------------
# Passo 1: incerteza
# ---------------------------------------------------------------------------
def calcular_incerteza(modo, atas, focus):
    opcoes = config.MODOS[modo]
    texto_mensal = copom.indice_texto_mensal(copom.indice_texto(atas, opcoes))
    indice_exp = expectativas.indice_expectativas(
        expectativas.series_mensais(focus, opcoes), opcoes
    )
    resultado = indicador.consolidar(texto_mensal, indice_exp, opcoes)
    resultado.to_csv(config.DADOS_PROCESSADOS / f"iiebr_{modo}.csv", index_label="mes")
    return resultado


def passo1_incerteza(atualizar):
    titulo("1. Série de incerteza")
    atas = copom.baixar_atas(forcar=atualizar)
    focus = expectativas.baixar_expectativas(forcar=atualizar)
    resultados = {modo: calcular_incerteza(modo, atas, focus) for modo in config.MODOS}

    for modo, r in resultados.items():
        serie = r["iiebr"]
        print(f"[{modo}] {serie.index.min()} a {serie.index.max()}, "
              f"pico {serie.max():.1f} em {serie.idxmax()}, "
              f"peso efetivo do texto: {indicador.contribuicao_texto(r):.0%}")

    principal = resultados[config.MODO_TRABALHO]
    graficos.grafico_indicador(principal["iiebr"], "Indicador de incerteza da economia brasileira",
                               nome="1_incerteza.png")
    graficos.grafico_componentes(principal, nome="1_componentes_incerteza.png")
    graficos.grafico_comparacao(
        {"Notebook original": resultados["original"]["iiebr"],
         "Versão corrigida": resultados["corrigido"]["iiebr"]},
        "O que muda com as correções", nome="1_original_vs_corrigido.png",
    )

    fgv = indicador.ler_fgv()
    if fgv is not None:
        graficos.grafico_comparacao(
            {"Réplica": principal["iiebr"], "FGV (IIE-Br oficial)": fgv},
            "Réplica vs. IIE-Br oficial da FGV", nome="1_vs_fgv.png",
            fonte="Fontes: Banco Central e FGV IBRE (IIE-Br). Elaboração própria.",
        )
        stats = indicador.comparar_com_fgv(principal["iiebr"], fgv)
        print(f"vs FGV: corr. nível {stats['correlacao_nivel']:.2f}, "
              f"corr. variação {stats['correlacao_variacao']:.2f} ({stats['meses_em_comum']} meses)")

    return principal["iiebr"]


# ---------------------------------------------------------------------------
# Passos 2 e 3: câmbio
# ---------------------------------------------------------------------------
def passo2_futuro(atualizar):
    titulo(f"2. Dólar futuro (contrato que liquida em {config.HORIZONTE_HEDGE} meses)")
    dol = cambio.baixar_futuros_mensais(forcar=atualizar)
    futuro = cambio.serie_futuro(dol)
    print(f"{len(futuro)} meses, de {futuro.index.min()} a {futuro.index.max()}")
    print(futuro.head(3).to_string())
    return dol, futuro


def passo3_ptax(atualizar, dol):
    titulo("3. PTAX de fechamento do mês")
    ptax = cambio.baixar_ptax_mensal(forcar=atualizar)
    print(f"{len(ptax)} meses, de {ptax.index.min()} a {ptax.index.max()}")

    maior_dif, n = base_hedge.checar_convergencia(dol, ptax)
    print(f"Validação: o contrato que vence no dia seguinte bate com a PTAX "
          f"em {n} meses (maior diferença: R$ {maior_dif:.4f})")
    return ptax


# ---------------------------------------------------------------------------
# Passo 4: base casada
# ---------------------------------------------------------------------------
def passo4_base(incerteza, ptax, futuro):
    titulo("4. Base casada: futuro em t x PTAX em t + 3")
    base = base_hedge.montar_base(incerteza, ptax, futuro)
    base.to_csv(config.DADOS_PROCESSADOS / "base_hedge.csv")

    completos = base.dropna(subset=["ptax_liquidacao"])
    print(f"{len(base)} meses com futuro; {len(completos)} já com a PTAX do vencimento")
    colunas = ["incerteza", "ptax", "contrato", "futuro", "ptax_liquidacao", "resultado"]
    print(completos[colunas].tail(5).round(4).to_string())

    graficos.grafico_futuro_vs_spot(base, config.HORIZONTE_HEDGE, nome="4_futuro_vs_ptax.png")
    return base


# ---------------------------------------------------------------------------
# Passo 5: resultado do hedge
# ---------------------------------------------------------------------------
def passo5_resultado(base):
    lado = config.LADO_EMPRESA
    titulo(f"5. Resultado do hedge do {lado}")
    dados = analise.amostra_completa(base)
    formula = ("ln(s_t+3 / f_t)" if lado == "importador" else "ln(f_t / s_t+3)")
    print(f"Medida: {formula}  (> 0 = o hedge deixou a empresa melhor do que sem hedge)")
    print(f"{len(dados)} operações já vencidas")
    print(f"Resultado médio: {100 * dados['resultado'].mean():+.2f}% por operação de "
          f"{config.HORIZONTE_HEDGE} meses")
    print(f"O hedge compensou em {100 * dados['hedge_compensou'].astype(float).mean():.0f}% "
          f"dos meses")
    total = dados["resultado_reais"].sum()
    exposicao = f"{config.EXPOSICAO_USD:,.0f}".replace(",", ".")
    print(f"Ganho acumulado com US$ {exposicao}/mês: R$ {total:,.0f}".replace(",", "."))
    graficos.grafico_resultado_hedge(base, lado, nome="5_resultado_hedge.png")
    graficos.grafico_acumulado(base, lado, nome="5_resultado_acumulado.png")


# ---------------------------------------------------------------------------
# Passo 6: análise estatística
# ---------------------------------------------------------------------------
def passo6_analise(base):
    titulo("6. O resultado do hedge depende da incerteza?")

    cen = analise.cenarios(base)
    cen.to_csv(config.DADOS_PROCESSADOS / "cenarios.csv")
    print("Cenários (custos/receitas somados em R$; resultados em %):")
    print(cen.round(2).to_string())

    reg = analise.regressoes(base)
    reg.to_csv(config.DADOS_PROCESSADOS / "regressoes.csv")
    print(f"\nRegressões  resultado = α + β·(U - {config.MEDIA_BASE})  "
          f"(erros-padrão de Newey-West, {config.LAGS_NEWEY_WEST} lags):")
    print(reg[["n", "alfa", "beta", "beta_ep", "beta_t", "beta_p", "r2"]].round(4).to_string())
    print("\n" + analise.texto_conclusao(reg))

    graficos.grafico_dispersao(base, reg, config.LADO_EMPRESA, nome="6_incerteza_vs_resultado.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--atualizar", action="store_true", help="ignora o cache e baixa tudo de novo")
    args = parser.parse_args()
    config.DADOS_PROCESSADOS.mkdir(parents=True, exist_ok=True)

    incerteza = passo1_incerteza(args.atualizar)
    dol, futuro = passo2_futuro(args.atualizar)
    ptax = passo3_ptax(args.atualizar, dol)
    base = passo4_base(incerteza, ptax, futuro)
    passo5_resultado(base)
    passo6_analise(base)

    print(f"\nPronto. Base em {config.DADOS_PROCESSADOS / 'base_hedge.csv'}, "
          f"gráficos em {config.FIGURAS}")


if __name__ == "__main__":
    main()
