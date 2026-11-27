# Kurulum: servisleri başlatır, Postgres kimlik bilgisini ve workflow'ları
# n8n'e yükler, fatura ve hata workflow'larını yayınlar.
# Tekrar çalıştırmak güvenlidir: aynı kimlikli kayıtların üzerine yazar.
#
#   powershell -ExecutionPolicy Bypass -File .\kurulum.ps1

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([Convert]::ToBase64String($bytes) -replace '[+/=]', '')
}

# PowerShell 5.1'in utf8'i BOM ekler; n8n ve docker compose BOM'suz bekler.
function Write-Utf8($path, $text) {
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $path), $text, (New-Object System.Text.UTF8Encoding $false))
}

if (-not (Test-Path .env)) {
    Write-Host '.env oluşturuluyor (rastgele şifrelerle)...'
    Write-Utf8 .env (((Get-Content .env.example -Encoding utf8) -join "`n") + "`n")
}

# Boş ya da eksik gizli değerler rastgele üretilir; dolu olanlara dokunulmaz.
# Eski bir .env'ye sonradan eklenen değerler de böylece tamamlanır.
# -cmatch (büyük/küçük harf duyarlı) bilerek seçildi: Türkçe Windows'ta -match,
# I harfini ı ile eşleştirmeye çalıştığından FATURA_API_KEY gibi adları bulamaz.
$lines = [System.Collections.Generic.List[string]](Get-Content .env -Encoding utf8)
$changed = $false
foreach ($key in 'POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY', 'FATURA_API_KEY', 'ASISTAN_SIFRE') {
    $index = $lines.FindIndex([Predicate[string]] { param($l) $l -cmatch "^\s*$key=" })
    if ($index -ge 0 -and $lines[$index] -cmatch "^\s*$key=\s*\S") { continue }
    $entry = "$key=$(New-Secret)"
    if ($index -ge 0) { $lines[$index] = $entry } else { $lines.Add($entry) }
    $changed = $true
}
if ($changed) { Write-Utf8 .env (($lines -join "`n") + "`n") }

$envValues = @{}
foreach ($line in $lines) {
    if ($line -cmatch '^\s*([A-Z0-9_]+)=(.*)$') { $envValues[$Matches[1]] = $Matches[2].Trim() }
}
$chatUser = if ($envValues.ASISTAN_KULLANICI) { $envValues.ASISTAN_KULLANICI } else { 'muhasebe' }
$pgUser = if ($envValues.POSTGRES_USER) { $envValues.POSTGRES_USER } else { 'otomasyon' }
$pgDb = if ($envValues.POSTGRES_DB) { $envValues.POSTGRES_DB } else { 'otomasyon' }
$port = if ($envValues.N8N_PORT) { $envValues.N8N_PORT } else { '5678' }

Write-Host 'Servisler başlatılıyor (ilk seferde extractor build edilir)...'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'docker compose up başarısız' }

Write-Host 'n8n bekleniyor...'
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest "http://localhost:$port/healthz" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw 'n8n 2 dakikada açılmadı: docker compose logs n8n' }

# Kimlik bilgisi şifresiz yazılır, n8n içeri alırken şifreler. Dosya gitignore'da.
New-Item -ItemType Directory -Force credentials | Out-Null
$credential = @(@{
    id   = 'pgBelgeler000001'
    name = 'Postgres (belgeler)'
    type = 'postgres'
    data = @{
        host = 'postgres'; port = 5432; database = $pgDb; user = $pgUser
        password = $envValues.POSTGRES_PASSWORD; ssl = 'disable'
    }
}, @{
    id   = 'ollamaYerel00001'
    name = 'Ollama (yerel)'
    type = 'ollamaApi'
    data = @{ baseUrl = 'http://ollama:11434' }
}, @{
    # Fatura webhook'una gönderen her sistem bu başlığı yollar.
    id   = 'faturaApiAnahtar'
    name = 'Fatura API anahtarı'
    type = 'httpHeaderAuth'
    data = @{ name = 'X-API-Key'; value = $envValues.FATURA_API_KEY }
}, @{
    id   = 'asistanGirisi0001'
    name = 'Asistan girişi'
    type = 'httpBasicAuth'
    data = @{ user = $chatUser; password = $envValues.ASISTAN_SIFRE }
})
# Telegram botu .env'den gelir (README, "Telegram"); yoksa bildirimler kapalı kalır.
if ($envValues.TELEGRAM_BOT_TOKEN) {
    $credential += @{
        id   = 'telegramBot00001'
        name = 'Telegram bot'
        type = 'telegramApi'
        data = @{ accessToken = $envValues.TELEGRAM_BOT_TOKEN }
    }
}
Write-Utf8 credentials/kimlik-bilgileri.json (ConvertTo-Json -InputObject $credential -Depth 5)

Write-Host 'Kimlik bilgileri ve workflow''lar yükleniyor...'
docker compose exec -T n8n n8n import:credentials --input=/import/credentials/kimlik-bilgileri.json
if ($LASTEXITCODE -ne 0) { throw 'Kimlik bilgileri yüklenemedi' }

# Workflow'lar bu kuruluma göre doldurulur: Telegram sohbeti, tablo adresi ve
# n8n arayüzünde bağlanan Google hesapları (scripts/render-workflows.js).
docker compose exec -T n8n sh -c 'n8n export:credentials --all --output=/tmp/kimlikler.json >/dev/null 2>&1'
$render = docker compose exec -T -e "TELEGRAM_CHAT_ID=$($envValues.TELEGRAM_CHAT_ID)" `
    -e "GOOGLE_SHEET_URL=$($envValues.GOOGLE_SHEET_URL)" n8n `
    sh -c 'rm -rf /tmp/workflows && node /import/scripts/render-workflows.js /import/workflows /tmp/workflows /tmp/kimlikler.json; status=$?; rm -f /tmp/kimlikler.json; exit $status'
if ($LASTEXITCODE -ne 0) { throw 'Workflow''lar hazırlanamadı' }
$render | Where-Object { $_ -notlike 'READY=*' } | ForEach-Object { Write-Host "  $_" }
$optional = (($render | Where-Object { $_ -like 'READY=*' }) -replace '^READY=', '') -split ',' | Where-Object { $_ }

docker compose exec -T n8n n8n import:workflow --separate --input=/tmp/workflows
if ($LASTEXITCODE -ne 0) { throw 'Workflow''lar yüklenemedi' }
foreach ($id in @('HataBildirim0099', 'FaturaIsleme0001', 'FaturaAsistani03') + $optional) {
    docker compose exec -T n8n n8n publish:workflow --id=$id
    if ($LASTEXITCODE -ne 0) { throw "$id yayınlanamadı" }
}

# Asistan modeli: qwen3.5:4b, bu makineye uygun thread sayısıyla. Ollama her
# çekirdeğe bir thread açar; P/E çekirdekli CPU'larda bu üretimi 40 kat
# yavaşlatabilir (README, "Hız"). Model yoksa önce indirilir (~3 GB, bir kez).
$threads = if ($envValues.OLLAMA_NUM_THREAD) { $envValues.OLLAMA_NUM_THREAD } else { '8' }
Write-Host "Asistan modeli hazırlanıyor (qwen3.5-asistan, $threads thread)..."
docker compose exec -T ollama sh -c "ollama show qwen3.5:4b >/dev/null 2>&1 || ollama pull qwen3.5:4b; ollama show nomic-embed-text >/dev/null 2>&1 || ollama pull nomic-embed-text; printf 'FROM qwen3.5:4b\nPARAMETER num_thread $threads\n' > /tmp/Modelfile && ollama create qwen3.5-asistan -f /tmp/Modelfile" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Asistan modeli oluşturulamadı: docker compose logs ollama' }

# Extractor'ın gizli modundaki görsel model de aynı thread ayarını alır; adı
# extractor'ın beklediği gibi kalır (~2 GB, bir kez iner).
Write-Host "Görsel model hazırlanıyor (qwen3-vl:2b-instruct, $threads thread)..."
docker compose exec -T ollama sh -c "ollama show qwen3-vl:2b-instruct >/dev/null 2>&1 || ollama pull qwen3-vl:2b-instruct; printf 'FROM qwen3-vl:2b-instruct\nPARAMETER num_thread $threads\n' > /tmp/Modelfile && ollama create qwen3-vl:2b-instruct -f /tmp/Modelfile" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning 'Görsel model hazırlanamadı; extractor OCR ve kurallarla çalışır.' }

# Örnek belgeler RAG'e bir kez yüklenir (asistanın dokuman_sor aracı için).
# RAG dışarıya açık değil; yükleme compose ağındaki bir curl konteynerinden yapılır.
$network = "$((Split-Path -Leaf $PSScriptRoot).ToLower())_default"
$indexed = docker compose exec -T n8n wget -qO- http://rag:8000/documents 2>$null
foreach ($file in Get-ChildItem ornekler/belgeler -File) {
    if ("$indexed" -clike "*$($file.Name)*") { continue }
    Write-Host "RAG'e yükleniyor: $($file.Name) (ilk seferde birkaç dakika sürebilir)"
    docker run --rm --network $network -v "$($file.DirectoryName):/b:ro" curlimages/curl:8.11.1 `
        -s -m 600 -F "file=@/b/$($file.Name)" http://rag:8000/upload | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning "$($file.Name) yüklenemedi: docker compose logs rag" }
}

# Çalışan n8n yayını birkaç saniye içinde alır; o ana kadar webhook 404 verir.
Start-Sleep -Seconds 10

Write-Host ''
Write-Host "Hazır. n8n: http://localhost:$port (ilk açılışta yönetici hesabı oluşturun)"
Write-Host "Fatura göndermek için (anahtar .env'de FATURA_API_KEY):"
Write-Host "  curl.exe -H `"X-API-Key: <anahtar>`" -F file=@fatura.pdf http://localhost:$port/webhook/fatura"
Write-Host "Asistan: http://localhost:$port/webhook/fatura-asistani/chat"
Write-Host "  kullanıcı: $chatUser, şifre: .env'de ASISTAN_SIFRE"
