"""
Testes da regressão (passo 7) com dados simulados de coeficientes conhecidos.

O gerador reproduz a estrutura do trabalho:
    s_t+3 - s_t = a + b·(f_t - s_t) + γ·(U_t - média) + η_t+1 + η_t+2 + η_t+3
    => H_t = s_t+3 - f_t = a + (b - 1)·fd_t + γ·(U_t - média) + (η_t+1 + η_t+2 + η_t+3)
O erro soma 3 choques mensais, então os resíduos são MA(2), como no documento.
A incerteza reage ao choque cambial do mesmo mês (kappa), então U_t+1..U_t+3
é correlacionada com o erro de H_t, mas U_t, U_t-1... não.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incerteza import base_hedge, regressao  # noqa: E402


def gerar(n=400, gamma=0.0, b=0.4, a=0.0, kappa=3.0, rho_u=0.85, sigma=0.03,
          raiz_unitaria_u=False, rho_fd=0.8, semente=0, so_arrays=False):
    """
    Devolve a base (como a de montar_base) ou, com so_arrays, (H, U, fd).

    Construção exata: o spot é s_t = Σ η + c_t, com c_t+3 = c_t + μ_t, de modo que
    s_t+3 - s_t = μ_t + η_t+1 + η_t+2 + η_t+3, onde μ_t = a + b·fd_t + γ·(U_t - média).
    O futuro é f_t = s_t + fd_t. Logo H_t = s_t+3 - f_t = a + (b-1)·fd_t + γ·(U_t - média) + e_t.
    """
    rng = np.random.default_rng(semente)
    T = n + 3
    eta = rng.normal(0, sigma, T)                       # choque cambial de cada mês
    u = np.zeros(T)
    for t in range(1, T):
        rho = 1.0 if raiz_unitaria_u else rho_u
        u[t] = rho * u[t - 1] + kappa * eta[t] / sigma + rng.normal(0, 2.0)
    U = 100 + u
    fd = np.zeros(T)
    for t in range(1, T):
        fd[t] = rho_fd * fd[t - 1] + rng.normal(0, 0.01)   # forward discount persistente

    mu = a + b * fd[:n] + gamma * (U[:n] - U[:n].mean())
    c = np.zeros(T)
    for t in range(n):
        c[t + 3] = c[t] + mu[t]
    s = np.log(3.0) + np.cumsum(eta) + c
    f = s[:n] + fd[:n]                                  # f_t = s_t + fd_t
    H = s[3:3 + n] - f
    if so_arrays:
        return H, U[:n], fd[:n]

    meses = pd.period_range("2000-01", periods=T, freq="M")
    ptax = pd.Series(np.exp(s), index=meses)
    futuro = pd.DataFrame({"contrato": "DOLX", "futuro": np.exp(f)}, index=meses[:n])
    return base_hedge.montar_base(pd.Series(U, index=meses), ptax, futuro)


def test_recupera_coeficientes_conhecidos():
    base = gerar(n=1500, gamma=0.001, b=0.4, semente=1)
    out = regressao.estimar(base)
    p = out["especificacoes"].loc["(2) PRINCIPAL: H ~ U + ln(F/S)"]
    assert p["beta1"] == pytest.approx(0.001, abs=0.0008)
    assert p["beta2"] == pytest.approx(0.4 - 1, abs=0.35)   # fd é bem persistente; folga maior
    assert p["b_fama"] == pytest.approx(1 + p["beta2"])
    assert out["diferenciar"] == []


def test_construcao_do_gerador_bate_com_a_base():
    """fd = ln(F/S) e H = ln(S_t+3/F_t) calculados pela base são os do gerador."""
    H, U, fd = gerar(n=300, semente=2, so_arrays=True)
    d = regressao.preparar(gerar(n=300, semente=2))
    assert len(d) == 300
    assert d["fd"].to_numpy() == pytest.approx(fd, abs=1e-9)
    assert d["H"].to_numpy() == pytest.approx(H, abs=1e-9)
    assert d["U"].to_numpy() == pytest.approx(U, abs=1e-9)


def test_beta_zero_nao_rejeita_e_beta_positivo_rejeita():
    nulo = regressao.estimar(gerar(n=500, gamma=0.0, semente=3))["especificacoes"]
    forte = regressao.estimar(gerar(n=500, gamma=0.004, semente=3))["especificacoes"]
    k = "(2) PRINCIPAL: H ~ U + ln(F/S)"
    assert nulo.loc[k, "beta1_p"] > 0.01
    assert forte.loc[k, "beta1_p"] < 0.01
    assert forte.loc[k, "beta1"] > 0


def test_padronizada_e_igual_ao_nivel_vezes_desvio_padrao():
    tab = regressao.estimar(gerar(n=400, gamma=0.002, semente=4))["especificacoes"]
    nivel = tab.loc["(2) PRINCIPAL: H ~ U + ln(F/S)"]
    z = tab.loc["(3) U padronizada + ln(F/S)"]
    assert z["beta1"] == pytest.approx(nivel["beta1"] * nivel["dp_incerteza"])
    assert z["beta1_p"] == pytest.approx(nivel["beta1_p"])      # mesma estatística t
    assert z["beta2"] == pytest.approx(nivel["beta2"])


def test_tem_todas_as_especificacoes_e_a_amostra_ate_2024():
    base = gerar(n=400, semente=5)   # 2000-01 a 2033-04: passa de 2024
    out = regressao.estimar(base)
    tab = out["especificacoes"]
    assert len(tab) == 9    # 1, 2, 3, 3 dummies, sem 2020, sem sobreposição, até 2024
    ate = tab[tab.index.str.contains("até 2024-12")].iloc[0]
    assert ate["n"] < tab.loc["(2) PRINCIPAL: H ~ U + ln(F/S)", "n"]
    d24 = regressao.preparar(base, ate="2024-12")
    assert d24.index.max() <= pd.Period("2024-12", "M")
    sobrep = tab[tab.index.str.contains("sem sobreposição")].iloc[0]
    assert sobrep["n"] == pytest.approx(tab.loc["(2) PRINCIPAL: H ~ U + ln(F/S)", "n"] / 3, abs=1)


def test_adf_detecta_raiz_unitaria_e_diferencia_so_o_que_precisa():
    base = gerar(n=400, semente=6, raiz_unitaria_u=True)
    out = regressao.estimar(base)
    assert "U" in out["diferenciar"]
    assert "fd" not in out["diferenciar"]
    adf = out["adf"]
    principal = adf[adf["amostra"] == "principal"]
    assert principal.loc["H", "decisao"] == "estacionária"   # erro de previsão
    assert principal.loc["U", "decisao"] == "raiz unitária"
    assert (out["especificacoes"].loc["(2) PRINCIPAL: H ~ U + ln(F/S)", "transformacao"]
            == "Δ em U")
    # nível: o dummy continua sendo definido pelo nível de U (D80 tem ~20% de 1s)
    assert 0.1 < out["dados"]["D80"].mean() < 0.3


def test_residuos_sao_ma2_e_ljung_box_rejeita():
    out = regressao.estimar(gerar(n=800, gamma=0.001, semente=7))
    fac, lb = regressao.diagnostico_residuos(out["principal"])
    # MA(2) com pesos iguais: ρ1 = 2/3, ρ2 = 1/3, ρ3 = 0
    assert fac.loc[1, "fac"] == pytest.approx(2 / 3, abs=0.1)
    assert fac.loc[2, "fac"] == pytest.approx(1 / 3, abs=0.1)
    assert abs(fac.loc[4, "fac"]) < 0.15
    assert (lb["lb_pvalue"] < 0.01).all()


def test_newey_west_melhora_muito_o_tamanho_do_teste_mas_nao_resolve_em_amostra_pequena():
    """
    O documento diz que o MQO simples torna o teste t inválido com erros MA(h-1).
    Sob β1 = 0 verdadeiro (n = 240, U persistente):
      - MQO simples rejeita ~30% (nominal 5%): inválido, como o documento diz;
      - Newey-West L = 3 rejeita bem menos, mas ainda acima de 5% (~14%): é a distorção
        conhecida do HAC em amostra pequena com regressor persistente. Com n grande
        (2400) ele volta para ~5%; sem sobreposição (jan/abr/jul/out) o HC1 tem ~5%.
    Por isso p-valores de Newey-West perto de 0,05 pedem cautela.
    """
    rej_mqo, rej_nw, reps = 0, 0, 250
    for s in range(reps):
        H, U, fd = gerar(n=240, gamma=0.0, semente=1000 + s, so_arrays=True)
        X = pd.DataFrame({"U": U - U.mean(), "fd": fd})
        mqo, nw = regressao._ajustar(pd.Series(H), X, lags=3)
        rej_mqo += mqo.pvalues["U"] < 0.05
        rej_nw += nw.pvalues["U"] < 0.05
    assert rej_mqo / reps > 0.2
    assert rej_nw < 0.7 * rej_mqo
    assert rej_nw / reps < 0.2


def test_exogeneidade_fraca_defasagens_nao_importam_adiantamentos_sim():
    out = regressao.estimar(gerar(n=800, gamma=0.0, kappa=4.0, semente=8))
    exo = regressao.teste_exogeneidade_fraca(out["dados"])
    p_def = exo[exo.index.str.contains("defasagens")]["p"].iloc[0]
    p_adi = exo[exo.index.str.contains("adiantamentos")]["p"].iloc[0]
    assert p_def > 0.01
    assert p_adi < 0.01


def test_cambio_e_incerteza_no_mesmo_mes():
    base = gerar(n=500, kappa=3.0, semente=9)
    r = regressao.regressao_cambio_incerteza(base)
    assert r["alfa1"] > 0 and r["alfa1_p"] < 0.01     # U sobe junto com o choque cambial


def test_sensibilidade_a_lags_tem_o_mqo_e_os_lags_do_config():
    d = regressao.estimar(gerar(n=300, semente=10))["dados"]
    s = regressao.sensibilidade_lags(d)
    assert len(s) == 1 + len(regressao.LAGS_SENSIBILIDADE)
    assert s["beta1"].nunique() == 1 or np.allclose(s["beta1"], s["beta1"].iloc[0])  # só o EP muda
    # com cohorts sobrepostos o EP do MQO simples subestima o robusto
    assert s["ep"].iloc[0] < s["ep"].iloc[1:].max()


def test_texto_conclusao_roda():
    tab = regressao.estimar(gerar(n=300, gamma=0.003, semente=11))["especificacoes"]
    texto = regressao.texto_conclusao(tab)
    assert "β1" in texto and "b implícito" in texto


def test_fd_persistente_nunca_e_diferenciado_e_o_texto_nao_inventa_puzzle():
    out = regressao.estimar(gerar(n=400, rho_fd=1.0, gamma=0.001, semente=13))
    assert "fd" not in out["diferenciar"]
    adf = out["adf"][out["adf"]["amostra"] == "principal"]
    assert adf.loc["fd", "decisao"] in ("persistente (mantida em nível)", "estacionária")
    tab = out["especificacoes"]
    assert (tab["transformacao"] == "níveis").all() or "fd" not in "".join(tab["transformacao"])
    texto = regressao.texto_conclusao(tab, out["diferenciar"])
    linha = tab.loc[[i for i in tab.index if "PRINCIPAL" in i][0]]
    if linha["beta2_p"] >= 0.05:
        assert "não rejeita b = 1" in texto and "puzzle" not in texto
