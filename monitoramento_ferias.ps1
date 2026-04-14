# Script para monitoramento da equipe Green Máquinas
$equipe = @(
    "Adeilson de Oliveira", "Anderson Lucas Duarte Freitas", "Antônio Weslley Santos Batista",
    "Clenison de Sousa Soares", "Daniel Mateus Oliveira", "Dhone Francisco da Silva",
    "Edilson Ribeiro de Lima Junior", "Felipe Honorato", "Gabriel Sousa Vieira",
    "Geoglenn Jose Lanz Parra", "Igor Matthews Barros Marques", "Jaime da Silva Coelho",
    "Jose Augusto Barbosa Neto", "Kaio Gabriel Carrêra", "Leonardo Winicios Simões dos Santos",
    "Lucas Gleub Ribeiro", "Phillip Antonic Persaud", "Rayan dos Santos Mendes",
    "Rócio Diaz Del Pino", "Jorge William Braga Menezes", "Bruno Caik da Silva Thome",
    "Antonio Carlos Caetano", "Marinilson Mota de Lira"
)

Write-Host "`n--- MONITORAMENTO DE FÉRIAS | GREEN MÁQUINAS ---" -ForegroundColor Green
Write-Host "Total de Colaboradores: $($equipe.Count)"

# Simulação de envio do link
$linkForms = "https://link-do-seu-forms-aqui.com"

Write-Host "`n[AÇÕES DISPONÍVEIS]"
Write-Host "1. Listar Equipe Completa"
Write-Host "2. Gerar Link de Envio (WhatsApp/Email)"
Write-Host "3. Verificar Planilha de Status"

$choice = Read-Host "`nEscolha uma opção"

if ($choice -eq "1") {
    $equipe | ForEach-Object { Write-Host "- $_" }
} elseif ($choice -eq "2") {
    Write-Host "`nCopie o texto abaixo para enviar à equipe:"
    Write-Host "--------------------------------------------------"
    Write-Host "Prezados, favor preencher a programação de férias no link: $linkForms"
    Write-Host "Lembre-se das regras de períodos permitidos e divisões (30, 15+15 ou 20+10)."
    Write-Host "--------------------------------------------------"
}