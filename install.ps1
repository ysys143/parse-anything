<#
.SYNOPSIS
  parse-anything installer for Windows.
.DESCRIPTION
  Downloads a self-contained release bundle (frozen Python + a trimmed JRE -- no Python or Java needed)
  from GitHub Releases, installs it under %LOCALAPPDATA%\parse-anything, and puts the parse-anything /
  parse / pa commands on your user PATH. Re-run to update.

    irm https://raw.githubusercontent.com/ysys143/parse-anything/main/install.ps1 | iex

  With arguments:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/ysys143/parse-anything/main/install.ps1))) -Version v0.1.0
    ... -Uninstall
#>
[CmdletBinding()]
param(
  [string]$Version = $env:PARSE_ANYTHING_VERSION,
  [string]$InstallDir = $(if ($env:PARSE_ANYTHING_INSTALL_DIR) { $env:PARSE_ANYTHING_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'parse-anything' }),
  [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$Owner = 'ysys143'
$Repo  = 'parse-anything'

function Info($m) { Write-Host "  $m" }
function Die($m)  { Write-Error $m; exit 1 }

function Add-UserPath($dir) {
  $cur = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (($cur -split ';') -notcontains $dir) {
    $new = if ([string]::IsNullOrEmpty($cur)) { $dir } else { "$cur;$dir" }
    [Environment]::SetEnvironmentVariable('Path', $new, 'User')
    Info "added $dir to your user PATH"
  }
  $env:Path = "$dir;$env:Path"   # usable in this session too
}

function Do-Uninstall {
  foreach ($c in 'parse','pa') {
    $p = Join-Path $InstallDir "$c.cmd"
    if (Test-Path $p) { Remove-Item $p -Force }
  }
  if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force; Info "removed $InstallDir" }
  Info "a '$InstallDir' entry may remain in your user PATH; remove it manually if desired"
}

function Do-Install {
  $arch = switch ($env:PROCESSOR_ARCHITECTURE) {
    'AMD64' { 'x86_64' }; 'ARM64' { 'arm64' }; default { Die "unsupported architecture: $env:PROCESSOR_ARCHITECTURE" }
  }
  $platform = "windows-$arch"

  if (-not $Version) {
    $rel = Invoke-RestMethod "https://api.github.com/repos/$Owner/$Repo/releases/latest"
    $Version = $rel.tag_name
    if (-not $Version) { Die "could not resolve the latest release (pass -Version)" }
  }

  $asset = "parse-anything-$Version-$platform.tar.gz"
  $base  = "https://github.com/$Owner/$Repo/releases/download/$Version"
  $tmp   = Join-Path ([System.IO.Path]::GetTempPath()) ("pa-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $tmp -Force | Out-Null
  try {
    $tgz = Join-Path $tmp 'pkg.tar.gz'
    Info "downloading $asset"
    Invoke-WebRequest "$base/$asset" -OutFile $tgz

    try {
      $shaFile = Join-Path $tmp 'pkg.sha256'
      Invoke-WebRequest "$base/$asset.sha256" -OutFile $shaFile
      $expected = ((Get-Content $shaFile -Raw) -split '\s+')[0].Trim().ToLower()
      $actual = (Get-FileHash $tgz -Algorithm SHA256).Hash.ToLower()
      if ($actual -ne $expected) { Die "checksum mismatch (expected $expected, got $actual)" }
      Info "checksum ok"
    } catch { Write-Warning "no checksum published for $asset; skipping verification" }

    Info "installing to $InstallDir"
    if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    tar -xzf $tgz -C $InstallDir --strip-components=1   # Windows 10+ ships bsdtar

    $exe = Join-Path $InstallDir 'parse-anything.exe'
    if (-not (Test-Path $exe)) { Die "bundle layout unexpected: $exe not found" }
    foreach ($c in 'parse','pa') {   # .cmd shims for the aliases
      Set-Content -Path (Join-Path $InstallDir "$c.cmd") -Value "@echo off`r`n`"$exe`" %*" -Encoding ASCII
    }
    Add-UserPath $InstallDir

    & $exe --help | Out-Null
    Write-Host "`nparse-anything $Version installed. Try:  parse-anything --pdf doc.pdf --out out\ --mode deterministic"
    Write-Host "(open a new terminal so the updated PATH takes effect)"
  } finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if ($Uninstall) { Do-Uninstall } else { Do-Install }
