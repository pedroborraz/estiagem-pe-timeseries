# Projeto de Introdução a Ciência de Dados 2026.1

### Análise temporal de períodos de seca em Pernambuco

A proposta busca explorar informações meteorológicas históricas e atuais para compreender fenômenos como períodos de seca, variações de temperatura e possíveis riscos climáticos para a produção agrícola de subsistência.


#### Participantes:
- Henrique Jales
- Mikael Rodrigues
- Gabriel Lopes
- Pedro Borras Souto


#### Abordagem da coleta de dados:
- APIs de meteorologia (Open-Meteo)
- Possível utilização de APIs do IBGE e dados do INMET, se houver dados relevantes disponíveis


## Conjunto de dados

Dados meteorológicos diários de seis municípios de Pernambuco (Recife, Caruaru, Garanhuns, Serra Talhada, Salgueiro e Petrolina) cobrindo as mesorregiões Metropolitana, Agreste, Sertão e São Francisco, de **1970 até a data de coleta**. A partir dos dados diários são gerados dados processados: série diária limpa, agregação mensal, o **SPI** (Índice Padronizado de Precipitação, escalas de 3 e 12 meses) e uma tabela de eventos de seca classificados por gravidade

### Coleta

Os dados são coletados a partir da **API Archive da Open-Meteo** (ERA5), consultando as coordenadas de cada município para o período de 1970 até hoje. Os dados brutos vão para data/raw/ e, após limpeza, agregação mensal e cálculo do SPI, os resultados vão para data/processed/

### Colunas

**Dados diários** (data/raw/*_diario.csv, data/processed/dados_diarios_limpos.csv):

| Coluna | Descrição | Exemplo |
|---|---|---|
| `data` | Data do registro | `1970-01-01` |
| `precipitacao_mm` | Precipitação acumulada no dia (mm) | `4.1` |
| `temp_max_c` | Temperatura máxima do dia (°C) | `29.6` |
| `temp_min_c` | Temperatura mínima do dia (°C) | `23.7` |
| `temp_media_c` | Temperatura média do dia (°C) | `26.1` |
| `evapo_mm` | Evapotranspiração de referência ET0 FAO (mm) | `4.41` |
| `municipio` | Município do registro | `Recife` |

**Dados mensais** (data/processed/dados_mensais.csv):

| Coluna | Descrição | Exemplo |
|---|---|---|
| `data` | Primeiro dia do mês de referência | `1970-01-01` |
| `municipio` | Município | `Caruaru` |
| `precip_mm` | Precipitação total do mês (mm) | `103.8` |
| `temp_max_c` | Média mensal das máximas (°C) | `29.0` |
| `temp_min_c` | Média mensal das mínimas (°C) | `20.56` |
| `temp_media_c` | Média mensal das médias (°C) | `23.99` |
| `evapo_mm` | Evapotranspiração total do mês (mm) | `138.75` |
| `dias_sem_chuva` | Dias do mês com chuva abaixo de 1 mm | `8` |
| `n_dias` | Dias com registro no mês | `31` |

**SPI por município** (data/processed/spi_*.csv):

| Coluna | Descrição | Exemplo |
|---|---|---|
| `data` | Primeiro dia do mês | `1970-01-01` |
| `precip_mm` | Precipitação total do mês (mm) | `76.4` |
| `spi3` | SPI na escala de 3 meses (curto prazo) | `-1.26` |
| `spi12` | SPI na escala de 12 meses (longo prazo) | `0.85` |

**Eventos de seca** (data/processed/eventos_seca.csv):

| Coluna | Descrição | Exemplo |
|---|---|---|
| `municipio` | Município do evento | `Recife` |
| `inicio` | Mês de início (SPI ≤ -1.0) | `1971-01-01` |
| `fim` | Mês final do evento | `1971-02-01` |
| `duracao_meses` | Duração em meses | `2` |
| `spi_minimo` | Menor SPI no evento (pico da seca) | `-1.26` |
| `classificacao` | Severidade: Moderada, Severa ou Extrema | `Seca Moderada` |

## Como executar

### 1. Criar o ambiente virtual (venv)

Na raiz do projeto, crie e ative um ambiente virtual:

```bash
# Criar a venv
python3 -m venv .venv

# Ativar a venv
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

### 2. Instalar as dependências

Com a venv ativada, instale os pacotes listados em `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 3. Executar o script

```bash
python src/main.py
```

Os dados brutos são salvos em `data/raw/` e os resultados processados em `data/processed/`.
