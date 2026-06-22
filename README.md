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
