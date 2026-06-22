# O índice SPI explicado de forma simples

## O que é o SPI?

**SPI** quer dizer *Standardized Precipitation Index* (Índice Padronizado de Precipitação).

Ele responde a uma pergunta simples: **"choveu mais ou menos do que o normal nesta época do ano?"**

- Ele compara a chuva de um período com o histórico daquele local.
- O resultado é um número: **negativo = chuva abaixo do normal (seca)**, **positivo = chuva acima do normal**.
- O **zero** é a média histórica.

Como o número é "padronizado", dá para comparar o sertão com o litoral, mesmo tendo climas bem diferentes.

---

## Como ler os valores

| Valor do SPI | O que significa |
|--------------|-----------------|
| **+2 ou mais** | Muito chuvoso |
| **0** | Normal |
| **−1.0 a −1.5** | Seca moderada |
| **−1.5 a −2.0** | Seca severa |
| **−2.0 ou menos** | Seca extrema |

No código, esses limites estão nas constantes `LIMIAR_SECA`, `SPI_SEVERA` e `SPI_EXTREMA`.

---

## SPI-3 e SPI-12: por que dois?

O SPI depende de **quantos meses** você olha de uma vez:

- **SPI-3** (3 meses) seca de **curto prazo**. Boa para ver impacto na agricultura.
- **SPI-12** (12 meses) seca de **longo prazo**. Boa para ver impacto em rios e reservatórios.

O código calcula os dois em `calcular_spi_todos_municipios(...)`.

---

## Onde isso está no código

1. **`agregar_mensal(...)`** o SPI trabalha por mês, então primeiro juntamos os dados diários em mensais.
2. **`calcular_spi(...)`** faz a conta do SPI usando o pacote `spei`. A gente não calcula a fórmula na mão; o pacote faz isso.
3. **`identificar_secas(...)`** percorre o SPI ao longo do tempo. Sempre que ele fica abaixo de `−1.0` por meses seguidos, isso é registrado como um **evento de seca**.

> O cálculo matemático em si (distribuição Gama, normalização) é feito pela biblioteca `spei`.

---

## Um detalhe do código

Em regiões muito secas, com quase nenhuma chuva, a conta do SPI pode "estourar" e gerar valores sem sentido (tipo −10). Por isso a função `calcular_spi` limita o resultado entre **−3.5 e +3.5**, que é o intervalo que faz sentido na prática.

---
