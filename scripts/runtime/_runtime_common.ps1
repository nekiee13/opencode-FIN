Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LocalhostIp = "127.0.0.1"
$RuntimeContainerPort = 4096

$FinContainerName = "oc-fin-opencode"
$AgentCoreContainerName = "oc-agentcore-opencode"
$LlmWikiContainerName = "oc-llmwiki-opencode"

$FinHostPort = 5096
$AgentCoreHostPort = 4096
$LlmWikiHostPort = 4196

function Write-GateResult {
    param(
        [Parameter(Mandatory = $true)][string]$Gate,
        [Parameter(Mandatory = $true)][string]$Result,
        [Parameter(Mandatory = $true)][string]$Message
    )
    Write-Host "GATE=$Gate RESULT=$Result MESSAGE=$Message"
}

function Assert-DockerReady {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-GateResult -Gate "DOCKER_READY" -Result "FAIL_DOCKER" -Message "docker engine unavailable"
        exit 10
    }
    Write-GateResult -Gate "DOCKER_READY" -Result "PASS" -Message "docker engine available"
}

function Remove-ContainerIdempotent {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$Gate
    )

    $names = docker ps -a --format "{{.Names}}"
    if ($LASTEXITCODE -ne 0) {
        Write-GateResult -Gate $Gate -Result "FAIL_DOCKER" -Message "unable to enumerate containers"
        exit 11
    }

    $exists = @($names | Where-Object { $_ -eq $ContainerName }).Count -gt 0
    if (-not $exists) {
        Write-GateResult -Gate $Gate -Result "SKIP_ABSENT" -Message "container absent ($ContainerName)"
        return
    }

    docker rm -f $ContainerName *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-GateResult -Gate $Gate -Result "FAIL_DOCKER" -Message "remove failed ($ContainerName)"
        exit 12
    }

    Write-GateResult -Gate $Gate -Result "PASS" -Message "container removed ($ContainerName)"
}

function Assert-PortFree {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Gate
    )

    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -ne $listeners) {
        $pidList = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ","
        Write-GateResult -Gate $Gate -Result "FAIL_PORT_IN_USE" -Message "port=$Port owner_pid=$pidList"
        exit 21
    }

    Write-GateResult -Gate $Gate -Result "PASS" -Message "port=$Port free"
}

function Assert-FinSafetyHealthy {
    $url = ("http://{0}:{1}/global/health" -f $LocalhostIp, $FinHostPort)
    $response = curl.exe -sS --max-time 10 $url
    if ($LASTEXITCODE -ne 0) {
        Write-GateResult -Gate "FIN_SAFETY_HEALTH" -Result "FAIL_HEALTH" -Message "transport failure ($url)"
        exit 22
    }

    if ($response -notmatch '"healthy"\s*:\s*true') {
        Write-GateResult -Gate "FIN_SAFETY_HEALTH" -Result "FAIL_HEALTH" -Message "unhealthy ($url)"
        exit 23
    }

    Write-GateResult -Gate "FIN_SAFETY_HEALTH" -Result "PASS" -Message "healthy ($url)"
}

function Start-OpencodeContainer {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][int]$HostPort,
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [Parameter(Mandatory = $true)][string]$ConfigFilePath,
        [Parameter(Mandatory = $true)][string]$Gate
    )

    $portMap = ("{0}:{1}:{2}" -f $LocalhostIp, $HostPort, $RuntimeContainerPort)
    $repoVolume = ("{0}:/repo" -f $RepoPath)
    $configVolume = ("{0}:/workspace/.config/opencode/opencode.jsonc:ro" -f $ConfigFilePath)

    docker run -d --name $ContainerName `
        -p $portMap `
        -e OPENCODE_CONFIG_DIR=/workspace/.config/opencode `
        -e XDG_CONFIG_HOME=/workspace/.config `
        -v $repoVolume `
        -v oc_fin_workspace:/workspace `
        -v oc_fin_home:/home/opencode `
        -v $configVolume `
        opencode-sandbox-opencode `
        opencode serve --hostname 0.0.0.0 --port 4096 --print-logs --log-level INFO *> $null

    if ($LASTEXITCODE -ne 0) {
        Write-GateResult -Gate $Gate -Result "FAIL_DOCKER" -Message "runtime start failed ($ContainerName)"
        exit 24
    }

    Write-GateResult -Gate $Gate -Result "PASS" -Message "runtime started ($ContainerName)"
}

function Assert-HealthyEndpoint {
    param(
        [Parameter(Mandatory = $true)][int]$HostPort,
        [Parameter(Mandatory = $true)][string]$Gate
    )

    $url = ("http://{0}:{1}/global/health" -f $LocalhostIp, $HostPort)
    $deadline = (Get-Date).AddSeconds(30)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 3
            if (($null -ne $response) -and ($response.healthy -eq $true)) {
                Write-GateResult -Gate $Gate -Result "PASS" -Message "healthy ($url)"
                return
            }
        } catch {
        }
        Start-Sleep -Milliseconds 750
    }

    Write-GateResult -Gate $Gate -Result "FAIL_HEALTH" -Message "startup timeout waiting for healthy endpoint ($url)"
    exit 26
}
function Assert-ContainerCommand {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string[]]$Command,
        [Parameter(Mandatory = $true)][string]$Gate
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $args = @("exec", $ContainerName) + $Command
        $proc = Start-Process -FilePath "docker" -ArgumentList $args -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

        if ($proc.ExitCode -ne 0) {
            $stderrText = (Get-Content -Raw -Path $stderrPath -ErrorAction SilentlyContinue)
            Write-GateResult -Gate $Gate -Result "FAIL_HEALTH" -Message ("command failed ({0} :: {1}) stderr={2}" -f $ContainerName, ($Command -join ' '), $stderrText.Trim())
            exit 27
        }
    } finally {
        Remove-Item -Path $stdoutPath -ErrorAction SilentlyContinue
        Remove-Item -Path $stderrPath -ErrorAction SilentlyContinue
    }

    Write-GateResult -Gate $Gate -Result "PASS" -Message ("command ok ({0})" -f ($Command -join ' '))
}



