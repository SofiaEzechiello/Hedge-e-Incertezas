"""
Passo 7: regressão econométrica do resultado do hedge na incerteza.

Segue o documento "Criando o modelo". Para a empresa IMPORTADORA:

    H_t = ln(S_t+3 / F_t) = β0 + β1·U_t + β2·ln(F_t / S_t) + ε_t

    H_t            resultado do hedge do importador (> 0: o hedge economizou dinheiro)
    U_t            incerteza (EPU) conhecida no fechamento de t
    ln(F_t / S_t)  forward discount (diferencial de juros), controle de Fama

Por que o controle: H = (s_t+3 - s_t) - (f_t - s_t). Se a regressão de Fama
s_t+3 - s_t = a + b·(f_t - s_t) + e tem b < 1 (forward premium puzzle), então
H = a + (b - 1)·(f_t - s_t) + e, ou seja, β2 = b - 1. Sob "o futuro é um
previsor não viesado do spot" (b = 1), β2 = 0.

Cuidados de estimação (um por função):

    1. Estacionariedade (ADF com BIC, KPSS de conferência)  -> testes_estacionariedade
       Variável com raiz unitária entra diferenciada.
    2. Exogeneidade fraca: E[ε_t | U_t, U_t-1, ...] = 0, mas NÃO a estrita
       (choques cambiais futuros mexem na incerteza futura).
                                                         -> regressao_cambio_incerteza
                                                         -> teste_exogeneidade_fraca
    3. Resíduos são MA(h-1) por causa da janela de 3 meses (FAC/FACP)
                                                         -> diagnostico_residuos
       Por isso o erro-padrão é Newey-West (HAC) com L >= h  -> sensibilidade_lags
       h = 3 meses: a sobreposição entre cohorts vizinhos é de h-1 = 2 meses, então
       L = 3 já cobre a dependência teórica (e sobra um lag de folga).

Teste principal: H0: β1 = 0 contra H1: β1 != 0 (bicaudal), p-valor pela normal
com erro-padrão HAC.

Variantes (robustez): EPU padronizado, dummy de incerteza alta (percentis 75/80/90),
amostra até dez/2024 (salto do EPU em 2025), sem 2020 e cohorts sem sobreposição.
"""

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf

from . import analise, config, graficos

# A série do EPU dá um salto em 2025; a amostra de robustez para em dez/2024
# (mês de contratação do hedge).
ULTIMO_MES_ROBUSTEZ = "2024-12"
# Tamanhos de Newey-West testados na tabela de sensibilidade
LAGS_SENSIBILIDADE = (2, 3, 4, 6, 9, 12)

NOMES = {
    "H": "H = ln(S_t+3 / F_t)",
    "U": "Incerteza U_t (EPU)",
    "fd": "ln(F_t / S_t)",
}


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
def _percentis_dummy():
    principal = config.PERCENTIL_INCERTEZA_ALTA
    return sorted({0.75, principal, 0.90})


def preparar(base, ate=None, diferenciar=()):
    """
    Monta o quadro da regressão: uma linha por cohort que já venceu.

        H   ln(S_t+3 / F_t)  (importador, como no documento)
        U   incerteza em t
        fd  ln(F_t / S_t)
        D75, D80, D90  dummies de incerteza alta (U acima do percentil da AMOSTRA)

    ate:        último mês de contratação incluído, ex.: "2024-12".
    diferenciar: nomes entre "U" e "fd" que entram em primeira diferença
                 (calculada em meses consecutivos; a dummy usa sempre o nível de U).
    """
    d = analise.amostra_completa(base).dropna(subset=["ptax", "futuro", "ptax_liquidacao"])
    if ate is not None:
        d = d[d.index <= pd.Period(ate, "M")]
    q = pd.DataFrame({
        "H": d["H_importador"].astype(float),
        "U": d["incerteza"].astype(float),
        "fd": np.log(d["futuro"].astype(float) / d["ptax"].astype(float)),
    })
    for p in _percentis_dummy():
        q[f"D{round(100 * p)}"] = (q["U"] > q["U"].quantile(p)).astype(float)

    for v in diferenciar:
        meses = pd.period_range(q.index.min(), q.index.max(), freq="M")
        q[v] = q[v].reindex(meses).diff().reindex(q.index)
    return q.dropna()


# ---------------------------------------------------------------------------
# 1. Estacionariedade
# ---------------------------------------------------------------------------
def testes_estacionariedade(d, variaveis=("H", "U", "fd"), nivel=0.05):
    """
    ADF (H0: raiz unitária) com constante e lags escolhidos por BIC (com erros MA(2)
    o AIC escolhe lags demais e perde poder: em simulação, 92% contra 99% do BIC). Colunas extras:
    ADF com tendência e KPSS (H0: estacionária), só para conferência.
    A decisão usa o ADF: p >= nivel -> "raiz unitária" (diferenciar).
    """
    linhas = []
    for v in variaveis:
        x = d[v].dropna().astype(float)
        with warnings.catch_warnings():
            # KPSS avisa quando o p-valor sai da tabela; o adfuller avisa sobre mudança futura
            # do formato do retorno (o kwarg que a silencia não existe no statsmodels 0.14)
            warnings.simplefilter("ignore")
            est, p, lags, n, *_ = adfuller(x, regression="c", autolag="BIC")
            p_ct = adfuller(x, regression="ct", autolag="BIC")[1]
            p_kpss = kpss(x, regression="c", nlags="auto")[1]
        linhas.append({
            "variavel": v, "descricao": NOMES.get(v, v), "n": int(n),
            "adf_estatistica": est, "adf_p": p, "adf_lags": int(lags),
            "adf_p_com_tendencia": p_ct, "kpss_p": p_kpss,
            "decisao": "raiz unitária" if p >= nivel else "estacionária",
        })
    return pd.DataFrame(linhas).set_index("variavel")


# ---------------------------------------------------------------------------
# Estimação
# ---------------------------------------------------------------------------
def _ajustar(y, X, lags):
    """MQO + a versão com erro-padrão robusto (Newey-West; HC1 se lags = 0)."""
    X = sm.add_constant(X.astype(float), has_constant="add")
    y = y.astype(float)
    mqo = sm.OLS(y, X).fit()
    if lags > 0:
        robusto = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    else:
        robusto = sm.OLS(y, X).fit(cov_type="HC1")
    return mqo, robusto


def _linha(nome, d, u, controle=True, lags=config.LAGS_NEWEY_WEST, transformacao="níveis"):
    """
    Uma especificação. u: "U" (índice centrado na média da amostra), "z" (padronizado)
    ou o nome de uma dummy ("D80"...). Devolve (linha da tabela, resultado robusto).
    """
    d = d.copy()
    if u == "U":
        d["x"] = d["U"] - d["U"].mean()  # α passa a ser o H esperado com U na média da amostra
    elif u == "z":
        d["x"] = (d["U"] - d["U"].mean()) / d["U"].std(ddof=1)
    else:
        d["x"] = d[u]
    X = d[["x", "fd"]] if controle else d[["x"]]
    mqo, rob = _ajustar(d["H"], X, lags)
    linha = {
        "especificacao": nome, "transformacao": transformacao, "n": int(rob.nobs),
        "regressor": {"U": "U (pontos)", "z": "U padronizada (1 d.p.)"}.get(u, f"{u}"),
        "dp_incerteza": d["U"].std(ddof=1),
        "alfa": rob.params["const"],
        "beta1": rob.params["x"], "beta1_ep": rob.bse["x"], "beta1_t": rob.tvalues["x"],
        "beta1_p": rob.pvalues["x"], "beta1_p_mqo": mqo.pvalues["x"],
        "beta1_ep_mqo": mqo.bse["x"],
        "beta2": np.nan, "beta2_ep": np.nan, "beta2_p": np.nan, "b_fama": np.nan,
        "r2": rob.rsquared, "lags_nw": lags,
    }
    if controle:
        linha.update(beta2=rob.params["fd"], beta2_ep=rob.bse["fd"], beta2_p=rob.pvalues["fd"],
                     b_fama=1 + rob.params["fd"])
    return linha, rob


def _amostra_principal(base, ate, nivel):
    """Prepara a amostra, roda o ADF e diferencia o que tiver raiz unitária."""
    d0 = preparar(base, ate)
    adf = testes_estacionariedade(d0, nivel=nivel)
    diferenciar = [v for v in ("U", "fd") if adf.loc[v, "decisao"] == "raiz unitária"]
    d = preparar(base, ate, diferenciar) if diferenciar else d0
    return d, diferenciar, adf


def _rotulo(diferenciar):
    return "níveis" if not diferenciar else "Δ em " + ", ".join(diferenciar)


def estimar(base, ate=None, lags=config.LAGS_NEWEY_WEST, nivel=0.05):
    """
    Estima todas as especificações. Devolve um dicionário:

        especificacoes  tabela principal + robustez (uma linha por modelo)
        adf             testes de estacionariedade (amostra principal e até 2024)
        diferenciar     o que entrou diferenciado na amostra principal
        principal       resultado do statsmodels do modelo principal (para diagnósticos)
        dados           quadro usado no modelo principal
    """
    d, dif, adf = _amostra_principal(base, ate, nivel)
    rot = _rotulo(dif)
    p_alta = round(100 * config.PERCENTIL_INCERTEZA_ALTA)

    linhas = []
    linha, _ = _linha("(1) Básico: H ~ U", d, "U", controle=False, lags=lags, transformacao=rot)
    linhas.append(linha)
    linha, principal = _linha("(2) PRINCIPAL: H ~ U + ln(F/S)", d, "U", lags=lags, transformacao=rot)
    linhas.append(linha)
    linha, _ = _linha("(3) U padronizada + ln(F/S)", d, "z", lags=lags, transformacao=rot)
    linhas.append(linha)
    for p in _percentis_dummy():
        col = f"D{round(100 * p)}"
        linha, _ = _linha(f"(4) Dummy U > percentil {round(100 * p)} + ln(F/S)", d, col,
                          lags=lags, transformacao=rot)
        linhas.append(linha)

    inicio, fim = (pd.Period(p, "M") for p in config.PERIODO_PANDEMIA)
    sem_pandemia = d[(d.index < inicio) | (d.index > fim)]
    linha, _ = _linha("(5) Principal sem 2020", sem_pandemia, "U", lags=lags, transformacao=rot)
    linhas.append(linha)
    sem_sobreposicao = d[d.index.month % config.HORIZONTE_HEDGE == 1]
    linha, _ = _linha("(6) Principal, cohorts sem sobreposição (jan/abr/jul/out)",
                      sem_sobreposicao, "U", lags=0, transformacao=rot)
    linhas.append(linha)

    adf = adf.assign(amostra="principal")
    ate_rob = ULTIMO_MES_ROBUSTEZ
    if ate is None or pd.Period(ate, "M") > pd.Period(ate_rob, "M"):
        d24, dif24, adf24 = _amostra_principal(base, ate_rob, nivel)
        linha, _ = _linha(f"(7) Principal até {ate_rob}", d24, "U", lags=lags,
                          transformacao=_rotulo(dif24))
        linhas.append(linha)
        adf = pd.concat([adf, adf24.assign(amostra=f"até {ate_rob}")])

    tabela = pd.DataFrame(linhas).set_index("especificacao")
    return {"especificacoes": tabela, "adf": adf, "diferenciar": dif,
            "principal": principal, "dados": d}


# ---------------------------------------------------------------------------
# 2. Exogeneidade
# ---------------------------------------------------------------------------
def regressao_cambio_incerteza(base, ate=None):
    """
    Δln(PTAX_t) = α0 + α1·ΔU_t + u_t   (variações mensais, sem sobreposição).
    Mostra que câmbio e incerteza andam juntos no mesmo mês: α1 != 0 é o motivo
    de a exogeneidade ser só fraca (choques cambiais futuros mexem em U futuro).
    """
    b = base.dropna(subset=["ptax", "incerteza"])
    if ate is not None:
        b = b[b.index <= pd.Period(ate, "M")]
    meses = pd.period_range(b.index.min(), b.index.max(), freq="M")
    dlnS = np.log(b["ptax"].astype(float)).reindex(meses).diff()
    dU = b["incerteza"].astype(float).reindex(meses).diff()
    q = pd.concat([dlnS.rename("dlnS"), dU.rename("dU")], axis=1).dropna()
    _, rob = _ajustar(q["dlnS"], q[["dU"]], lags=0)
    return {"n": int(rob.nobs), "alfa0": rob.params["const"], "alfa1": rob.params["dU"],
            "alfa1_ep": rob.bse["dU"], "alfa1_p": rob.pvalues["dU"], "r2": rob.rsquared}


def teste_exogeneidade_fraca(d, lags=config.LAGS_NEWEY_WEST, n_defasagens=2, n_adiantamentos=None):
    """
    Checagem informal do argumento do documento:
        E[ε_t | U_t, U_t-1, ...] = 0           (defasagens não devem importar)
        E[ε_t | U_t+1, ..., U_t+h] != 0        (adiantamentos podem importar)

    Acrescenta ao modelo principal U_t-1..U_t-k (teste conjunto) e, separadamente,
    U_t+1..U_t+h (teste conjunto), ambos com erro-padrão Newey-West.
    p alto nas defasagens e p baixo nos adiantamentos é o padrão esperado.
    """
    n_adiantamentos = config.HORIZONTE_HEDGE if n_adiantamentos is None else n_adiantamentos
    meses = pd.period_range(d.index.min(), d.index.max(), freq="M")
    u = d["U"].reindex(meses)
    q = d[["H", "fd"]].copy()
    q["x"] = d["U"] - d["U"].mean()
    saida = []
    for rotulo, passos in (("defasagens", [-k for k in range(1, n_defasagens + 1)]),
                           ("adiantamentos", [k for k in range(1, n_adiantamentos + 1)])):
        X = q[["x", "fd"]].copy()
        nomes = []
        for k in passos:
            nome = f"U_{'l' if k < 0 else 'f'}{abs(k)}"
            X[nome] = (u.shift(-k) - d["U"].mean()).reindex(q.index)  # k > 0: U_t+k
            nomes.append(nome)
        ok = X.dropna().index
        _, rob = _ajustar(q.loc[ok, "H"], X.loc[ok], lags)
        w = rob.wald_test(", ".join(f"{n} = 0" for n in nomes), use_f=False, scalar=True)
        saida.append({"teste": f"U_t{'-' if passos[0] < 0 else '+'}1..{abs(passos[-1])}"
                               f" ({rotulo})", "n": int(rob.nobs),
                      "qui2": float(w.statistic), "gl": len(nomes), "p": float(w.pvalue)})
    return pd.DataFrame(saida).set_index("teste")


# ---------------------------------------------------------------------------
# 3. Resíduos e erro-padrão
# ---------------------------------------------------------------------------
def diagnostico_residuos(res, nlags=12):
    """
    FAC e FACP dos resíduos do modelo principal e Ljung-Box.
    Esperado com janela de h = 3 meses: FAC significativa nos lags 1 e 2
    (MA(h-1)) e que se apaga depois; FACP decaindo.
    """
    e = np.asarray(res.resid, dtype=float)
    n = len(e)
    tabela = pd.DataFrame({
        "fac": acf(e, nlags=nlags, fft=False)[1:],
        "facp": pacf(e, nlags=nlags, method="ywm")[1:],
    }, index=pd.Index(range(1, nlags + 1), name="lag"))
    tabela["banda_95"] = 1.96 / np.sqrt(n)
    tabela["fac_significativa"] = tabela["fac"].abs() > tabela["banda_95"]
    tabela["facp_significativa"] = tabela["facp"].abs() > tabela["banda_95"]
    lb = acorr_ljungbox(e, lags=[3, 6, 12])
    lb.index.name = "lag"
    return tabela, lb


def sensibilidade_lags(d, lags=LAGS_SENSIBILIDADE):
    """β1 do modelo principal com Newey-West de diferentes tamanhos (e o MQO sem correção)."""
    x = d[["U", "fd"]].copy()
    x["U"] = x["U"] - x["U"].mean()
    linhas = []
    mqo, _ = _ajustar(d["H"], x, 1)
    linhas.append({"erro_padrao": "MQO simples (inválido)", "lags": 0,
                   "beta1": mqo.params["U"], "ep": mqo.bse["U"], "p": mqo.pvalues["U"]})
    for L in lags:
        _, rob = _ajustar(d["H"], x, L)
        linhas.append({"erro_padrao": f"Newey-West L = {L}", "lags": L,
                       "beta1": rob.params["U"], "ep": rob.bse["U"], "p": rob.pvalues["U"]})
    return pd.DataFrame(linhas).set_index("erro_padrao")


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def texto_conclusao(tabela, diferenciar=()):
    """Frases em português sobre o modelo principal (sem interpretar causalidade)."""
    p = tabela.loc[[i for i in tabela.index if "PRINCIPAL" in i][0]]
    unidade = "ponto de incerteza" if not diferenciar else "ponto de variação mensal da incerteza"
    efeito = 100 * p["beta1"] * p["dp_incerteza"]
    rejeita = p["beta1_p"] < 0.05
    frases = [
        f"Modelo principal (n = {p['n']:.0f}; {p['transformacao']}): "
        f"β1 = {100 * p['beta1']:+.4f} p.p. por {unidade} "
        f"(EP Newey-West {100 * p['beta1_ep']:.4f}; p = {p['beta1_p']:.3f}).",
        f"+1 desvio-padrão de incerteza ({p['dp_incerteza']:.1f} pontos) está associado a "
        f"{efeito:+.2f} p.p. no resultado do hedge do importador.",
        ("Rejeita H0: β1 = 0 a 5%: a incerteza tem poder preditivo sobre o resultado do hedge."
         if rejeita else
         "Não rejeita H0: β1 = 0 a 5%: sem evidência de que a incerteza preveja o resultado do hedge."),
        f"Controle de Fama: β2 = {p['beta2']:+.3f} (p = {p['beta2_p']:.3f}); "
        f"b implícito = {p['b_fama']:.3f} "
        f"({'b < 1: compatível com o forward premium puzzle' if p['b_fama'] < 1 else 'b >= 1'}), "
        f"p-valor de H0: b = 1 igual ao de β2.",
    ]
    return "\n".join(frases)


# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------
def grafico_fac_facp(tabela, n, nome="7_fac_facp_residuos.png"):
    """FAC e FACP dos resíduos do modelo principal, com a banda de 95% (±1,96/√n)."""
    plt = graficos.plt
    banda = 1.96 / n ** 0.5
    fig, eixos = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, col, titulo in ((eixos[0], "fac", "FAC dos resíduos"),
                            (eixos[1], "facp", "FACP dos resíduos")):
        fora = tabela[col].abs() > banda
        cores = [config.COR_SECUNDARIA if f else config.COR_PRINCIPAL for f in fora]
        ax.bar(tabela.index, tabela[col], color=cores, width=0.6, zorder=3)
        ax.axhline(0, color="#8c8c8c", linewidth=0.8)
        for sinal in (1, -1):
            ax.axhline(sinal * banda, color="#8c8c8c", linewidth=0.8, linestyle="--")
        ax.set_title(titulo, loc="left", fontsize=12, fontweight="bold", color=config.COR_TEXTO)
        ax.set_xlabel("Defasagem (meses)", color=config.COR_TEXTO)
        ax.set_xticks(list(tabela.index))
        ax.grid(axis="y", color=config.COR_GRADE, linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
    return graficos._salvar(fig, nome, "Laranja: fora da banda de 95%. Elaboração própria.")
