param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$ApiKey  = "dockit-material-beta-123"
)

$ErrorActionPreference = "Stop"

$headers = @{
  "X-DOCKIT-API-KEY" = $ApiKey
  "Content-Type"     = "application/json"
}

$body = @{
  text           = "Installera 2 nätverksuttag cat6 och montera en taklampa"
  customer_name  = "Test"
  customer_email = "test@example.com"
  apply_rot      = $false
} | ConvertTo-Json

$res = Invoke-RestMethod -Method Post -Uri "$BaseUrl/sandbox/interpret" -Headers $headers -Body $body

if (-not $res.lines -or $res.lines.Count -lt 1) {
  Write-Error "SMOKE FAIL: No lines returned"
  exit 1
}

Write-Host "SMOKE OK: sandbox=$($res.sandbox) lines=$($res.lines.Count) total=$($res.total_sek)"
exit 0
