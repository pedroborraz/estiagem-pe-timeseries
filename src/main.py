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

from __future__ import annotations
from datetime import date
from pathlib import Path
import time
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from scipy.stats import gamma as dist_gamma
from spei import spi as spei_spi
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

MUNICIPIOS: dict[str, dict[str, float | str]] = {
    "Recife":        {"lat": -8.0539, "lon": -34.8811, "mesoregiao": "Metropolitana"},
    "Caruaru":       {"lat": -8.2756, "lon": -35.9764, "mesoregiao": "Agreste"},
    "Garanhuns":     {"lat": -8.8878, "lon": -36.4965, "mesoregiao": "Agreste Meridional"},
    "Serra Talhada": {"lat": -7.9855, "lon": -38.2950, "mesoregiao": "Sertao"},
    "Salgueiro":     {"lat": -8.0731, "lon": -39.1248, "mesoregiao": "Sertao Central"},
    "Petrolina":     {"lat": -9.3891, "lon": -40.5027, "mesoregiao": "Sao Francisco"},
}

VARIAVEIS: list[str] = [
    "precipitation_sum",
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "et0_fao_evapotranspiration",
]

RENOMEAR: dict[str, str] = {
    "precipitation_sum":          "precipitacao_mm",
    "temperature_2m_max":         "temp_max_c",
    "temperature_2m_min":         "temp_min_c",
    "temperature_2m_mean":        "temp_media_c",
    "et0_fao_evapotranspiration": "evapo_mm",
}

COLS_NUMERICAS: list[str] = list(RENOMEAR.values())

DATA_INICIO = "1970-01-01"
DATA_FIM = date.today().isoformat()

LIMIAR_CHUVA_MM = 1.0   # abaixo disso, o dia conta como sem chuva
LIMIAR_SECA = -1.0      # SPI <= -1.0: seca moderada
SPI_SEVERA = -1.5
SPI_EXTREMA = -2.0


def criar_diretorios() -> None:
    """Garante que as pastas de dados existam antes de qualquer operacao"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def criar_sessao_http() -> requests.Session:
    """Cria uma sessao HTTP com retry automatico e backoff exponencial para erros 429 e 5xx"""
    retry = Retry(
        total=6,
        backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = "Mozilla/5.0"
    return session


def dados_ja_existem() -> bool:
    """Verifica se os CSVs brutos ja foram coletados"""
    arquivos = list(RAW_DIR.glob("*_diario.csv"))
    return len(arquivos) >= len(MUNICIPIOS)


def coletar_municipio(
    nome: str,
    lat: float,
    lon: float,
    session: requests.Session,
    variaveis: list[str] = VARIAVEIS,
    data_inicio: str = DATA_INICIO,
    data_fim: str = DATA_FIM,
    max_tentativas: int = 4,
    pausa_429: int = 6,
) -> pd.DataFrame:
    """
    Busca dados diarios da Open-Meteo para um municipio

    Retorna um DataFrame com indice de datas ou DataFrame vazio em caso de falha
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": data_inicio,
        "end_date":   data_fim,
        "daily":      ",".join(variaveis),
        "timezone":   "America/Recife",
    }

    for tentativa in range(max_tentativas):
        try:
            resp = session.get(url, params=params, timeout=60)

            if resp.status_code == 429:
                try:
                    motivo = resp.json().get("reason", "limite atingido")
                except ValueError:
                    motivo = "limite atingido"

                espera = pausa_429 * (tentativa + 1)
                print(f"  {nome}: 429 - {motivo} | aguardando {espera}s...")
                time.sleep(espera)
                continue

            resp.raise_for_status()

            df = pd.DataFrame(resp.json()["daily"])
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time").rename_axis("data")
            df = df.rename(columns={k: v for k, v in RENOMEAR.items() if k in df.columns})
            df["municipio"] = nome

            print(
                f"  {nome:16s} | {len(df):,} dias | "
                f"{df.index.min().date()} -> {df.index.max().date()}"
            )
            return df

        except requests.exceptions.Timeout:
            print(f"  {nome}: timeout na tentativa {tentativa + 1}/{max_tentativas}")

        except requests.exceptions.RequestException as exc:
            # erro permanente (SSL, DNS): nao adianta repetir
            print(f"  {nome}: erro na requisicao - {exc}")
            break

    print(f"  {nome}: falhou apos {max_tentativas} tentativas")
    return pd.DataFrame()


def coletar_todos_municipios(
    municipios: dict[str, dict[str, float | str]] = MUNICIPIOS,
    variaveis: list[str] = VARIAVEIS,
    data_inicio: str = DATA_INICIO,
    data_fim: str = DATA_FIM,
    pausa_entre_municipios: int = 6,
) -> dict[str, pd.DataFrame]:
    """
    Coleta dados de todos os municipios, salva CSVs brutos e retorna
    um dicionario {nome: DataFrame} com os municipios bem-sucedidos
    """
    session = criar_sessao_http()
    dados: dict[str, pd.DataFrame] = {}

    print(f"Coletando dados: {data_inicio} -> {data_fim}\n")

    for nome, info in municipios.items():
        df = coletar_municipio(
            nome=nome,
            lat=float(info["lat"]),
            lon=float(info["lon"]),
            session=session,
            variaveis=variaveis,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        if not df.empty:
            dados[nome] = df
            arquivo = RAW_DIR / f"{nome.replace(' ', '_').lower()}_diario.csv"
            df.to_csv(arquivo)

        time.sleep(pausa_entre_municipios)

    print(f"\nMunicipios coletados: {len(dados)}/{len(municipios)}")
    return dados


def interpolar_lacunas(
    dados: dict[str, pd.DataFrame],
    colunas: list[str] = COLS_NUMERICAS,
    limite: int = 7,
) -> pd.DataFrame:
    """
    Preenche lacunas curtas nas series diarias por interpolacao temporal
    e retorna um DataFrame unico com todos os municipios

    A Open-Meteo Archive (reanalise ERA5) e uma serie completa, sem datas
    faltantes. A interpolacao e defensiva, caso uma coleta futura retorne
    lacunas; `limite` e o numero maximo de dias consecutivos a preencher
    """
    frames: list[pd.DataFrame] = []

    for df in dados.values():
        df_c = df.copy()
        df_c[colunas] = df_c[colunas].interpolate(
            method="time", limit=limite, limit_direction="both"
        )
        frames.append(df_c)

    return pd.concat(frames).sort_index() if frames else pd.DataFrame()


def agregar_mensal(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega o DataFrame diario para escala mensal por municipio (MultiIndex data, municipio)"""
    mensal = (
        df.copy()
        .assign(periodo=lambda d: d.index.to_period("M"))
        .groupby(["periodo", "municipio"])
        .agg(
            precip_mm      =("precipitacao_mm", "sum"),
            temp_max_c     =("temp_max_c",      "mean"),
            temp_min_c     =("temp_min_c",      "mean"),
            temp_media_c   =("temp_media_c",    "mean"),
            evapo_mm       =("evapo_mm",        "sum"),
            dias_sem_chuva =("precipitacao_mm", lambda x: (x < LIMIAR_CHUVA_MM).sum()),
            n_dias         =("precipitacao_mm", "count"),
        )
        .round(2)
    )

    # Period -> Timestamp para exportar em CSV
    mensal.index = mensal.index.set_levels(
        mensal.index.levels[0].to_timestamp(), level=0
    )
    mensal.index.names = ["data", "municipio"]
    return mensal


def calcular_spi(serie_mensal: pd.Series, escala: int = 3) -> pd.Series:
    """
    Calcula o SPI de uma serie de precipitacao mensal usando o pacote spei

    O pacote acumula a precipitacao em janela de escala meses, ajusta a
    distribuicao Gama separadamente para cada mes do ano (apenas observacoes
    daquele mes), corrige a probabilidade de precipitacao zero e transforma o
    resultado para a normal padrao. Valores negativos indicam deficit (seca)
    Os primeiros `escala - 1` meses retornam NaN por falta de janela completa

    Referencia: Lloyd-Hughes & Saunders (2002), Int. J. Climatology, 22,
    1571-1592. DOI: 10.1002/joc.846
    """
    spi = spei_spi(
        serie_mensal,
        dist=dist_gamma,
        timescale=escala,
        fit_freq="MS",
        fit_window=0,
        prob_zero=True,
    )
    spi.name = f"SPI-{escala}"

    # Em meses muito secos de regioes aridas (precip ~0) o ajuste da Gama
    # degenera e a PPF retorna valores absurdos. Como o SPI e normal padronizado,
    # |SPI|>3.5 nao tem sentido fisico, limita sem descartar o pico da seca
    return spi.clip(-3.5, 3.5)


def calcular_spi_todos_municipios(df_mensal: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Calcula SPI-3 e SPI-12 por municipio"""
    resultados: dict[str, pd.DataFrame] = {}

    for municipio in df_mensal.index.get_level_values("municipio").unique():
        precip = df_mensal.xs(municipio, level="municipio")["precip_mm"].sort_index()
        resultados[municipio] = pd.DataFrame(
            {
                "precip_mm": precip,
                "spi3":      calcular_spi(precip, escala=3),
                "spi12":     calcular_spi(precip, escala=12),
            }
        )

    return resultados


def _classificar_seca(spi_min: float, em_andamento: bool) -> str:
    """Retorna o rotulo de classificacao de um evento de seca"""
    sufixo = " (em andamento)" if em_andamento else ""

    if spi_min <= SPI_EXTREMA:
        return f"Seca Extrema{sufixo}"
    if spi_min <= SPI_SEVERA:
        return f"Seca Severa{sufixo}"
    return f"Seca Moderada{sufixo}"


def _registrar_evento(
    eventos: list[dict],
    spi: pd.Series,
    municipio: str,
    inicio: pd.Timestamp,
    fim: pd.Timestamp,
    em_andamento: bool = False,
) -> None:
    """Acrescenta um evento de seca a lista de resultados"""
    trecho = spi[inicio:fim]
    if len(trecho) < 2:
        return

    spi_min = round(float(trecho.min()), 2)

    eventos.append(
        {
            "municipio":     municipio,
            "inicio":        inicio,
            "fim":           fim,
            "duracao_meses": len(trecho),
            "spi_minimo":    spi_min,
            "classificacao": _classificar_seca(spi_min, em_andamento),
        }
    )


def identificar_secas(
    df_spi: pd.DataFrame,
    municipio: str,
    limiar: float = LIMIAR_SECA,
    col: str = "spi3",
) -> pd.DataFrame:
    """Identifica blocos contiguos de SPI abaixo do limiar como eventos de seca"""
    spi = df_spi[col].dropna()
    eventos: list[dict] = []
    inicio: pd.Timestamp | None = None

    for data, em_seca in (spi <= limiar).items():
        if em_seca and inicio is None:
            inicio = data
        elif not em_seca and inicio is not None:
            fim = spi.index[spi.index.get_loc(data) - 1]
            _registrar_evento(eventos, spi, municipio, inicio, fim)
            inicio = None

    if inicio is not None:
        _registrar_evento(eventos, spi, municipio, inicio, spi.index[-1], em_andamento=True)

    return pd.DataFrame(eventos)


def identificar_secas_todos_municipios(
    resultados_spi: dict[str, pd.DataFrame],
    municipios: dict[str, dict[str, float | str]] = MUNICIPIOS,
    limiar: float = LIMIAR_SECA,
    col: str = "spi3",
) -> pd.DataFrame:
    """Concatena os eventos de seca de todos os municipios em um unico DataFrame"""
    frames = [
        identificar_secas(resultados_spi[nome], nome, limiar=limiar, col=col)
        for nome in municipios
        if nome in resultados_spi
    ]

    if not frames:
        return pd.DataFrame(
            columns=["municipio", "inicio", "fim", "duracao_meses", "spi_minimo", "classificacao"]
        )

    df_eventos = pd.concat(frames, ignore_index=True)
    df_eventos[["inicio", "fim"]] = df_eventos[["inicio", "fim"]].apply(pd.to_datetime)
    return df_eventos


def salvar_resultados(
    resultados_spi: dict[str, pd.DataFrame],
    df_diario: pd.DataFrame,
    df_mensal: pd.DataFrame,
    df_eventos: pd.DataFrame,
    output_dir: Path = PROCESSED_DIR,
) -> None:
    """Salva todos os arquivos processados"""
    output_dir.mkdir(parents=True, exist_ok=True)

    df_diario.to_csv(output_dir / "dados_diarios_limpos.csv")
    df_mensal.to_csv(output_dir / "dados_mensais.csv")
    df_eventos.to_csv(output_dir / "eventos_seca.csv", index=False)

    for municipio, df_spi in resultados_spi.items():
        nome_arquivo = municipio.replace(" ", "_").lower()
        df_spi.to_csv(output_dir / f"spi_{nome_arquivo}.csv")


def mostrar_resumo(df_diario: pd.DataFrame, df_eventos: pd.DataFrame) -> None:
    """Exibe um resumo do processamento para conferencia rapida"""
    resumo = (
        df_diario.groupby("municipio")
        .agg(
            dias_registrados           =("precipitacao_mm", "count"),
            precipitacao_total_mm      =("precipitacao_mm", "sum"),
            temperatura_media_c        =("temp_media_c",    "mean"),
            evapotranspiracao_media_mm =("evapo_mm",        "mean"),
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


def main() -> None:
    criar_diretorios()

    if dados_ja_existem():
        print("Dados brutos ja existem, pulando coleta da API...")
        dados_brutos = {
            f.stem.replace("_diario", "").replace("_", " ").title():
                pd.read_csv(f, index_col="data", parse_dates=True)
            for f in sorted(RAW_DIR.glob("*_diario.csv"))
        }
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
