import pandas as pd
import os
import holidays
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DA EQUIPE ---
EQUIPE = {
    "Adeilson de Oliveira": "Consultor Técnico", "Anderson Lucas Duarte Freitas": "Auxiliar Técnico",
    "Antônio Weslley Santos Batista": "Consultor Técnico", "Clenison de Sousa Soares": "Consultor Técnico",
    "Daniel Mateus Oliveira": "Consultor Técnico", "Dhone Francisco da Silva": "Assist. Técnico Jr",
    "Edilson Ribeiro de Lima Junior": "Consultor Técnico", "Felipe Honorato": "Gestor de Frotas",
    "Gabriel Sousa Vieira": "Auxiliar Técnico", "Geoglenn Jose Lanz Parra": "Consultor Técnico",
    "Igor Matthews Barros Marques": "Consultor Técnico", "Jaime da Silva Coelho": "Assist. Técnico Sr",
    "Jose Augusto Barbosa Neto": "Assistênte Técnico", "Kaio Gabriel Carrêra": "Assistênte Técnico",
    "Leonardo Winicios Simões dos Santos": "Assist. Administrativo", "Lucas Gleub Ribeiro": "Consultor Técnico",
    "Phillip Antonic Persaud": "Consultor Técnico", "Rayan dos Santos Mendes": "Assist. Adm. Serviços",
    "Rócio Diaz Del Pino": "Analista de Garantia", "Jorge William Braga Menezes": "Assist. Técnico Jr",
    "Bruno Caik da Silva Thome": "Assist. Técnico Sr", "Antonio Carlos Caetano": "Gerente de Serviços",
    "Marinilson Mota de Lira": "Supervisor de Serviços"
}

# Inicializa feriados do Brasil para detecção automática
feriados_br = holidays.BR()

# --- 2. MOTOR DE VALIDAÇÃO ---
def validar_regras_green(nome, data_inicio_str, opcao_gozo, dias_especificos=None):
    try:
        # Limpeza simples para evitar espaços extras no nome
        nome = nome.strip() if isinstance(nome, str) else nome
        inicio = datetime.strptime(data_inicio_str, "%d/%m/%Y")
        amanha = inicio + timedelta(days=1)
        
        # Validação de Equipe
        if nome not in EQUIPE:
            return False, f"Funcionário '{nome}' não localizado."

        # Regra de Safra (Bloqueio 16/07 a 31/08)
        dia, mes = inicio.day, inicio.month
        if (mes == 7 and dia > 15) or (mes == 8):
            return False, "Bloqueio de Safra (Julho/Agosto)."

        # Regra CLT (Início proibido em Sexta, Sábado ou Domingo)
        if inicio.weekday() in [4, 5, 6]:
            return False, "Início proibido em sexta ou final de semana."

        # VALIDAÇÃO DE VÉSPERA DE FERIADO (2026/2027...)
        if amanha in feriados_br:
            nome_feriado = feriados_br.get(amanha)
            return False, f"Véspera de feriado: {nome_feriado} ({amanha.strftime('%d/%m/%Y')})."

        # Cálculo de Dias conforme Opção
        mapa_dias = {"b.1": 30, "b.2": 15, "b.3": int(dias_especificos) if dias_especificos else 0}
        dias = mapa_dias.get(opcao_gozo, 0)
        
        if dias == 0:
            return False, "Quantidade de dias inválida para a opção escolhida."

        fim = inicio + timedelta(days=dias - 1)
        retorno = fim + timedelta(days=1)
        
        return True, f"VALIDADO: {dias} dias. Retorno em {retorno.strftime('%d/%m/%Y')}"

    except Exception as e:
        return False, f"Erro nos dados: {str(e)}"

# --- 3. PROCESSADOR DE ARQUIVOS ---
def processar_arquivo_respostas():
    pasta = "respostas_forms"
    
    if not os.path.exists(pasta):
        os.makedirs(pasta)
        print(f"Pasta '{pasta}' criada. Coloque o CSV do Forms lá dentro.")
        return

    arquivos = [f for f in os.listdir(pasta) if f.endswith('.csv')]
    
    if not arquivos:
        print("Aguardando arquivo CSV na pasta 'respostas_forms'...")
        return

    resultados_finais = []

    for arquivo in arquivos:
        print(f"\n--- Analisando: {arquivo} ---")
        caminho = os.path.join(pasta, arquivo)
        # Lendo com encoding para evitar erros de caracteres latinos
        df = pd.read_csv(caminho)
        
        for index, row in df.iterrows():
            dias_solicitados = row.get('Dias', None)
            
            sucesso, msg = validar_regras_green(
                row['Nome'], 
                row['Inicio'], 
                row['Opcao'], 
                dias_solicitados
            )
            
            status_simbolo = "✅" if sucesso else "❌"
            print(f"{status_simbolo} {row['Nome']}: {msg}")

            # Armazena para o relatório final
            resultados_finais.append({
                'Nome': row['Nome'],
                'Status': "APROVADO" if sucesso else "REPROVADO",
                'Mensagem': msg,
                'Arquivo_Origem': arquivo
            })

    # --- 4. GERAÇÃO DO RELATÓRIO DE SAÍDA ---
    if resultados_finais:
        df_resultado = pd.DataFrame(resultados_finais)
        # Salvando em CSV com separador ponto e vírgula para abrir fácil no Excel
        df_resultado.to_csv("relatorio_final_ferias.csv", index=False, sep=';', encoding='latin-1')
        print(f"\n✅ Relatório 'relatorio_final_ferias.csv' gerado com sucesso!")

# --- 5. EXECUÇÃO ---
if __name__ == "__main__":
    processar_arquivo_respostas()