#Requires -Version 7
<#
.SYNOPSIS
    Gera um certificado de assinatura de codigo DE TESTE (ADR-0021, M24/T-2402).

.DESCRIPTION
    Fase 1 do code signing (C-15): enquanto a aprovacao do SignPath nao sai, um
    certificado auto-assinado destrava toda a parte REPRODUTIVEL do pipeline
    (assinar o sidecar, assinar o instalador, verificar o electron-updater e o
    degrau final do smoke de auto-update). Este cert NUNCA vai a producao: o
    publisher e falso e nao melhora nada para o usuario (ADR-0021, alternativas
    rejeitadas).

    Porque as decisoes abaixo:
      - Validade 30 dias (-NotAfter): trava anti-esquecimento. Se o cert de teste
        for confiado no host e esquecido, ele caduca sozinho (risco aceito na ADR).
      - PFX SEMPRE fora do repo (parametro -PfxPath, default em ~/.hf-signing):
        chave privada nunca versionada (REQ-SEC-001). O .gitignore ainda ganha
        *.pfx como segunda barreira.
      - Senha por parametro (SecureString), NUNCA hardcoded: nenhum segredo no
        arquivo do repo nem em log.
      - Confianca (import em Root/TrustedPublisher) NAO e feita aqui: mexer no
        Trusted Root e mudanca de seguranca do host, portao MANUAL do mantenedor
        por decisao da ADR. O script so IMPRIME as instrucoes.
      - Idempotente: remove qualquer cert anterior no My com o mesmo Subject antes
        de criar, para rodar 2x nao deixar lixo acumulado no store.

.EXAMPLE
    $s = Read-Host -AsSecureString 'Senha do PFX'
    pwsh scripts/preparar_cert_teste.ps1 -Senha $s
#>
[CmdletBinding()]
param(
    # Senha do PFX exportado. SecureString para nao trafegar em texto plano.
    [Parameter(Mandatory)]
    [System.Security.SecureString]$Senha,

    # Destino do PFX — SEMPRE fora do repo. Default no perfil do usuario.
    [string]$PfxPath = (Join-Path $env:USERPROFILE '.hf-signing\teste.pfx')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Subject unico do cert de teste (ADR-0021, publisherName da fase 1). O mesmo
# valor e o default de HF_CSC_PUBLISHER em build_assinado.ps1.
$SubjectCert = 'CN=Helper Financeiro (Teste)'

Write-Host "== Preparar certificado de TESTE (ADR-0021 / T-2402) ==" -ForegroundColor Cyan

# --- Idempotencia: limpa certs antigos com o mesmo Subject no store pessoal. ---
$antigos = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object { $_.Subject -eq $SubjectCert }
foreach ($c in $antigos) {
    Write-Host "  Removendo cert anterior do My: $($c.Thumbprint)" -ForegroundColor DarkYellow
    Remove-Item -Path "Cert:\CurrentUser\My\$($c.Thumbprint)" -Force
}

# --- Cria o cert de assinatura de codigo (validade 30 dias). ---
# -KeyExportPolicy Exportable e obrigatorio para o Export-PfxCertificate levar a
# chave privada junto (senao o PFX sai sem chave e nao assina).
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $SubjectCert `
    -NotAfter (Get-Date).AddDays(30) `
    -CertStoreLocation 'Cert:\CurrentUser\My' `
    -KeyUsage DigitalSignature `
    -KeyExportPolicy Exportable

$thumb = $cert.Thumbprint
Write-Host "  Certificado criado. Thumbprint: $thumb" -ForegroundColor Green
Write-Host "  Validade ate: $($cert.NotAfter.ToString('yyyy-MM-dd'))"

# --- Exporta o PFX (fora do repo). Garante a pasta destino. ---
$pfxDir = Split-Path -Parent $PfxPath
if (-not (Test-Path $pfxDir)) {
    New-Item -ItemType Directory -Path $pfxDir -Force | Out-Null
}
Export-PfxCertificate `
    -Cert "Cert:\CurrentUser\My\$thumb" `
    -FilePath $PfxPath `
    -Password $Senha | Out-Null
Write-Host "  PFX exportado para: $PfxPath" -ForegroundColor Green

# Caminho sugerido para a parte publica (.cer) usada nos imports de confianca.
$cerPath = [System.IO.Path]::ChangeExtension($PfxPath, '.cer')

# --- Instrucoes (o script NAO executa nada abaixo — portao manual). ---
Write-Host ""
Write-Host "== PROXIMOS PASSOS (execucao MANUAL do mantenedor) ==" -ForegroundColor Cyan
Write-Host ""
Write-Host "1) USAR no build assinado (defina as envs e rode build_assinado.ps1):" -ForegroundColor White
Write-Host "     `$env:HF_CSC_PFX   = '$PfxPath'"
Write-Host "     `$env:HF_CSC_SENHA = '<a senha que voce escolheu>'"
Write-Host "     pwsh scripts/build_assinado.ps1"
Write-Host ""
Write-Host "2) CONFIAR no cert de teste (SO no seu host de teste; caduca em 30 dias)." -ForegroundColor White
Write-Host "   Necessario para o Get-AuthenticodeSignature virar 'Valid' e para o"
Write-Host "   smoke de auto-update (T-2403). Exporta a parte PUBLICA e importa em"
Write-Host "   Root (cadeia) e TrustedPublisher (publisher):"
Write-Host "     Export-Certificate -Cert 'Cert:\CurrentUser\My\$thumb' -FilePath '$cerPath'"
Write-Host "     Import-Certificate -FilePath '$cerPath' -CertStoreLocation Cert:\CurrentUser\Root"
Write-Host "     Import-Certificate -FilePath '$cerPath' -CertStoreLocation Cert:\CurrentUser\TrustedPublisher"
Write-Host ""
Write-Host "3) REMOVER tudo quando terminar (limpa store + PFX + .cer):" -ForegroundColor White
Write-Host "     Remove-Item 'Cert:\CurrentUser\My\$thumb' -Force"
Write-Host "     Remove-Item 'Cert:\CurrentUser\Root\$thumb' -Force -ErrorAction SilentlyContinue"
Write-Host "     Remove-Item 'Cert:\CurrentUser\TrustedPublisher\$thumb' -Force -ErrorAction SilentlyContinue"
Write-Host "     Remove-Item '$PfxPath' -Force -ErrorAction SilentlyContinue"
Write-Host "     Remove-Item '$cerPath' -Force -ErrorAction SilentlyContinue"
Write-Host ""
Write-Host "Thumbprint (guarde para a remocao): $thumb" -ForegroundColor Yellow
