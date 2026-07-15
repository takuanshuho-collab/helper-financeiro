#Requires -Version 7
<#
.SYNOPSIS
    Build ASSINADO do Helper Financeiro com o cert de teste (ADR-0021, T-2402).

.DESCRIPTION
    Embrulha o `npm run dist` para produzir um instalador assinado SEM tocar no
    package.json — a config de assinatura entra so por override de CLI do
    electron-builder. Sem as envs HF_CSC_*, o build normal (npm run dist / dist:dir)
    permanece byte-identico ao atual (config inerte, zero impacto no dia a dia).

    Porque as decisoes abaixo:
      - Assina o sidecar-hf.exe ANTES do empacotamento: o electron-builder assina o
        instalador e o exe principal do app, mas NAO assina binarios de
        extraResources. O sidecar entra como extraResource (package.json), entao
        precisa ser assinado no lugar (dist/sidecar-hf) para a copia embarcada em
        release/win-unpacked/resources herdar a assinatura.
      - signtool com /fd sha256 e SEM /tr (timestamp): para o cert de TESTE o
        timestamp e dispensavel — o cert expira em 30 dias de qualquer jeito, entao
        nao ha o que "preservar apos a expiracao". Producao via SignPath usa o
        timestamping da plataforma deles (fora do escopo desta task).
      - Overrides -c.win.signtoolOptions.* (electron-builder 26.x) lidos de env:
        segredo nunca no repo. publisherName default = subject do cert de teste.
      - -VersaoFake -> -c.extraMetadata.version=99.0.0: e o gancho que a T-2403 usa
        para gerar o instalador de update do feed (versao maior que a instalada).

.EXAMPLE
    $env:HF_CSC_PFX = "$env:USERPROFILE\.hf-signing\teste.pfx"
    $env:HF_CSC_SENHA = 'senha-de-teste'
    pwsh scripts/build_assinado.ps1

.EXAMPLE
    # Instalador de update re-versionado para o smoke da T-2403:
    pwsh scripts/build_assinado.ps1 -VersaoFake 99.0.0
#>
[CmdletBinding()]
param(
    # Se informado, sobrescreve a versao do instalador (feed de update — T-2403).
    [string]$VersaoFake
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRaiz = Split-Path -Parent $PSScriptRoot
$GuiWeb   = Join-Path $RepoRaiz 'gui_web'
$Sidecar  = Join-Path $RepoRaiz 'dist\sidecar-hf\sidecar-hf.exe'
$Release  = Join-Path $GuiWeb 'release'

Write-Host "== Build ASSINADO (ADR-0021 / T-2402) ==" -ForegroundColor Cyan

# --- Le e valida as envs. Ausencia = aborto com mensagem clara. ---
$Pfx       = $env:HF_CSC_PFX
$SenhaTxt  = $env:HF_CSC_SENHA
$Publisher = if ($env:HF_CSC_PUBLISHER) { $env:HF_CSC_PUBLISHER } else { 'CN=Helper Financeiro (Teste)' }

if ([string]::IsNullOrWhiteSpace($Pfx) -or [string]::IsNullOrWhiteSpace($SenhaTxt)) {
    throw "Envs de assinatura ausentes. Defina HF_CSC_PFX (caminho do .pfx) e " +
          "HF_CSC_SENHA (senha) antes de rodar. Gere o cert com " +
          "scripts/preparar_cert_teste.ps1. (HF_CSC_PUBLISHER e opcional; " +
          "default '$Publisher'.)"
}
if (-not (Test-Path $Pfx)) {
    throw "HF_CSC_PFX aponta para um arquivo inexistente: $Pfx"
}
if (-not (Test-Path $Sidecar)) {
    throw "Sidecar nao encontrado em $Sidecar. Rode o PyInstaller antes: " +
          "uv run --group build pyinstaller SidecarHF.spec --noconfirm"
}

# --- Localiza o signtool.exe (Windows SDK; nao costuma estar no PATH). ---
function Find-Signtool {
    $bases = @(
        (Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' -ErrorAction SilentlyContinue),
        (Get-Item 'C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe' -ErrorAction SilentlyContinue)
    ) | ForEach-Object { $_ } | Where-Object { $_ }
    if (-not $bases) {
        $doPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
        if ($doPath) { return $doPath.Source }
        throw "signtool.exe nao encontrado. Instale o Windows SDK (Signing Tools)."
    }
    # Prefere a versao mais nova (ordena pelo nome da pasta de versao).
    return ($bases | Sort-Object FullName -Descending | Select-Object -First 1).FullName
}
$SignTool = Find-Signtool
Write-Host "  signtool: $SignTool"

# --- 1) Assina o sidecar no lugar (antes do empacotamento). ---
# NAO ecoamos a senha. /fd sha256 sem /tr (ver docstring: cert de teste, 30 dias).
Write-Host "  Assinando o sidecar: $Sidecar" -ForegroundColor White
& $SignTool sign /f $Pfx /p $SenhaTxt /fd sha256 $Sidecar
if ($LASTEXITCODE -ne 0) { throw "signtool falhou ao assinar o sidecar (exit $LASTEXITCODE)." }

# --- 2) npm run dist com os overrides de assinatura (sem tocar no package.json). ---
Write-Host "  Rodando npm run dist com overrides -c.win.signtoolOptions.*" -ForegroundColor White
$overrides = @(
    "-c.win.signtoolOptions.certificateFile=$Pfx",
    "-c.win.signtoolOptions.certificatePassword=$SenhaTxt",
    "-c.win.signtoolOptions.publisherName=$Publisher"
)
if ($VersaoFake) {
    Write-Host "  Versao sobrescrita (feed de update): $VersaoFake" -ForegroundColor White
    $overrides += "-c.extraMetadata.version=$VersaoFake"
}

Push-Location $GuiWeb
try {
    # `npm run dist -- <args>` -> os args caem no fim de `... && electron-builder --win`.
    & npm run dist -- @overrides
    if ($LASTEXITCODE -ne 0) { throw "npm run dist falhou (exit $LASTEXITCODE)." }
}
finally {
    Pop-Location
}

# --- 3) Verificacao: instalador + sidecar embarcado. ---
Write-Host ""
Write-Host "== Verificacao (Get-AuthenticodeSignature) ==" -ForegroundColor Cyan
Write-Host "Estados esperados: 'Valid' se o cert de teste estiver CONFIADO no host" -ForegroundColor DarkGray
Write-Host "(Root + TrustedPublisher); 'UnknownError' se NAO confiado (assinado, mas" -ForegroundColor DarkGray
Write-Host "cadeia nao verificavel). Qualquer status != NotSigned prova que assinou." -ForegroundColor DarkGray
Write-Host ""

$alvos = @()

# Pega o instalador mais RECENTE (release/ pode ter Setups antigos de outros
# builds) e exclui o __uninstaller (que tambem casa com *Setup*).
$instalador = Get-ChildItem -Path (Join-Path $Release '*.exe') -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*Setup*' -and $_.Name -notlike '*uninstaller*' } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($instalador) { $alvos += $instalador.FullName }
else { Write-Host "  AVISO: instalador (*Setup*.exe) nao encontrado em $Release" -ForegroundColor Yellow }

$sidecarEmbarcado = Join-Path $Release 'win-unpacked\resources\sidecar-hf\sidecar-hf.exe'
if (Test-Path $sidecarEmbarcado) { $alvos += $sidecarEmbarcado }
else { Write-Host "  AVISO: sidecar embarcado nao encontrado em $sidecarEmbarcado" -ForegroundColor Yellow }

foreach ($alvo in $alvos) {
    $sig = Get-AuthenticodeSignature -FilePath $alvo
    Write-Host ("  {0,-12} {1}" -f $sig.Status, $alvo) -ForegroundColor Green
    if ($sig.SignerCertificate) {
        Write-Host "               signer: $($sig.SignerCertificate.Subject)" -ForegroundColor DarkGray
    }
}
Write-Host ""
Write-Host "Build assinado concluido." -ForegroundColor Green
