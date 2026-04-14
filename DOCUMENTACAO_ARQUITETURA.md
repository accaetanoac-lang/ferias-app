# Arquitetura e Estrutura do Repositório

## Visão Geral do Sistema
Este repositório é um sistema de suporte à gestão de férias da Green Máquinas. Ele contém componentes para:

- Dashboard de férias em Streamlit (`app.py`)
- Motor de validação de solicitações e processamento de CSVs (`ferias.py`)
- Script auxiliar de monitoramento em PowerShell (`monitoramento_ferias.ps1`)
- Base local de solicitações de férias (`base_ferias.csv`)
- Formato de dados de planejamento em Excel (`ferias_equipe.xlsx`)

## Estrutura de arquivos

- `.venv/`
  - Ambiente virtual Python do projeto
- `app.py`
  - Dashboard Streamlit principal
  - Usa `pandas` para carregar e gravar `base_ferias.csv`
  - Exibe a planilha local e permite registrar novos lançamentos de férias
- `ferias.py`
  - Motor de validação de regras de férias da equipe
  - Processa arquivos CSV em `respostas_forms/`
  - Verifica regras de safra, início de férias e feriados nacionais
  - Gera `relatorio_final_ferias.csv`
- `monitoramento_ferias.ps1`
  - Script PowerShell para mostrar equipe e gerar mensagem de envio por WhatsApp
- `base_ferias.csv`
  - Arquivo local de dados de solicitações de férias gerado pelo `app.py`
- `ferias_equipe.xlsx`
  - Planilha Excel de exemplo com colunas de controle de férias
- `DOCUMENTACAO_ARQUITETURA.md`
  - Este arquivo de documentação

## Componentes e responsabilidades

### `app.py`
Responsável pela interface: 
- Configura a página Streamlit
- Mostra o inventário de técnicos
- Carrega e salva `base_ferias.csv`
- Possui abas para:
  - `Visão Geral`: exibe a planilha local de solicitações e alerta sobre o período de safra
  - `Lançar Férias`: permite registrar manualmente novas solicitações

### `ferias.py`
Responsável pelo processamento e validação de dados:
- Define o dicionário `EQUIPE` com cargos e usuários
- Usa `holidays.BR()` para detectar feriados do Brasil
- Valida regras de safra (bloqueio de 16/07 a 31/08)
- Valida início de férias e véspera de feriado
- Processa CSVs na pasta `respostas_forms/`
- Gera relatório final em CSV

### `monitoramento_ferias.ps1`
Responsável por ações de suporte no Windows:
- Exibe a lista de colaboradores
- Gera texto de envio para WhatsApp
- Simula opções de menu para ações de monitoramento

## Fluxo de dados

1. O usuário acessa `app.py` no Streamlit.
2. O dashboard carrega `base_ferias.csv` e exibe as solicitações existentes.
3. Ao lançar uma nova solicitação, o app grava diretamente em `base_ferias.csv`.
4. Para processar respostas de formulário externo, `ferias.py` lê arquivos `.csv` em `respostas_forms/`.
5. O resultado do processamento é exportado como `relatorio_final_ferias.csv`.

## Dependências do projeto

- Python 3.12
- pandas
- streamlit
- holidays

## Como rodar

1. Ative o ambiente virtual
2. Instale dependências
3. Execute o dashboard Streamlit:

```powershell
.venv\Scripts\streamlit.exe run app.py
```

4. Para processar respostas de formulário:

```powershell
python ferias.py
```

## Observações para o outro dev

- O `app.py` é o componente front-end principal hoje.
- O `ferias.py` contém lógica de negócio e pode ser integrado ao dashboard posteriormente.
- A planilha `base_ferias.csv` é a fonte local persistente para lançamentos manuais.
- O projeto está preparado para evoluir com abas adicionais e integrações de Forms.
