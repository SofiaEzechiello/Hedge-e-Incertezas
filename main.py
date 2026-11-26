"""
Trabalho de Derivativos e Riscos: hedge cambial e incerteza.

Pergunta: para uma empresa IMPORTADORA que faz hedge cambial todo mês,
o hedge compensa financeiramente? E compensa mais quando a incerteza está alta?

Passos:
    1. Série mensal de incerteza (EPU Brasil, de Baker, Bloom e Davis)
    2. Dólar futuro: ajuste de fim de mês do contrato que liquida em t + 3
       (planilha em data/raw, obtida pelo Bernardo)
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


# Passo 5: resultado do hedge
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
    print(f"Resultado acumulado com US$ {exposicao}/mês (1 contrato): "
          f"R$ {total:,.0f}".replace(",", "."))
    graficos.grafico_resultado_hedge(base, lado, nome="5_resultado_hedge.png")
    graficos.grafico_acumulado(base, lado, nome="5_resultado_acumulado.png")


# Passo 6: análise descritiva
def passo6_descritivo(base):
    titulo("6. O que aconteceu com o hedge em cada situação")
    pd_opcoes = {"float_format": lambda x: f"{x:,.2f}"}

    cen = analise.cenarios(base).astype({"meses": int})
    cen.to_csv(config.DADOS_PROCESSADOS / "cenarios.csv")
    print(f"Incerteza alta (índice > {config.LIMIAR_INCERTEZA}) x normal:")
    print(cen.to_string(**pd_opcoes))

    crises = analise.por_episodio(base)
    crises.to_csv(config.DADOS_PROCESSADOS / "por_crise.csv")
    print("\nNas crises e fora delas (pelo mês em que o hedge foi contratado):")
    print(crises.to_string(**pd_opcoes))

    anos = analise.por_ano(base)
    anos.to_csv(config.DADOS_PROCESSADOS / "por_ano.csv")
    print("\nPor ano:")
    print(anos.to_string(**pd_opcoes))
    graficos.graficos_descritivos(base, cen, crises, anos)


# Passo 7: regressão econométrica
def passo7_regressao(base, ate=None):
    titulo("7. Regressão: o resultado do hedge depende da incerteza?")
    pd.set_option("display.width", 200)
    saida = config.DADOS_PROCESSADOS
    out = regressao.estimar(base, ate=ate)
    d = out["dados"]

    print("Modelo: H_t = ln(S_t+3 / F_t) = b0 + b1·U_t + b2·ln(F_t / S_t) + e_t   (importador)")
    print(f"Amostra: {d.index.min()} a {d.index.max()}, {len(d)} cohorts"
          + (f" (hedges contratados até {ate})" if ate else ""))

    print("\n7.1 Estacionariedade (ADF; H0: raiz unitária)")
    adf = out["adf"]
    cols = ["amostra", "descricao", "adf_estatistica", "adf_p", "adf_lags",
            "adf_p_com_tendencia", "kpss_p", "decisao"]
    print(adf[cols].to_string(float_format=lambda x: f"{x:,.3f}"))
    if adf[adf["amostra"] == "principal"].loc["H", "decisao"] == "raiz unitária":
        print("ATENÇÃO: o próprio H (erro de previsão do hedge) saiu com raiz unitária. "
              "O código não diferencia o H; confira o ADF com tendência e o KPSS.")
    if out["diferenciar"]:
        print(f"-> Raiz unitária em {', '.join(out['diferenciar'])}: entram em primeira "
              f"diferença no modelo principal.")
    else:
        print("-> Todas estacionárias em nível: o modelo é estimado em níveis.")
    adf.to_csv(saida / "regressao_adf.csv")

    print("\n7.2 Câmbio e incerteza no mesmo mês: dlnS_t = a0 + a1·dU_t + u_t")
    c = regressao.regressao_cambio_incerteza(base, ate=ate)
    print(f"a1 = {c['alfa1']:.5f} (EP {c['alfa1_ep']:.5f}, p = {c['alfa1_p']:.3f}, n = {c['n']})")
    pd.Series(c).to_csv(saida / "regressao_cambio_incerteza.csv", header=["valor"])

    print("\n7.3 Exogeneidade fraca (Wald com Newey-West):")
    exo = regressao.teste_exogeneidade_fraca(d)
    print(exo.to_string(float_format=lambda x: f"{x:,.3f}"))
    print("   Esperado: defasagens sem efeito (p alto); adiantamentos podem ter efeito.")
    exo.to_csv(saida / "regressao_exogeneidade.csv")

    print("\n7.4 Resíduos do modelo principal (MQO): FAC, FACP e Ljung-Box")
    fac, lb = regressao.diagnostico_residuos(out["principal"])
    print(fac.to_string(float_format=lambda x: f"{x:,.3f}"))
    print(lb.to_string(float_format=lambda x: f"{x:,.4f}"))
    fac.to_csv(saida / "regressao_residuos_fac.csv")
    caminho = regressao.grafico_fac_facp(fac, n=int(out["principal"].nobs))
    print(f"Figura: {caminho}")

    print("\n7.5 Sensibilidade do erro-padrão de b1 ao tamanho do Newey-West:")
    sens = regressao.sensibilidade_lags(d)
    print(sens.to_string(float_format=lambda x: f"{x:,.5f}"))
    sens.to_csv(saida / "regressao_lags_hac.csv")

    print(f"\n7.6 Especificações (p com Newey-West L = {config.LAGS_NEWEY_WEST}):")
    tab = out["especificacoes"]
    cols = ["transformacao", "n", "beta1", "beta1_ep", "beta1_p", "beta1_p_mqo",
            "beta2", "beta2_p", "b_fama", "r2"]
    print(tab[cols].to_string(float_format=lambda x: f"{x:,.4f}"))
    tab.to_csv(saida / "regressao_especificacoes.csv")

    print("\nLeitura do modelo principal:")
    print(regressao.texto_conclusao(tab, out["diferenciar"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--atualizar", action="store_true", help="ignora o cache e baixa tudo de novo")
    parser.add_argument("--ate", default=None, metavar="AAAA-MM",
                        help="regressão só com hedges contratados até este mês (ex.: 2024-12)")
    args = parser.parse_args()
    config.DADOS_PROCESSADOS.mkdir(parents=True, exist_ok=True)

    incerteza = passo1_incerteza(args.atualizar)
    dol, futuro = passo2_futuro(args.atualizar)
    ptax, ptax_liq = passo3_ptax(args.atualizar, dol, futuro)
    base = passo4_base(incerteza, ptax, futuro, ptax_liq)
    passo5_resultado(base)
    passo6_descritivo(base)
    passo7_regressao(base, ate=args.ate)

    print(f"\nPronto. Base em {config.DADOS_PROCESSADOS / 'base_hedge.csv'}, "
          f"gráficos em {config.FIGURAS}")


if __name__ == "__main__":
    main()