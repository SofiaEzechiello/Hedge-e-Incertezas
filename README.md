# Hedge cambial e incerteza

Trabalho de Derivativos e Riscos (UFRGS) 

 Sofia Ezechiello e Bernardo.

**A pergunta.** Uma empresa **importadora** compra mercadoria em dólar todo mês e paga 3
meses depois. Para não correr o risco de o dólar subir, ela trava o câmbio comprando dólar
futuro. O hedge **compensa financeiramente**? E o que acontece quando a **incerteza
econômica** está alta?

A ideia não é medir a eficiência do hedge pela redução de volatilidade, e sim o
**resultado em dinheiro**: a empresa pagou menos ou mais do que pagaria sem hedge?

## Resultados principais (versão preliminar, só descritiva)

240 operações, de jul/2006 a jun/2026, com 1 contrato (US$ 50 mil) por mês:

- Na média, **o hedge custou 0,6% por operação** e compensou em só 39% dos meses
  (resultado acumulado de cerca de −R$ 214 mil).
- **Todo o custo veio dos meses de incerteza alta**: −3,0% por operação, contra 0,0% nos
  meses de incerteza normal.
- O resultado se mantém com outros cortes de "incerteza alta":

  | Incerteza alta = | Meses | Incerteza alta | Incerteza normal |
  |---|---|---|---|
  | 25% de meses mais incertos | 60 | −2,8% | +0,1% |
  | 20% de meses mais incertos | 48 | −3,0% | 0,0% |
  | 10% de meses mais incertos | 24 | −4,8% | −0,2% |

- Leitura: **o hedge protege contra a incerteza que ainda não chegou, não contra a que já
  está aí.** Os maiores ganhos vieram de hedges contratados antes dos choques (meados de
  2008, começo de 2020); contratado com a incerteza já alta, o dólar já subiu e o hedge
  trava um câmbio caro.

O relatório completo, com os gráficos, está em PDF (`relatorio_hedge.pdf`).

## Como rodar

1. Abra a pasta do projeto no VS Code (**Arquivo → Abrir Pasta**).
2. **Coloque a planilha do dólar futuro em `data/raw/`**, com o nome começando por
   `dolar_futuro` (ex.: `dolar_futuro_t4_bdi_a_partir_2006-07.xlsx`). Ela não está no
   GitHub porque a pasta `data/raw` fica fora do Git.
3. No terminal do VS Code (**Ctrl + '**):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
   python -m pip install -r requirements.txt
   python main.py
   ```

   Com Anaconda, dá para pular as duas primeiras linhas: escolha o interpretador do
   Anaconda em **Ctrl+Shift+P → Python: Select Interpreter** e rode as duas últimas.

O `main.py` baixa sozinho o EPU e a PTAX (leva menos de um minuto) e guarda tudo em
`data/raw/`. Para baixar de novo: `python main.py --atualizar`. Os testes rodam com
`python -m pytest`.

## O que o programa faz

| Passo | O quê | Arquivo |
|---|---|---|
| 1 | Série de incerteza: **EPU Brasil** (Baker, Bloom e Davis) | `epu.py` |
| 2 | Dólar futuro: ajuste de fim de mês do contrato que liquida em t + 3 (planilha) | `cambio.py` |
| 3 | PTAX: a do dia exato em que cada contrato liquida | `cambio.py` |
| 4 | Base casada: futuro travado em t × PTAX que de fato ocorreu em t + 3 | `base_hedge.py` |
| 5 | Resultado do hedge, em % e em R$ | `base_hedge.py` |
| 6 | Análise descritiva: incerteza alta × normal, por ano e nas