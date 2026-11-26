"""
Configurações do projeto: caminhos, fontes de dados e parâmetros do hedge.
"""

from pathlib import Path

# Caminhos
RAIZ = Path(__file__).resolve().parents[2]          # pasta do projeto
DADOS_BRUTOS = RAIZ / "data" / "raw"                # downloads (cache)
DADOS_PROCESSADOS = RAIZ / "data" / "processed"     # séries prontas
FIGURAS = RAIZ / "figuras"                          # gráficos exportados

# Câmbio: PTAX e dólar futuro
# PTAX venda, fim de período, mensal (= PTAX do último dia útil do mês)
SGS_PTAX_MENSAL = 3696
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados?formato=json&dataInicial={}&dataFinal={}"

# Arquivo diário de preços da B3 (BVBG.086). Só existe a partir de jan/2018.
URL_B3_PRECOS = "https://www.b3.com.br/pesquisapregao/download?filelist=PR{}.zip"
INICIO_FUTUROS = "2018-01"
PASTA_FUTUROS = DADOS_BRUTOS / "b3_dol"

# Horizonte do hedge em meses: o futuro do fim do mês t é casado com a PTAX
# do fim do mês t + HORIZONTE_HEDGE. O DOL liquida pela PTAX do último dia útil
# do mês ANTERIOR ao vencimento, então o contrato usado é o que vence em
# t + HORIZONTE_HEDGE + 1 (ex.: fim de janeiro, horizonte 3 -> contrato de maio,
# que paga a PTAX de fim de abril).
HORIZONTE_HEDGE = 3

# O DOL é cotado em R$ por US$ 1.000
COTACAO_POR = 1000

# Planilha do dólar futuro desde 2006 (extraída dos BDIs da B3, obtida pelo Bernardo).
# Se este arquivo existir, o passo 2 usa a planilha e não baixa nada da B3.
ARQUIVO_FUTUROS_PLANILHA = DADOS_BRUTOS / "dolar_futuro_t4_bdi_a_partir_2006-07.xlsx"

# PTAX venda diária (para pegar a PTAX exata do dia da liquidação)
SGS_PTAX_DIARIA = 1

# Tamanho do contrato cheio de dólar futuro (DOL): US$ 50.000
TAMANHO_CONTRATO_USD = 50_000

# Empresa simulada (passos 5 a 7): IMPORTADORA. Todo mês t fecha uma compra que paga
# em t + 3 e, no mesmo dia, compra 1 contrato de dólar futuro (US$ 50 mil) para travar o câmbio.
LADO_EMPRESA = "importador"   # "importador" ou "exportador"
EXPOSICAO_USD = TAMANHO_CONTRATO_USD

# Índice de incerteza: EPU Brasil de Baker, Bloom e Davis (policyuncertainty.com), gratuito.
URL_EPU = "https://www.policyuncertainty.com/media/Brazil_Policy_Uncertainty_Data.xlsx"
ARQUIVO_EPU = DADOS_BRUTOS / "Brazil_Policy_Uncertainty_Data.xlsx"

# Mês de incerteza alta = acima deste percentil do índice nos meses da amostra
# do hedge (0.80 = os 20% de meses mais incertos). Atenção: o percentil usa a
# amostra inteira, então não é uma regra ex ante.
PERCENTIL_INCERTEZA_ALTA = 0.80

# Limiar do índice (EPU) acima do qual o mês é de "incerteza alta". Este valor é só um
# padrão: o main.py (passo 4) o recalcula a partir de PERCENTIL_INCERTEZA_ALTA.
LIMIAR_INCERTEZA = 110

# Defasagens do erro-padrão de Newey-West (cohorts de 3 meses se sobrepõem).
# Cohorts vizinhos compartilham h - 1 = 2 meses, então os resíduos são MA(2); L = h = 3
# cobre isso com um lag de folga.
LAGS_NEWEY_WEST = 3

# Robustez: meses excluídos no teste "sem a pandemia"
PERIODO_PANDEMIA = ("2020-01", "2020-12")

# Episódios de crise, pelo mês em que o hedge é contratado (início, fim)
CRISES = {
    "Crise financeira global": ("2008-09", "2009-03"),
    "Recessão e impeachment": ("2015-01", "2016-08"),
    "Pandemia": ("2020-02", "2020-12"),
}

# Gráficos
COR_PRINCIPAL = "#282f6b"   # azul escuro
COR_SECUNDARIA = "#e8730c"  # laranja
COR_TERCIARIA = "#1b998b"   # verde-água
COR_TEXTO = "#3d3d3d"
COR_GRADE = "#d9d9d9"