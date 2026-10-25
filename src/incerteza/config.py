"""
Configurações do projeto: caminhos, URLs, termos e parâmetros do indicador.
"""

from dataclasses import dataclass
from pathlib import Path

# Caminhos
RAIZ = Path(__file__).resolve().parents[2]          # pasta do projeto
DADOS_BRUTOS = RAIZ / "data" / "raw"                # downloads (cache)
DADOS_PROCESSADOS = RAIZ / "data" / "processed"     # séries prontas
FIGURAS = RAIZ / "figuras"                          # gráficos exportados

ARQUIVO_ATAS = DADOS_BRUTOS / "atas_copom.csv"
ARQUIVO_FGV = DADOS_BRUTOS / "xgdvConsulta.csv"     # export do FGV Data (opcional)

# Fontes de dados (Banco Central)

URL_LISTA_ATAS = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas?quantidade=9999"
URL_DETALHE_ATA = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas_detalhes?nro_reuniao={}"
URL_OLINDA = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"

# Faixas de formato das atas: até a 199 e a partir da 232 o texto vem em HTML;
# entre a 200 e a 231 só existe o PDF.
ATA_PDF_INICIO, ATA_PDF_FIM = 200, 231

# Componente textual (substitui os jornais do IIE-Br Mídia)
TERMOS_INCERTEZA = r"(incerteza|incerto|risco|volatilidade|imprevisível|balanço de riscos)"
TERMOS_ECONOMIA = r"(inflação|atividade|juros|selic|política monetária|expectativas)"

# Fórmula do IIE-Br
PESO_TEXTO = 0.8
PESO_EXPECTATIVAS = 0.2
JANELA_REFERENCIA = ("2006-01", "2015-12")  # média 100 / desvio 10 neste período
MEDIA_BASE, DESVIO_BASE = 100, 10

JANELA_CV_MESES = 12      # janela móvel do CV no modo "temporal"
HORIZONTE_MESES = 12      # horizonte das expectativas (12 meses à frente)
DIA_COLETA = 15           # o IIE-Br usa a coleta mais próxima do dia 15


# Modos de cálculo
@dataclass(frozen=True)
class Opcoes:
    """Liga/desliga cada correção em relação ao notebook original."""

    nome: str
    limpar_html: bool               # remove tags e converte &ccedil; -> ç antes de contar palavras
    padronizar_componentes: bool    # z-score de cada componente ANTES de ponderar 0,8/0,2
    dispersao: str                  # "temporal" (original) ou "entre_analistas" (DesvioPadrao/Mediana)
    horizonte_fixo: bool            # escolhe o horizonte ~12m de forma explícita


# Reproduz o notebook da Análise Macro exatamente como está
ORIGINAL = Opcoes(
    nome="original",
    limpar_html=False,
    padronizar_componentes=False,
    dispersao="temporal",
    horizonte_fixo=False,
)

# Versão com as correções descritas no README
CORRIGIDO = Opcoes(
    nome="corrigido",
    limpar_html=True,
    padronizar_componentes=True,
    dispersao="entre_analistas",
    horizonte_fixo=True,
)

MODOS = {"original": ORIGINAL, "corrigido": CORRIGIDO}

# Câmbio: PTAX e dólar futuro (trabalho de hedge)
# Modo do indicador de incerteza usado na base do hedge
MODO_TRABALHO = "corrigido"

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

# Empresa simulada e análise (passos 6 e 7)
# A empresa é IMPORTADORA: todo mês t fecha uma compra de US$ EXPOSICAO_USD
# que paga em t + 3 e, no mesmo dia, compra dólar futuro para travar o câmbio.
LADO_EMPRESA = "importador"   # "importador" ou "exportador"
EXPOSICAO_USD = 1_000_000     # US$ por mês (só muda a escala do resultado em R$)

# Meses de "incerteza alta": acima deste limiar do índice.
# 110 = 1 desvio-padrão acima da média de 2006-2015. Como a escala do índice
# foi fixada em 2006-2015, o limiar é definido ANTES de olhar a amostra do
# hedge (2018 em diante), como o resumo de Fama pede ("fixado ex ante").
LIMIAR_INCERTEZA = 110

# Defasagens do erro-padrão de Newey-West (cohorts de 3 meses se sobrepõem)
LAGS_NEWEY_WEST = 3

# Robustez: meses excluídos no teste "sem a pandemia"
PERIODO_PANDEMIA = ("2020-01", "2020-12")

# Gráficos
COR_PRINCIPAL = "#282f6b"   # azul escuro
COR_SECUNDARIA = "#e8730c"  # laranja
COR_TERCIARIA = "#1b998b"   # verde-água
COR_TEXTO = "#3d3d3d"
COR_GRADE = "#d9d9d9"
