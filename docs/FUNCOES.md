# Entendendo o `src/main.py`


## O que o programa faz?

Ele **baixa dados de chuva e temperatura** de 6 cidades de Pernambuco, **calcula um índice de seca (SPI)** e **descobre os períodos de seca** de cada cidade. No final, salva tudo em arquivos `.csv`

```
1. Baixar dados da API Open-Meteo
2. Limpar e juntar os dados
3. Transformar dados diários em mensais
4. Calcular o índice de seca (SPI)
5. Encontrar os períodos de seca
6. Salvar tudo em CSV
```

A função `main()` (no final do arquivo) é quem chama todas as outras nessa ordem

---

## Configurações do topo do arquivo

Antes das funções, o código define algumas "constantes":

- **`MUNICIPIOS`** as 6 cidades com sua latitude, longitude e região.
- **`VARIAVEIS`** o que pedimos para a API: chuva, temperatura, evaporação.
- **`RENOMEAR`** troca os nomes técnicos da API por nomes mais fáceis (ex: precipitation_sum vira precipitacao_mm).
- **`DATA_INICIO` / `DATA_FIM`** o período coletado (de 1970 até hoje).
- **`LIMIAR_SECA`, `SPI_SEVERA`, `SPI_EXTREMA`** valores de SPI que definem se a seca é moderada, severa ou extrema.

---

## As funções, passo a passo

### Preparação

| Função | O que faz |
|--------|-----------|
| `criar_diretorios()` | Cria as pastas data/raw e data/processed se não existirem |
| `dados_ja_existem()` | Verifica se já baixamos os dados antes, para não baixar de novo |

### Coleta dos dados

| Função | O que faz |
|--------|-----------|
| `coletar_municipio(...)` | Baixa os dados de **uma** cidade. Se der erro, tenta algumas vezes antes de desistir. Retorna um DataFrame |
| `coletar_todos_municipios(...)` | Repete a função acima para **todas** as cidades e salva um CSV bruto de cada uma |

### Limpeza e agregação

| Função | O que faz |
|--------|-----------|
| `interpolar_lacunas(...)` | Preenche pequenos buracos nos dados (dias sem informação), estimando os valores que faltam, e junta todas as cidades em uma tabela só |
| `agregar_mensal(...)` | Junta os dados diários em mensais (soma a chuva do mês, tira a média da temperatura, etc.). O SPI trabalha com dados mensais |

### Cálculo do SPI (índice de seca)

| Função | O que faz |
|--------|-----------|
| `calcular_spi(...)` | Calcula o índice SPI de uma cidade. Valor negativo = seca |
| `calcular_spi_todos_municipios(...)` | Calcula o SPI de 3 meses e de 12 meses para cada cidade |

### Encontrando os períodos de seca

| Função | O que faz |
|--------|-----------|
| `adicionar_evento(...)` | Guarda um período de seca encontrado (início, fim, duração) e diz se foi moderada, severa ou extrema, conforme o SPI mínimo |
| `identificar_secas(...)` | Olha o SPI de uma cidade ao longo do tempo e marca os períodos contínuos de seca |
| `identificar_secas_todos_municipios(...)` | Faz isso para todas as cidades e junta tudo numa tabela só |

### Salvar e mostrar resultados

| Função | O que faz |
|--------|-----------|
| `salvar_resultados(...)` | Grava todos os CSVs finais na pasta data/processed |
| `mostrar_resumo(...)` | Joga no terminal um resumo rápido (chuva total, temperatura média, secas encontradas) |
| `main()` | Chama as funções na ordem certa |
