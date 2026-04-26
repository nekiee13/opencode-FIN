param(
    [string]$ComposeFilePath = "C:\opencode-sandbox\docker-compose.opencode.yml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_runtime_common.ps1"

Assert-DockerReady

if (Test-Path $ComposeFilePath) {
    docker compose -f $ComposeFilePath stop *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-GateResult -Gate "FIN_COMPOSE_STOP" -Result "FAIL_DOCKER" -Message ("compose stop failed ({0})" -f $ComposeFilePath)
        exit 32
    }
    Write-GateResult -Gate "FIN_COMPOSE_STOP" -Result "PASS" -Message ("compose stop ok ({0})" -f $ComposeFilePath)
} else {
    Write-GateResult -Gate "FIN_COMPOSE_STOP" -Result "SKIP_ABSENT" -Message ("compose file absent ({0})" -f $ComposeFilePath)
}

Remove-ContainerIdempotent -ContainerName $FinContainerName -Gate "FIN_CLOSE_REMOVE"
Assert-PortFree -Port $FinHostPort -Gate "FIN_PORT_CLOSED"

Write-GateResult -Gate "FIN_CLOSE" -Result "PASS" -Message "closed and port clear"
