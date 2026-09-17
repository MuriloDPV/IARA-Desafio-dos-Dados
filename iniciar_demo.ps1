# Sobe bot + painel em duas janelas separadas para a gravação da demo.
$pasta = $PSScriptRoot

if (-not (Test-Path (Join-Path $pasta ".env"))) {
    Write-Host "ERRO: .env nao encontrado. Copie .env.example para .env e preencha." -ForegroundColor Red
    exit 1
}

# Mata instancias antigas de python DESTE projeto (evita "Conflict" no Telegram
# e porta 8000 ocupada). O filtro exige o caminho desta pasta na linha de
# comando, entao python de outros projetos nao e tocado.
$antigos = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($pasta) }

foreach ($p in $antigos) {
    Write-Host "Encerrando processo antigo deste projeto (PID $($p.ProcessId))." -ForegroundColor Yellow
    try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {}
}

if ($antigos) { Start-Sleep -Seconds 1 }

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$pasta'; python '$pasta\bot.py'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$pasta'; python '$pasta\painel.py'"
Start-Sleep -Seconds 2
Start-Process "http://localhost:8000"
Write-Host "Bot + painel iniciados. Painel: http://localhost:8000"
