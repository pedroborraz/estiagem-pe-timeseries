"""
Coleta dados historicos da API Open-Meteo, calcula o
Standardized Precipitation Index (SPI) e identifica eventos de seca

Fluxo:
1. Coletar dados diarios via Open-Meteo (1970 ate hoje)
2. Interpolar pequenas lacunas na serie diaria
3. Agregar para escala mensal
4. Calcular SPI-3 e SPI-12 por municipio
5. Identificar e classificar eventos de seca
6. Salvar resultados em CSV
"""

from datetime import date
from pathlib import Path
import time
import pandas as pd
import requests
from scipy.stats import gamma as dist_gamma
from spei import spi as spei_spi

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

MUNICIPIOS = {
    "Recife": {"lat": -8.0539, "lon": -34.8811, "mesoregiao": "Metropolitana"},
    "Caruaru": {"lat": -8.2756, "lon": -35.9764, "mesoregiao": "Agreste"},
    "Garanhuns": {"lat": -8.8878, "lon": -36.4965, "mesoregiao": "Agreste Meridional"},
    "Serra Talhada": {"lat": -7.9855, "lon": -38.2950, "mesoregiao": "Sertao"},
    "Salgueiro": {"lat": -8.0731, "lon": -39.1248, "mesoregiao": "Sertao Central"},
    "Petrolina": {"lat": -9.3891, "lon": -40.5027, "mesoregiao": "Sao Francisco"},
}

VARIAVEIS = [
    "precipitation_sum",
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "et0_fao_evapotranspiration",
]

RENOMEAR = {
    "precipitation_sum": "precipitacao_mm",
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "temperature_2m_mean": "temp_media_c",
    "et0_fao_evapotranspiration": "evapo_mm",
}

COLS_NUMERICAS = list(RENOMEAR.values())

DATA_INICIO = "1970-01-01"
DATA_FIM = date.today().isoformat()

LIMIAR_CHUVA_MM = 1.0  # abaixo disso, o dia conta como sem chuva
LIMIAR_SECA = -1.0  # SPI <= -1.0: seca moderada
SPI_SEVERA = -1.5
SPI_EXTREMA = -2.0


def criar_diretorios():
    """Garante que as pastas de dados existam antes de qualquer operacao"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def dados_ja_existem():
    """Verifica se os CSVs brutos ja foram coletados"""
    arquivos = list(RAW_DIR.glob("*_diario.csv"))
    return len(arquivos) >= len(MUNICIPIOS)


def coletar_municipio(nome, lat, lon):
    """
    Busca dados diarios da Open-Meteo para um municipio
    Retorna um DataFrame com indice de datas ou DataFrame vazio em caso de falha
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": DATA_INICIO,
        "end_date": DATA_FIM,
        "daily": ",".join(VARIAVEIS),
        "timezone": "America/Recife",
    }

    max_tentativas = 6
    for tentativa in range(max_tentativas):
        try:
            resp = requests.get(url, params=params, timeout=60)

            # 429 = limite de requisicoes da API, espera um pouco e tenta de novo
            if resp.status_code == 429:
                espera = 6 * (tentativa + 1)
                print(f"  {nome}: limite da API atingido, aguardando {espera}s...")
                time.sleep(espera)
                continue

            resp.raise_for_status()

            df = pd.DataFrame(resp.json()["daily"])
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time").rename_axis("data")
            df = df.rename(columns=RENOMEAR)
            df["municipio"] = nome

            print(f"  {nome}: {len(df)} dias ({df.index.min().date()} ate {df.index.max().date()})")
            return df

        except requests.exceptions.Timeout:
            print(f"  {nome}: timeout na tentativa {tentativa + 1}/{max_tentativas}")

        except requests.exceptions.RequestException as exc:
            print(f"  {nome}: erro na requisicao - {exc}")
            break

    print(f"  {nome}: falhou apos {max_tentativas} tentativas")
    return pd.DataFrame()


def coletar_todos_municipios():
    """
    Coleta dados de todos os municipios, salva CSVs brutos e retorna
    um dicionario {nome: DataFrame} com os municipios bem-sucedidos
    """
    dados = {}
    print(f"Coletando dados: {DATA_INICIO} -> {DATA_FIM}\n")

    for nome, info in MUNICIPIOS.items():
        df = coletar_municipio(nome, info["lat"], info["lon"])
        if not df.empty:
            dados[nome] = df
            arquivo = RAW_DIR / f"{nome.replace(' ', '_').lower()}_diario.csv"
            df.to_csv(arquivo)

        time.sleep(6)  # pausa entre municipios para nao estourar o limite da API

    print(f"\nMunicipios coletados: {len(dados)}/{len(MUNICIPIOS)}")
    return dados


def interpolar_lacunas(dados):
    """
    Preenche lacunas curtas nas series diarias por interpolacao temporal
    e retorna um DataFrame unico com todos os municipios
    A Open-Meteo Archive e uma serie completa, sem datas faltantes.
    A interpolacao e defensiva, caso uma coleta futura retorne lacunas
    no maximo 7 dias consecutivos sao preenchidos
    """
    frames = []
    for df in dados.values():
        df = df.copy()
        df[COLS_NUMERICAS] = df[COLS_NUMERICAS].interpolate(
            method="time", limit=7, limit_direction="both"
        )
        frames.append(df)

    return pd.concat(frames).sort_index()


def agregar_mensal(df_diario):
    """Agrega o DataFrame diario para escala mensal (uma linha por mes e municipio)"""
    df = df_diario.copy()
    df["mes"] = df.index.to_period("M").to_timestamp()
    df["sem_chuva"] = df["precipitacao_mm"] < LIMIAR_CHUVA_MM
    df["n_dias"] = df["precipitacao_mm"].notna()

    mensal = df.groupby(["mes", "municipio"], as_index=False).agg(
        {
            "precipitacao_mm": "sum",
            "temp_max_c": "mean",
            "temp_min_c": "mean",
            "temp_media_c": "mean",
            "evapo_mm": "sum",
            "sem_chuva": "sum",
            "n_dias": "sum",
        }
    )

    mensal = mensal.rename(
        columns={"mes": "data", "precipitacao_mm": "precip_mm", "sem_chuva": "dias_sem_chuva"}
    )
    return mensal.round(2)


def calcular_spi(serie_mensal, escala=3):
    """
    Calcula o SPI de uma serie de precipitacao mensal usando o pacote spei
    O pacote acumula a precipitacao em janela de escala meses, ajusta a
    distribuicao Gama separadamente para cada mes do ano (apenas observacoes
    daquele mes), corrige a probabilidade de precipitacao zero e transforma o
    resultado para a normal padrao. Valores negativos indicam deficit (seca)
    Os primeiros `escala - 1` meses retornam NaN por falta de janela completa
    """
    spi = spei_spi(serie_mensal, dist=dist_gamma, timescale=escala, fit_freq="MS",
                   fit_window=0, prob_zero=True)
    spi.name = f"SPI-{escala}"

    # Em meses muito secos de regioes aridas (precip ~0) o ajuste da Gama retorna valores absurdos.
    # |SPI|>3.5 nao tem sentido fisico, limita sem descartar o pico da seca
    return spi.clip(-3.5, 3.5)


def calcular_spi_todos_municipios(df_mensal):
    """Calcula SPI-3 e SPI-12 por municipio"""
    resultados = {}

    for municipio in df_mensal["municipio"].unique():
        dados_mun = df_mensal[df_mensal["municipio"] == municipio]
        precip = dados_mun.set_index("data")["precip_mm"].sort_index()

        resultados[municipio] = pd.DataFrame(
            {
                "precip_mm": precip,
                "spi3": calcular_spi(precip, escala=3),
                "spi12": calcular_spi(precip, escala=12),
            }
        )

    return resultados


def adicionar_evento(eventos, municipio, datas, valores, em_andamento):
    """
    Acrescenta um evento de seca a lista de resultados, classificando-o
    pelo SPI minimo, blocos com menos de 2 meses sao ignorados
    """
    if len(datas) < 2:
        return

    spi_min = round(min(valores), 2)

    if spi_min <= SPI_EXTREMA:
        classificacao = "Seca Extrema"
    elif spi_min <= SPI_SEVERA:
        classificacao = "Seca Severa"
    else:
        classificacao = "Seca Moderada"

    if em_andamento:
        classificacao += " (em andamento)"

    eventos.append(
        {
            "municipio": municipio,
            "inicio": datas[0],
            "fim": datas[-1],
            "duracao_meses": len(datas),
            "spi_minimo": spi_min,
            "classificacao": classificacao,
        }
    )


def identificar_secas(df_spi, municipio):
    """Identifica blocos contiguos de SPI abaixo do limiar como eventos de seca"""
    spi = df_spi["spi3"].dropna()
    eventos = []
    datas = []
    valores = []

    for data, valor in spi.items():
        if valor <= LIMIAR_SECA:
            datas.append(data)
            valores.append(valor)
        else:
            adicionar_evento(eventos, municipio, datas, valores, em_andamento=False)
            datas = []
            valores = []

    # se a serie termina em seca, o ultimo evento ainda esta em andamento
    adicionar_evento(eventos, municipio, datas, valores, em_andamento=True)

    return pd.DataFrame(eventos)


def identificar_secas_todos_municipios(resultados_spi):
    """Concatena os eventos de seca de todos os municipios em um unico DataFrame"""
    frames = []
    for municipio in MUNICIPIOS:
        if municipio in resultados_spi:
            frames.append(identificar_secas(resultados_spi[municipio], municipio))

    df_eventos = pd.concat(frames, ignore_index=True)
    df_eventos[["inicio", "fim"]] = df_eventos[["inicio", "fim"]].apply(pd.to_datetime)
    return df_eventos


def salvar_resultados(resultados_spi, df_diario, df_mensal, df_eventos):
    """Salva todos os arquivos processados"""
    df_diario.to_csv(PROCESSED_DIR / "dados_diarios_limpos.csv")
    df_mensal.to_csv(PROCESSED_DIR / "dados_mensais.csv", index=False)
    df_eventos.to_csv(PROCESSED_DIR / "eventos_seca.csv", index=False)

    for municipio, df_spi in resultados_spi.items():
        nome_arquivo = municipio.replace(" ", "_").lower()
        df_spi.to_csv(PROCESSED_DIR / f"spi_{nome_arquivo}.csv")


def mostrar_resumo(df_diario, df_eventos):
    """Exibe um resumo do processamento para conferencia rapida"""
    resumo = (
        df_diario.groupby("municipio")
        .agg(
            dias_registrados=("precipitacao_mm", "count"),
            precipitacao_total_mm=("precipitacao_mm", "sum"),
            temperatura_media_c=("temp_media_c", "mean"),
            evapotranspiracao_media_mm=("evapo_mm", "mean"),
        )
        .round(2)
        .reset_index()
    )

    print("\nResumo por municipio")
    print(resumo.to_string(index=False))

    if not df_eventos.empty:
        total = len(df_eventos)
        print(f"\nEventos de seca identificados ({total} no total - exibindo primeiros 10)")
        print(df_eventos.head(10).to_string(index=False))


def main():
    criar_diretorios()

    if dados_ja_existem():
        print("Dados brutos ja existem, pulando coleta da API...")
        dados_brutos = {}
        for arquivo in sorted(RAW_DIR.glob("*_diario.csv")):
            nome = arquivo.stem.replace("_diario", "").replace("_", " ").title()
            dados_brutos[nome] = pd.read_csv(arquivo, index_col="data", parse_dates=True)
    else:
        print("COLETA DE DADOS")
        dados_brutos = coletar_todos_municipios()

    if not dados_brutos:
        print("Nenhum municipio coletado com sucesso!")
        return

    print("\nLIMPEZA E AGREGACAO")
    df_diario = interpolar_lacunas(dados_brutos)
    df_mensal = agregar_mensal(df_diario)

    print("\nCALCULO DO SPI")
    resultados_spi = calcular_spi_todos_municipios(df_mensal)
    df_eventos = identificar_secas_todos_municipios(resultados_spi)

    salvar_resultados(resultados_spi, df_diario, df_mensal, df_eventos)
    print(f"\nDados brutos: {RAW_DIR}")
    print(f"Dados processados: {PROCESSED_DIR}")

    mostrar_resumo(df_diario, df_eventos)


if __name__ == "__main__":
    main()
