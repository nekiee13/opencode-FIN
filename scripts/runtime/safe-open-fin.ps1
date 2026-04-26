param(
    [string]$ComposeFilePath = "C:\opencode-sandbox\docker-compose.opencode.yml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_runtime_common.ps1"

Assert-DockerReady

if (-not (Test-Path $ComposeFilePath)) {
    Write-GateResult -Gate "FIN_COMPOSE_FILE" -Result "FAIL_DOCKER" -Message ("compose file missing ({0})" -f $ComposeFilePath)
    exit 30
}

$stdoutPath = [System.IO.Path]::GetTempFileName()
$stderrPath = [System.IO.Path]::GetTempFileName()
try {
    $args = @("compose", "-f", $ComposeFilePath, "up", "-d")
    $proc = Start-Process -FilePath "docker" -ArgumentList $args -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    if ($proc.ExitCode -ne 0) {
        $stderrText = (Get-Content -Raw -Path $stderrPath -ErrorAction SilentlyContinue)
        Write-GateResult -Gate "FIN_COMPOSE_UP" -Result "FAIL_DOCKER" -Message ("compose up failed ({0}) stderr={1}" -f $ComposeFilePath, $stderrText.Trim())
        exit 31
    }
} finally {
    Remove-Item -Path $stdoutPath -ErrorAction SilentlyContinue
    Remove-Item -Path $stderrPath -ErrorAction SilentlyContinue
}

Write-GateResult -Gate "FIN_COMPOSE_UP" -Result "PASS" -Message ("compose up ok ({0})" -f $ComposeFilePath)

Assert-HealthyEndpoint -HostPort $FinHostPort -Gate "FIN_HEALTH"
Assert-ContainerCommand -ContainerName $FinContainerName -Command @("opencode", "auth", "list") -Gate "FIN_AUTH"
Assert-ContainerCommand -ContainerName $FinContainerName -Command @("opencode", "models") -Gate "FIN_MODELS"

Write-GateResult -Gate "FIN_OPEN" -Result "PASS" -Message "ready at http://127.0.0.1:5096"
