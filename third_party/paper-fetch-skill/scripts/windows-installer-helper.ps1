param(
    [ValidateSet("Install", "Uninstall", "Smoke")]
    [string]$Action = "Install",
    [string]$InstallRoot,
    [string]$LogPath,
    [switch]$SkipSmoke,
    [switch]$ProbeLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SkillName = "paper-fetch-skill"
$McpName = "paper-fetch"
$OfflineManagedBegin = "# BEGIN paper-fetch offline managed"
$OfflineManagedEnd = "# END paper-fetch offline managed"
$CodexManagedBegin = "# BEGIN paper-fetch installer managed"
$CodexManagedEnd = "# END paper-fetch installer managed"
$McpEnvKeys = @(
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "PAPER_FETCH_ENV_FILE",
    "PAPER_FETCH_DOWNLOAD_DIR",
    "PAPER_FETCH_FORMULA_TOOLS_DIR",
    "MATHML_TO_LATEX_NODE_BIN",
    "CLOAKBROWSER_HEADLESS"
)
$InstallerWarnings = New-Object System.Collections.Generic.List[string]

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
}

function Import-InstallerManifest {
    $manifestPath = Join-Path $InstallRoot "installer/manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Missing installer manifest: $manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $script:SkillName = [string]$manifest.skill.name
    $script:McpName = [string]$manifest.mcp.name
    $script:OfflineManagedBegin = [string]$manifest.managed_blocks.offline.begin
    $script:OfflineManagedEnd = [string]$manifest.managed_blocks.offline.end
    $script:CodexManagedBegin = [string]$manifest.managed_blocks.codex.begin
    $script:CodexManagedEnd = [string]$manifest.managed_blocks.codex.end
    $script:McpEnvKeys = @($manifest.mcp.env_keys | ForEach-Object { [string]$_ })
    Normalize-McpEnvKeys

    if ([string]::IsNullOrWhiteSpace($script:SkillName) -or
        [string]::IsNullOrWhiteSpace($script:McpName) -or
        [string]::IsNullOrWhiteSpace($script:OfflineManagedBegin) -or
        [string]::IsNullOrWhiteSpace($script:OfflineManagedEnd) -or
        [string]::IsNullOrWhiteSpace($script:CodexManagedBegin) -or
        [string]::IsNullOrWhiteSpace($script:CodexManagedEnd) -or
        $script:McpEnvKeys.Count -eq 0) {
        throw "installer manifest is missing required installer constants."
    }
}

function Normalize-McpEnvKeys {
    $filtered = New-Object System.Collections.Generic.List[string]
    $seenHeadless = $false
    foreach ($key in $script:McpEnvKeys) {
        if ($key -eq "PLAYWRIGHT_BROWSERS_PATH") {
            continue
        }
        if ($key -eq "CLOAKBROWSER_HEADLESS") {
            $seenHeadless = $true
        }
        $filtered.Add($key)
    }
    if (-not $seenHeadless) {
        $filtered.Add("CLOAKBROWSER_HEADLESS")
    }
    $script:McpEnvKeys = $filtered.ToArray()
}

Import-InstallerManifest

function Write-Log {
    param([string]$Message)
    Write-Host "==> $Message"
    Write-InstallerLogLine -Level "INFO" -Message $Message
}

function Write-Warn {
    param([string]$Message)
    Write-Warning $Message
    Write-InstallerLogLine -Level "WARN" -Message $Message
}

function Write-InstallerLogLine {
    param(
        [string]$Level,
        [string]$Message
    )

    if ([string]::IsNullOrWhiteSpace($LogPath)) {
        return
    }
    try {
        $logDir = Split-Path -Parent $LogPath
        if (-not [string]::IsNullOrWhiteSpace($logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$timestamp [$Level] $Message"
    } catch {
        Write-Warning "Could not write installer helper log: $($_.Exception.Message)"
    }
}

function Invoke-InstallerStep {
    param(
        [string]$Name,
        [scriptblock]$ScriptBlock,
        [switch]$Required
    )

    try {
        & $ScriptBlock
    } catch {
        $message = "$Name failed: $($_.Exception.Message)"
        if ($Required) {
            throw $message
        }
        $script:InstallerWarnings.Add($message)
        Write-Warn $message
    }
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$IgnoreFailure
    )

    & $FilePath @Arguments | ForEach-Object { Write-Host $_ }
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "Command failed with exit code ${exitCode}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-RuntimePythonScript {
    param(
        [string]$Script,
        [string[]]$Arguments = @()
    )

    $scriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("paper-fetch-smoke-{0}.py" -f [System.Guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($scriptPath, $Script, [System.Text.UTF8Encoding]::new($false))
        Invoke-Checked -FilePath (ConvertTo-FullPath (Get-RuntimePython)) -Arguments (@("-X", "utf8", $scriptPath) + $Arguments)
    } finally {
        Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-RuntimePython {
    return Join-Path (Join-Path $InstallRoot "runtime") "python.exe"
}

function Get-MathmlToLatexNode {
    return Join-Path $InstallRoot "runtime/Lib/site-packages/playwright/driver/node.exe"
}

function ConvertTo-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Quote-DotenvValue {
    param([string]$Value)
    $escaped = (ConvertTo-FullPath $Value).Replace("\", "/").Replace("'", "\'")
    return "'$escaped'"
}

function ConvertTo-TomlString {
    param([string]$Value)
    $escaped = $Value.Replace("\", "\\").Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Get-McpEnv {
    $offlineEnv = Join-Path $InstallRoot "offline.env"
    $downloads = Join-Path $InstallRoot "downloads"
    $formulaTools = Join-Path $InstallRoot "formula-tools"

    $values = @{
        PYTHONUTF8 = "1"
        PYTHONIOENCODING = "utf-8"
        PAPER_FETCH_ENV_FILE = (ConvertTo-FullPath $offlineEnv)
        PAPER_FETCH_DOWNLOAD_DIR = (ConvertTo-FullPath $downloads)
        PAPER_FETCH_FORMULA_TOOLS_DIR = (ConvertTo-FullPath $formulaTools)
        MATHML_TO_LATEX_NODE_BIN = (ConvertTo-FullPath (Get-MathmlToLatexNode))
        CLOAKBROWSER_HEADLESS = "true"
    }
    $ordered = [ordered]@{}
    foreach ($key in $McpEnvKeys) {
        if (-not $values.ContainsKey($key)) {
            throw "Unknown MCP env key in installer manifest: $key"
        }
        $ordered[$key] = $values[$key]
    }
    return $ordered
}

function Set-ProcessRuntimeEnv {
    foreach ($entry in (Get-McpEnv).GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
    }
}

function Remove-ManagedEnvBlock {
    param([string[]]$Lines)

    $result = New-Object System.Collections.Generic.List[string]
    $skip = $false
    foreach ($line in $Lines) {
        if ($line -eq $OfflineManagedBegin) {
            $skip = $true
            continue
        }
        if ($line -eq $OfflineManagedEnd) {
            $skip = $false
            continue
        }
        if (-not $skip) {
            $result.Add($line)
        }
    }
    return $result.ToArray()
}

function Write-ManagedEnvFile {
    $target = Join-Path $InstallRoot "offline.env"
    $envMap = Get-McpEnv
    $lines = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        $existing = Get-Content -LiteralPath $target
        foreach ($line in (Remove-ManagedEnvBlock $existing)) {
            $lines.Add($line)
        }
    } elseif (Test-Path -LiteralPath (Join-Path $InstallRoot ".env.example") -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath (Join-Path $InstallRoot ".env.example")) {
            $lines.Add($line)
        }
    } else {
        $lines.Add('ELSEVIER_API_KEY=""')
    }
    $lines.Add("")
    $lines.Add($OfflineManagedBegin)
    foreach ($name in @(
        "PAPER_FETCH_DOWNLOAD_DIR",
        "PAPER_FETCH_FORMULA_TOOLS_DIR",
        "MATHML_TO_LATEX_NODE_BIN",
        "CLOAKBROWSER_HEADLESS",
        "PYTHONUTF8",
        "PYTHONIOENCODING"
    )) {
        $value = [string]$envMap[$name]
        if ($name -in @("PYTHONUTF8", "PYTHONIOENCODING", "CLOAKBROWSER_HEADLESS")) {
            $lines.Add("$name='$value'")
        } else {
            $lines.Add("$name=$(Quote-DotenvValue $value)")
        }
    }
    $lines.Add("PAPER_FETCH_BROWSER_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'")
    $lines.Add("# CLOAKBROWSER_BINARY_PATH='C:/path/to/preinstalled/browser.exe'")
    $lines.Add($OfflineManagedEnd)
    [System.IO.File]::WriteAllLines($target, $lines, [System.Text.UTF8Encoding]::new($false))
}

function Copy-InstalledSkill {
    param([string]$Destination)

    $source = Join-Path (Join-Path $InstallRoot "skills") $SkillName
    if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md") -PathType Leaf)) {
        throw "Missing bundled skill source: $source"
    }

    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Destination
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $source "*") -Destination $Destination -Recurse -Force
}

function Install-Skills {
    $codexSkill = Join-Path (Join-Path (Join-Path $env:USERPROFILE ".codex") "skills") $SkillName
    $claudeSkill = Join-Path (Join-Path (Join-Path $env:USERPROFILE ".claude") "skills") $SkillName

    Write-Log "Installing Codex skill to $codexSkill"
    Copy-InstalledSkill $codexSkill
    Write-Log "Installing Claude Code skill to $claudeSkill"
    Copy-InstalledSkill $claudeSkill
}

function Remove-Skills {
    foreach ($base in @(".codex", ".claude")) {
        $skillDir = Join-Path (Join-Path (Join-Path $env:USERPROFILE $base) "skills") $SkillName
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $skillDir
        Write-Log "Removed $skillDir"
    }
}

function Get-NormalizedPathPart {
    param([string]$Path)
    try {
        return ([System.IO.Path]::GetFullPath($Path)).TrimEnd("\").ToLowerInvariant()
    } catch {
        return $Path.TrimEnd("\").ToLowerInvariant()
    }
}

function Add-UserPathEntry {
    param([string]$Entry)

    $normalizedEntry = Get-NormalizedPathPart $Entry
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        $parts = @($current -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    foreach ($part in $parts) {
        if ((Get-NormalizedPathPart $part) -eq $normalizedEntry) {
            return
        }
    }
    $parts += [System.IO.Path]::GetFullPath($Entry)
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
    $env:Path = "$Entry;$env:Path"
    Write-Log "Added $Entry to the user PATH"
}

function Remove-UserPathEntry {
    param([string]$Entry)

    $normalizedEntry = Get-NormalizedPathPart $Entry
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if ([string]::IsNullOrWhiteSpace($current)) {
        return
    }
    $kept = New-Object System.Collections.Generic.List[string]
    foreach ($part in @($current -split ";")) {
        if ([string]::IsNullOrWhiteSpace($part)) {
            continue
        }
        if ((Get-NormalizedPathPart $part) -ne $normalizedEntry) {
            $kept.Add($part)
        }
    }
    [Environment]::SetEnvironmentVariable("Path", ($kept.ToArray() -join ";"), "User")
    Write-Log "Removed $Entry from the user PATH"
}

function Backup-File {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $stamp = Get-Date -Format "yyyyMMddHHmmss"
        Copy-Item -LiteralPath $Path -Destination "$Path.bak-$stamp" -Force
    }
}

function Remove-CodexMcpTables {
    param([string[]]$Lines)

    $result = New-Object System.Collections.Generic.List[string]
    $skip = $false
    $mcpTablePattern = '^\s*\[mcp_servers\.' + [regex]::Escape($McpName) + '(?:\..*)?\]\s*$'
    foreach ($line in $Lines) {
        if ($line -eq $CodexManagedBegin) {
            $skip = $true
            continue
        }
        if ($line -eq $CodexManagedEnd) {
            $skip = $false
            continue
        }
        if ($line -match $mcpTablePattern) {
            $skip = $true
            continue
        }
        if ($skip -and $line -match '^\s*\[') {
            $skip = $false
        }
        if (-not $skip) {
            $result.Add($line)
        }
    }
    return $result.ToArray()
}

function Write-CodexConfigToml {
    $codexHome = Join-Path $env:USERPROFILE ".codex"
    $configPath = Join-Path $codexHome "config.toml"
    New-Item -ItemType Directory -Force -Path $codexHome | Out-Null
    Backup-File $configPath

    $existing = @()
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        $existing = Get-Content -LiteralPath $configPath
    }
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($line in (Remove-CodexMcpTables $existing)) {
        $lines.Add($line)
    }

    $python = ConvertTo-FullPath (Get-RuntimePython)
    $lines.Add("")
    $lines.Add($CodexManagedBegin)
    $lines.Add("[mcp_servers.$McpName]")
    $lines.Add("command = $(ConvertTo-TomlString $python)")
    $lines.Add('args = ["-X", "utf8", "-m", "paper_fetch.mcp.server"]')
    $lines.Add("")
    $lines.Add("[mcp_servers.$McpName.env]")
    foreach ($entry in (Get-McpEnv).GetEnumerator()) {
        $lines.Add("$($entry.Key) = $(ConvertTo-TomlString ([string]$entry.Value))")
    }
    $lines.Add($CodexManagedEnd)
    [System.IO.File]::WriteAllLines($configPath, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Log "Updated Codex MCP config at $configPath"
}

function Remove-CodexConfigToml {
    $configPath = Join-Path (Join-Path $env:USERPROFILE ".codex") "config.toml"
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        return
    }
    Backup-File $configPath
    $lines = Remove-CodexMcpTables (Get-Content -LiteralPath $configPath)
    [System.IO.File]::WriteAllLines($configPath, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Log "Removed Codex MCP config from $configPath"
}

function Register-CodexMcp {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    $python = ConvertTo-FullPath (Get-RuntimePython)
    if ($null -ne $codex) {
        try {
            Write-Log "Registering Codex MCP server '$McpName' with Codex CLI"
            Invoke-Checked -FilePath $codex.Source -Arguments @("mcp", "remove", $McpName) -IgnoreFailure
            $args = @("mcp", "add")
            foreach ($entry in (Get-McpEnv).GetEnumerator()) {
                $args += @("--env", "$($entry.Key)=$($entry.Value)")
            }
            $args += @($McpName, "--", $python, "-X", "utf8", "-m", "paper_fetch.mcp.server")
            Invoke-Checked -FilePath $codex.Source -Arguments $args
            return
        } catch {
            Write-Warn "Codex CLI MCP registration failed; falling back to config.toml. $($_.Exception.Message)"
        }
    }
    Write-CodexConfigToml
}

function Unregister-CodexMcp {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if ($null -ne $codex) {
        Invoke-Checked -FilePath $codex.Source -Arguments @("mcp", "remove", $McpName) -IgnoreFailure
    }
    Remove-CodexConfigToml
}

function Register-ClaudeMcp {
    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if ($null -eq $claude) {
        Write-Log "Claude CLI not found; installed the skill and skipped Claude MCP registration"
        return
    }

    try {
        $python = ConvertTo-FullPath (Get-RuntimePython)
        Write-Log "Registering Claude MCP server '$McpName' with Claude CLI"
        Invoke-Checked -FilePath $claude.Source -Arguments @("mcp", "remove", "-s", "user", $McpName) -IgnoreFailure
        $args = @("mcp", "add", "-s", "user")
        foreach ($entry in (Get-McpEnv).GetEnumerator()) {
            $args += @("-e", "$($entry.Key)=$($entry.Value)")
        }
        $args += @("--", $McpName, $python, "-X", "utf8", "-m", "paper_fetch.mcp.server")
        Invoke-Checked -FilePath $claude.Source -Arguments $args
    } catch {
        Write-Warn "Claude MCP registration failed and was skipped. $($_.Exception.Message)"
    }
}

function Unregister-ClaudeMcp {
    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if ($null -ne $claude) {
        Invoke-Checked -FilePath $claude.Source -Arguments @("mcp", "remove", "-s", "user", $McpName) -IgnoreFailure
    }
}

function Invoke-SmokeChecks {
    $texmath = ConvertTo-FullPath (Join-Path (Join-Path $InstallRoot "formula-tools") "bin/texmath.exe")
    $node = ConvertTo-FullPath (Get-MathmlToLatexNode)

    Set-ProcessRuntimeEnv
    Write-Log "Running bundled Python smoke checks"
    Invoke-RuntimePythonScript -Script @'
import paper_fetch
from paper_fetch.mcp.fetch_tool import provider_status_payload

payload = provider_status_payload()
assert "providers" in payload
'@

    $cloakbrowserCheck = @'
from pathlib import Path
import os
import sys

import cloakbrowser

assert hasattr(cloakbrowser, "launch")
binary_path = os.environ.get("CLOAKBROWSER_BINARY_PATH")
if binary_path:
    path = Path(binary_path)
    assert path.is_file(), binary_path

if len(sys.argv) > 1 and sys.argv[1] == "probe-launch":
    headless = os.environ.get("CLOAKBROWSER_HEADLESS", "true").strip().lower() not in {"0", "false", "no", "off"}
    browser = cloakbrowser.launch(headless=headless)
    browser.close()
'@
    $args = @()
    if ($ProbeLaunch) {
        $args += "probe-launch"
    }
    Invoke-RuntimePythonScript -Script $cloakbrowserCheck -Arguments $args
    Invoke-Checked -FilePath $texmath -Arguments @("--help")
    Invoke-Checked -FilePath $node -Arguments @("--version")
}

switch ($Action) {
    "Install" {
        Invoke-InstallerStep -Name "offline.env update" -Required -ScriptBlock { Write-ManagedEnvFile }
        Invoke-InstallerStep -Name "skill installation" -ScriptBlock { Install-Skills }
        Invoke-InstallerStep -Name "PATH update" -ScriptBlock { Add-UserPathEntry (Join-Path $InstallRoot "bin") }
        Invoke-InstallerStep -Name "Codex MCP registration" -ScriptBlock { Register-CodexMcp }
        Invoke-InstallerStep -Name "Claude MCP registration" -ScriptBlock { Register-ClaudeMcp }
        if (-not $SkipSmoke) {
            Invoke-InstallerStep -Name "smoke checks" -ScriptBlock { Invoke-SmokeChecks }
        }
        if ($InstallerWarnings.Count -gt 0) {
            Write-Warn "Install helper completed with $($InstallerWarnings.Count) non-critical warning(s)."
            exit 2
        }
    }
    "Uninstall" {
        try { Remove-Skills } catch { Write-Warn $_.Exception.Message }
        try { Remove-UserPathEntry (Join-Path $InstallRoot "bin") } catch { Write-Warn $_.Exception.Message }
        try { Unregister-CodexMcp } catch { Write-Warn $_.Exception.Message }
        try { Unregister-ClaudeMcp } catch { Write-Warn $_.Exception.Message }
    }
    "Smoke" {
        Invoke-SmokeChecks
    }
}

exit 0
