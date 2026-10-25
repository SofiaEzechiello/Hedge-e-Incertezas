# Hedge cambial e incerteza

Trabalho de Derivativos e Riscos (UFRGS).

**A pergunta.** Uma empresa **importadora** compra mercadoria em dólar todo mês e paga 3
meses depois. Para não correr o risco do dólar subir, ela faz hedge: compra dólar futuro e
trava o câmbio. O hedge **compensa financeiramente**? E compensa **mais quando a incerteza
econômica está alta**?

A ideia não é medir a eficiência do hedge pela redução de volatilidade, e sim o
**resultado em dinheiro**: a empresa pagou menos ou mais do que pagaria sem hedge?

O programa faz, mês a mês (fechamento do mês):

1. um **indicador de incerteza** (réplica do IIE-Br da FGV com dados públicos do Banco Central);
2. o **dólar futuro** (B3) do contrato que vence em 3 meses;
3. a **PTAX** de fechamento do mês;
4. o casamento dos dois: o futuro contratado em t contra a PTAX que de fato ocorreu em t + 3;
5. o **resultado do hedge**: ln(f_t / s_t+3), a variável de Fama (1984), e o espelho do importador;
6. a **análise**: regressão do resultado na incerteza e os cenários com/sem hedge.

## Como rodar no VS Code

1. Abra a pasta `hedge-incerteza` no VS Code (**Arquivo → Abrir Pasta**).
2. Aceite instalar as extensões recomendadas (Python e Pylance).
3. No terminal do VS Code (**Ctrl + '**):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   python main.py
   ```

4. Quando o VS Code perguntar, escolha o interpretador `.venv`.

A primeira execução baixa as atas do COPOM, o Focus, a PTAX e um arquivo da B3 por mês
desde 2018 (uns 15 a 20 minutos no total). Tudo fica guardado em `data/raw/`, então as
próximas execuções levam segundos e só baixam o que for novo. Para baixar tudo de novo:
`python main.py --atualizar`.

Também dá para rodar pelo botão ▶ da aba **Executar e Depurar** (já configurado) e rodar
os testes pela aba **Testes** (ou `python -m pytest`).

**Comparação com a FGV (opcional):** se vocês tiverem a série oficial exportada do FGV Data,
salvem como `data/raw/xgdvConsulta.csv`. O programa detecta o arquivo, gera o gráfico
`1_vs_fgv.png` e imprime a correlação.

## Estrutura

```
hedge-incerteza/
├── main.py                  ← roda os 6 passos, de ponta a ponta
├── src/incerteza/
│   ├── config.py            ← URLs, termos, pesos, horizonte do hedge, modos
│   ├── copom.py             ← passo 1: atas do COPOM → componente textual
│   ├── expectativas.py      ← passo 1: Focus → componente de expectativas
│   ├── indicador.py         ← passo 1: junta os dois (0,8 / 0,2) e padroniza em base 100
│   ├── cambio.py            ← passos 2 e 3: dólar futuro (B3) e PTAX (BCB)
│   ├── base_hedge.py        ← passos 4 e 5: casa futuro e PTAX, calcula o resultado
│   ├── analise.py           ← passo 6: regressões e cenários
│   └── graficos.py          ← gráficos em PNG
├── tests/                   ← testes (dados simulados + recortes reais das APIs)
├── data/raw/                ← downloads (cache, fora do git)
├── data/processed/          ← base_hedge.csv, regressoes.csv, cenarios.csv, iiebr_*.csv
└── figuras/                 ← gráficos gerados
```

## Passo 1: o indicador de incerteza

O IIE-Br oficial tem duas partes: **Mídia** (frequência de notícias sobre incerteza em
jornais) e **Expectativa** (o quanto os economistas discordam nas previsões). A réplica
troca as fontes pagas por fontes públicas:

| Parte | IIE-Br oficial | Réplica |
|---|---|---|
| Mídia (peso 0,8) | 6 jornais | atas do COPOM |
| Expectativa (peso 0,2) | previsões de especialistas | Focus do BCB: IPCA, câmbio e Selic |

**1. Componente textual (`copom.py`).** Baixa o texto de todas as atas do COPOM. Até a
reunião 199 e a partir da 232 o texto vem pronto no JSON da API; entre a 200 e a 231 só
existe o PDF, que é baixado e lido. Para cada ata conta duas **densidades**:

- termos de incerteza (incerteza, risco, volatilidade...) ÷ número de palavras;
- termos de economia (inflação, juros, Selic...) ÷ número de palavras.

O índice da ata é o **produto** das duas: só fica alto quando a ata fala de risco *e* de
economia ao mesmo tempo. Dividir pelo número de palavras evita que uma ata longa pareça
mais incerta só por ser longa.

**2. Componente de expectativas (`expectativas.py`).** Baixa as projeções do Focus para
IPCA 12 meses, câmbio e Selic. Em cada mês pega a coleta mais próxima do dia 15 (a data
que a FGV usa) e calcula o **coeficiente de variação** (desvio-padrão ÷ média) de cada
variável. O CV não tem unidade, então dá para tirar a média de IPCA (~4%), câmbio
(~R$ 5) e Selic juntos.

**3. Consolidação (`indicador.py`).** Junta os dois componentes por mês (meses sem
reunião repetem a última ata), aplica 0,8 × texto + 0,2 × expectativas e **padroniza**:
média 100 e desvio 10 no período 2006–2015. Ou seja, 100 é a incerteza "normal" daquela
década, 110 é um desvio-padrão acima.

### Problemas encontrados no notebook original (e o modo corrigido)

O `main.py` calcula duas versões: `original` (igual ao notebook) e `corrigido`. A base do
hedge usa a corrigida (`MODO_TRABALHO` em `config.py`), e cada correção pode ser
ligada/desligada lá.

1. **O texto não pesa nada no índice final.** O índice das atas tem ordem de grandeza
   0,0001 (testado em atas reais: entre 3×10⁻⁵ e 3×10⁻⁴), e é somado com as expectativas
   já em base 100. Na prática, 0,8 × 0,0002 + 0,2 × 100 ≈ só expectativas: o
   indicador "original" é quase 100% o componente de expectativas, não 20%.
   *Correção:* padronizar os dois componentes (z-score na janela 2006–2015) **antes** de
   aplicar os pesos. O programa imprime o "peso efetivo do texto na variância" para
   mostrar isso.

2. **As atas antigas escrevem os acentos como código HTML.** Na ata 50, por exemplo,
   aparece `infla&ccedil;&atilde;o` em vez de "inflação", então termos com acento nunca
   são encontrados nas atas antigas, e as tags HTML entram na contagem de palavras. Como
   as atas em PDF não têm nada disso, a série tem quebras artificiais nas reuniões 200 e
   232. *Correção:* remover as tags e converter as entidades antes de contar.

3. **O componente de expectativas não mede discordância entre analistas.** O original
   calcula o CV da *mediana* numa janela móvel de 12 meses, o que mede o quanto o
   consenso **mudou ao longo do ano**, não o quanto os analistas **discordam entre si**
   (o conceito do IIE-Br). Isso também deixa a série suave e atrasada. *Correção:* a API
   do Focus já traz o desvio-padrão das projeções de cada coleta, então o CV passa a ser
   `DesvioPadrao ÷ Mediana` do próprio mês.

4. **O horizonte das projeções de câmbio e Selic é arbitrário.** No câmbio, o primeiro
   `.first()` já deixa uma linha por mês, e o passo seguinte, que deveria escolher o
   horizonte de 12 meses, não faz nada. Na Selic, `R6/2028` vira só `2028`, então a
   reunião escolhida dentro do ano é aleatória. *Correção:* escolher explicitamente a
   projeção mais próxima de 12 meses à frente.

### Limitações do indicador (vale citar no trabalho)

- As atas mostram a visão do Banco Central, não a percepção ampla que os jornais captam.
- O vocabulário é fixo e não distingue contexto ("o risco diminuiu" conta como risco).
- O CV da Selic fica inflado quando a taxa está muito baixa (2020–21), porque a média no
  denominador é pequena.
- A série oficial da FGV só está disponível no FGV Data (pago).

## Passos 2 e 3: dólar futuro e PTAX

**PTAX (`cambio.py`).** PTAX de venda do último dia útil de cada mês, série 3696 do SGS do
Banco Central.

**Dólar futuro (`cambio.py`).** Preço de ajuste do contrato DOL da B3 no último pregão de
cada mês, tirado do arquivo diário de preços da B3 (BVBG.086, o mesmo que o pacote `rb3`
usa). Usamos o **preço de ajuste** e não o último negócio porque os vencimentos mais longos
quase não são negociados, mas a B3 calcula o ajuste de todos eles todo dia.

- O DOL é cotado em R$ por US$ 1.000; o código divide por 1.000 para ficar na unidade da PTAX.
- **Cobertura:** a B3 só disponibiliza esses arquivos de graça a partir de **jan/2018**
  (a página antiga de ajustes saiu do ar). Antes disso, só por terminal (Bloomberg,
  Economatica) ou pedindo à B3.
- A primeira execução baixa um arquivo por mês desde 2018 (uns 10 minutos) e guarda só as
  linhas do DOL em `data/raw/b3_dol/`.

### Qual contrato é o "de 3 meses"

O DOL vence no 1º dia útil do mês de vencimento e é liquidado pela **PTAX do último dia
útil do mês anterior**. Exemplo: o contrato de maio (DOLK) paga a PTAX de 30 de abril.

Então, no fechamento de janeiro, o contrato que vai valer exatamente a PTAX de fim de
abril (3 meses depois) é o de **maio**:

| Fim do mês t | Contrato usado | Liquida pela PTAX de |
|---|---|---|
| jan/2018 | DOLK18 (maio) | fim de abr/2018 |
| fev/2018 | DOLM18 (junho) | fim de mai/2018 |
| out/2018 | DOLF19 (janeiro) | fim de dez/2018 |

Assim o futuro e o à vista convergem por construção no vencimento. O programa confere isso
sozinho: no último pregão de cada mês, o contrato que vence no dia seguinte tem que valer a
PTAX daquele dia (testado com dados reais: DOLV26 em 30/09/2026 = 5180,9; PTAX = 5,1809).

O horizonte fica em `HORIZONTE_HEDGE` no `config.py`. Se o grupo preferir usar o contrato
*nomeado* para t + 3 (o de abril, no exemplo), basta pôr `HORIZONTE_HEDGE = 2`.

## Passo 4: a base casada

O gráfico `4_futuro_vs_ptax.png` mostra, para cada mês em que o hedge é contratado, o preço
do futuro (o câmbio que a empresa travou) e a PTAX que de fato ocorreu 3 meses depois (o
câmbio que ela pagaria sem hedge). Quando a linha da PTAX está acima, o hedge compensou.

Os 3 últimos meses ainda não têm PTAX de vencimento e ficam fora da análise.

## Passo 5: o resultado do hedge

Para o **exportador** (quem vende dólar futuro), a medida do resumo de Fama é

    H_t = ln(f_t / s_t+3)

O **importador** está do outro lado e ganha o espelho exato:

    H_t^imp = ln(s_t+3 / f_t) = −H_t

Como a empresa do trabalho é importadora, o resultado usado é o segundo
(`LADO_EMPRESA = "importador"` no `config.py`; dá para trocar).

Por que faz sentido:

- **Compara com e sem hedge.** Sem hedge a importadora paga s_t+3. Com hedge ela paga f_t,
  conhecido já em t. Então H^imp > 0 quer dizer que o dólar subiu além do que o futuro
  previa e **o hedge compensou**; H^imp < 0 quer dizer que ela pagou mais do que pagaria sem
  hedge.
- **É uma porcentagem.** ln(1,03) ≈ 3%, então H mede quanto a empresa economizou ou
  perdeu em % do valor da importação, comparável entre meses com o dólar a R$ 3 ou R$ 5.
- **Log deixa importador e exportador espelhos exatos** (com retorno simples, não).
- **É a variável de Fama (1984)**, com horizonte de 3 meses em vez de 1, então dá para
  apoiar a interpretação na literatura: H = prêmio de risco − erro de previsão.

O resultado também sai em reais, para uma importação simulada de US$ 1 milhão por mês
(`EXPOSICAO_USD`): `custo_sem_hedge` = N × s_t+3, `custo_com_hedge` = N × f_t, e
`resultado_reais` = a diferença. Para somar resultados ao longo do tempo, use reais e não
logs (disclaimer 7 do resumo).

`data/processed/base_hedge.csv`, uma linha por mês t:

| Coluna | O que é |
|---|---|
| `incerteza` | U_t: indicador de incerteza conhecido no fechamento de t (base 100) |
| `incerteza_alta` | True se U_t > `LIMIAR_INCERTEZA` (110) |
| `ptax` | s_t: dólar à vista no fim de t |
| `contrato`, `futuro` | contrato DOL usado e seu preço de ajuste em t (R$/US$) |
| `ptax_liquidacao` | s_t+3: PTAX de fim de t + 3, o dólar que de fato ocorreu |
| `H_importador`, `H_exportador` | ln(s_t+3/f_t) e ln(f_t/s_t+3) |
| `resultado` | o H do lado da empresa |
| `hedge_compensou` | True se o hedge deixou a empresa melhor do que sem hedge |
| `custo_sem_hedge`, `custo_com_hedge` | R$ pagos sem e com hedge |
| `resultado_reais` | R$ economizados com o hedge (negativo = perdeu) |
| `data_pregao`, `contratos_abertos`, `negocios` | dia usado e liquidez do contrato |

Gráficos: `5_resultado_hedge.png` (incerteza em cima, resultado de cada mês embaixo) e
`5_resultado_acumulado.png` (quanto a empresa ganhou ou perdeu ao longo do tempo).

## Passo 6: o resultado depende da incerteza?

**Cenários** (`cenarios.csv`): para os meses de incerteza alta e normal, quanto a empresa
pagaria sem hedge, quanto pagou com hedge, a diferença em R$, o resultado médio em % e em
quantos % dos meses o hedge compensou. É a tabela "com hedge × sem hedge × com incerteza ×
sem incerteza".

**Regressão** (`regressoes.csv`):

    resultado_t = α + β · (U_t − 100) + ε_t

- O índice entra centrado em 100, então **α é o resultado médio do hedge com incerteza
  normal**.
- **β > 0**: o hedge do importador rende mais quando a incerteza está alta. **β < 0**: rende
  menos. **β = 0**: a incerteza não muda o resultado.
- Para o exportador, α e β trocam de sinal e os erros-padrão, t e R² são idênticos.

Especificações calculadas:

| Especificação | Para quê |
|---|---|
| Principal | a regressão acima, com erro-padrão de Newey-West (3 lags) |
| Dummy (U > 110) | troca U_t por 1/0 de incerteza alta: o teste dos outliers do resumo |
| Sem 2020 | robustez: o resultado não pode depender só da pandemia |
| Sem sobreposição | só cohorts de jan/abr/jul/out, que não compartilham meses |

**Por que Newey-West:** cada operação dura 3 meses e começa uma nova todo mês, então a de
janeiro (jan→abr) e a de fevereiro (fev→mai) compartilham fev–abr. Os erros ficam
autocorrelacionados e o erro-padrão comum seria pequeno demais (Hansen e Hodrick, 1980).

**Por que o limiar é 110:** o índice tem média 100 e desvio 10 em 2006–2015, então 110 é
"1 desvio acima do normal". Como essa escala foi fixada antes da amostra do hedge (2018+),
o limiar é definido *ex ante*, como o resumo pede. Muda em `LIMIAR_INCERTEZA`.

**Timing:** U_t só usa informação conhecida no fechamento de t. A ata do COPOM entra no mês
em que foi **publicada** (uns 6 dias depois da reunião), e o Focus usa a coleta perto do
dia 15.

Gráfico: `6_incerteza_vs_resultado.png`, um ponto por mês com a reta da regressão.

## Limitações da análise (vale citar no trabalho)

- **Amostra curta:** o futuro gratuito da B3 começa em 2018, então são uns 100 meses
  (~33 operações independentes) e, de crise forte, só a pandemia. O poder dos testes é
  baixo: β não significativo **não** prova que a incerteza não importa.
- **H mede o derivativo isolado**, com hedge ratio 1 e sem custos de corretagem, margem ou
  o financiamento dos ajustes diários.
- **Convergência:** com o contrato escolhido como explicado nos passos 2 e 3, o futuro liquida
  exatamente na PTAX usada como s_t+3, então o "basis" do disclaimer 6 do resumo não se
  aplica aqui.
- Tudo que se lê como "prêmio" é condicional à hipótese de expectativas racionais (Fama).

## Fontes

- Atas do COPOM: API do site do Banco Central.
- Expectativas: Sistema de Expectativas de Mercado (Focus), API Olinda do BCB.
- PTAX: SGS do Banco Central, série 3696 (venda, fim de período).
- Dólar futuro: B3, arquivo de preços de mercado BVBG.086 (preço de ajuste do DOL), o mesmo
  usado pelo pacote rb3 (R).
- Fama, E. (1984). Forward and spot exchange rates. *Journal of Monetary Economics* 14(3).
- Hansen, L. e Hodrick, R. (1980). Forward exchange rates as optimal predictors of future
  spot rates. *Journal of Political Economy* 88(5).
- Metodologia do indicador: notebook "Replicando um Indicador de Incerteza no Python",
  Análise Macro (Vitor Wilher).
- IIE-Br: FGV IBRE.
