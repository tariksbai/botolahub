<#
.SYNOPSIS
    Contrôle (et corrige si demandé) le fuseau horaire des calendriers Outlook
    de toutes les boîtes aux lettres Exchange Online du CSEFRS.

.DESCRIPTION
    Pour chaque boîte aux lettres, le script lit deux paramètres :
      - TimeZone              (Get-MailboxRegionalConfiguration)  -> fuseau du calendrier / OWA / nouvel Outlook
      - WorkingHoursTimeZone  (Get-MailboxCalendarConfiguration)  -> fuseau des heures de travail (disponibilités)

    Une boîte est "conforme" si les deux valent le fuseau cible : par défaut "UTC"
    (GMT+0 fixe, sans heure d'été), heure de Casablanca retenue par le CSEFRS.

    ATTENTION : l'identifiant Windows "Morocco Standard Time" ("(UTC+01:00) Casablanca")
    correspond à GMT+1 ; il n'est donc PAS utilisé ici.

    Sans -Apply  : contrôle seul, AUCUNE modification. Export CSV + synthèse à l'écran.
    Avec -Apply  : corrige les boîtes non conformes (supporte -WhatIf et -Confirm).

.PARAMETER Identity
    Une ou plusieurs boîtes à traiter (adresse SMTP, UPN, alias). Par défaut : toutes.

.PARAMETER TimeZone
    Identifiant Windows du fuseau cible. Par défaut "UTC" (GMT+0 fixe).
    Équivalent possible : "Greenwich Standard Time" ("(UTC+00:00) Monrovia, Reykjavik").
    À éviter : "GMT Standard Time" (Londres, passe à GMT+1 l'été) et
    "Morocco Standard Time" (GMT+1).

.PARAMETER RecipientTypeDetails
    Types de boîtes à inclure. Par défaut : utilisateurs, partagées, salles et équipements.

.PARAMETER Apply
    Applique les corrections. Sans ce commutateur, le script ne modifie rien.

.PARAMETER ReportPath
    Chemin du rapport CSV. Par défaut : .\CSEFRS-CalendarTimeZone-<date>.csv

.EXAMPLE
    .\Set-CSEFRS-CalendarTimeZone.ps1
    Contrôle seul de toutes les boîtes : CSV + synthèse.

.EXAMPLE
    .\Set-CSEFRS-CalendarTimeZone.ps1 -Identity tsbai@csefrs.ma -Apply
    Test de la correction sur un seul compte.

.EXAMPLE
    .\Set-CSEFRS-CalendarTimeZone.ps1 -Apply
    Correction de toutes les boîtes non conformes.

.NOTES
    Prérequis : module ExchangeOnlineManagement (v3+) et un rôle Exchange Administrator
    (ou Recipient Management). Install-Module ExchangeOnlineManagement -Scope CurrentUser
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [string[]] $Identity,

    [string] $TimeZone = 'UTC',

    [ValidateSet('UserMailbox', 'SharedMailbox', 'RoomMailbox', 'EquipmentMailbox')]
    [string[]] $RecipientTypeDetails = @('UserMailbox', 'SharedMailbox', 'RoomMailbox', 'EquipmentMailbox'),

    [switch] $Apply,

    [string] $ReportPath = (Join-Path -Path (Get-Location) -ChildPath ("CSEFRS-CalendarTimeZone-{0:yyyyMMdd-HHmmss}.csv" -f (Get-Date)))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- 1. Vérification du fuseau cible -----------------------------------------
try {
    $tzInfo = [System.TimeZoneInfo]::FindSystemTimeZoneById($TimeZone)
    Write-Host ("Fuseau cible : {0} ({1})" -f $TimeZone, $tzInfo.DisplayName) -ForegroundColor Cyan
}
catch {
    Write-Warning "Fuseau '$TimeZone' introuvable localement ; Exchange Online le validera lors de l'application."
}

# --- 2. Connexion Exchange Online --------------------------------------------
if (-not (Get-Module -ListAvailable -Name ExchangeOnlineManagement)) {
    throw "Module ExchangeOnlineManagement absent. Installez-le : Install-Module ExchangeOnlineManagement -Scope CurrentUser"
}
Import-Module ExchangeOnlineManagement -ErrorAction Stop

$connected = $false
try {
    $connected = [bool](Get-ConnectionInformation | Where-Object { $_.State -eq 'Connected' })
}
catch { $connected = $false }

if (-not $connected) {
    Write-Host "Connexion à Exchange Online..." -ForegroundColor Cyan
    Connect-ExchangeOnline -ShowBanner:$false
}

# --- 3. Récupération des boîtes ----------------------------------------------
Write-Host "Récupération des boîtes aux lettres..." -ForegroundColor Cyan
if ($Identity) {
    $mailboxes = foreach ($id in $Identity) { Get-EXOMailbox -Identity $id }
}
else {
    $mailboxes = Get-EXOMailbox -ResultSize Unlimited -RecipientTypeDetails $RecipientTypeDetails
}
$mailboxes = @($mailboxes)
Write-Host ("{0} boîte(s) à contrôler." -f $mailboxes.Count) -ForegroundColor Cyan

# --- 4. Contrôle / correction ------------------------------------------------
$report = New-Object System.Collections.Generic.List[object]
$i = 0

foreach ($mbx in $mailboxes) {
    $i++
    $smtp = $mbx.PrimarySmtpAddress.ToString()
    Write-Progress -Activity 'Contrôle des fuseaux horaires' -Status $smtp -PercentComplete (($i / [math]::Max($mailboxes.Count, 1)) * 100)

    $row = [ordered]@{
        DisplayName                 = $mbx.DisplayName
        PrimarySmtpAddress          = $smtp
        RecipientTypeDetails        = $mbx.RecipientTypeDetails
        TimeZoneAvant               = $null
        WorkingHoursTimeZoneAvant   = $null
        Conforme                    = $false
        Action                      = 'Aucune'
        TimeZoneApres               = $null
        WorkingHoursTimeZoneApres   = $null
        Erreur                      = $null
    }

    try {
        $regional = Get-MailboxRegionalConfiguration -Identity $smtp
        $calendar = Get-MailboxCalendarConfiguration -Identity $smtp

        $row.TimeZoneAvant             = $regional.TimeZone
        $row.WorkingHoursTimeZoneAvant = $calendar.WorkingHoursTimeZone

        $regionalOk = ($regional.TimeZone -eq $TimeZone)
        $workingOk  = ($calendar.WorkingHoursTimeZone -eq $TimeZone)
        $row.Conforme = ($regionalOk -and $workingOk)

        if ($row.Conforme) {
            $row.Action = 'Déjà conforme'
        }
        elseif (-not $Apply) {
            $row.Action = 'À corriger (contrôle seul)'
        }
        elseif ($PSCmdlet.ShouldProcess($smtp, "Fuseau calendrier -> $TimeZone")) {
            $done = @()
            if (-not $regionalOk) {
                Set-MailboxRegionalConfiguration -Identity $smtp -TimeZone $TimeZone
                $done += 'TimeZone'
            }
            if (-not $workingOk) {
                Set-MailboxCalendarConfiguration -Identity $smtp -WorkingHoursTimeZone $TimeZone
                $done += 'WorkingHoursTimeZone'
            }
            $row.Action = 'Corrigé : ' + ($done -join ', ')

            $row.TimeZoneApres             = (Get-MailboxRegionalConfiguration -Identity $smtp).TimeZone
            $row.WorkingHoursTimeZoneApres = (Get-MailboxCalendarConfiguration -Identity $smtp).WorkingHoursTimeZone
            $row.Conforme = ($row.TimeZoneApres -eq $TimeZone -and $row.WorkingHoursTimeZoneApres -eq $TimeZone)
        }
        else {
            $row.Action = 'Ignoré (WhatIf / refus)'
        }
    }
    catch {
        $row.Action = 'Erreur'
        $row.Erreur = $_.Exception.Message
        Write-Warning "$smtp : $($_.Exception.Message)"
    }

    $report.Add([pscustomobject]$row)
}
Write-Progress -Activity 'Contrôle des fuseaux horaires' -Completed

# --- 5. Rapport --------------------------------------------------------------
$report | Export-Csv -Path $ReportPath -NoTypeInformation -Encoding UTF8 -Delimiter ';' -WhatIf:$false

$total      = $report.Count
$conformes  = @($report | Where-Object { $_.Conforme }).Count
$corriges   = @($report | Where-Object { $_.Action -like 'Corrigé*' }).Count
$aCorriger  = @($report | Where-Object { -not $_.Conforme -and $_.Action -ne 'Erreur' }).Count
$erreurs    = @($report | Where-Object { $_.Action -eq 'Erreur' }).Count

Write-Host ''
Write-Host '===== Synthèse =====' -ForegroundColor Cyan
Write-Host ("Mode                  : {0}" -f $(if ($Apply) { 'CORRECTION' } else { 'Contrôle seul (aucune modification)' }))
Write-Host ("Fuseau cible          : {0}" -f $TimeZone)
Write-Host ("Boîtes contrôlées     : {0}" -f $total)
Write-Host ("Conformes             : {0}" -f $conformes) -ForegroundColor Green
if ($Apply) { Write-Host ("Corrigées             : {0}" -f $corriges) -ForegroundColor Green }
Write-Host ("Non conformes         : {0}" -f $aCorriger) -ForegroundColor $(if ($aCorriger) { 'Yellow' } else { 'Green' })
Write-Host ("Erreurs               : {0}" -f $erreurs)   -ForegroundColor $(if ($erreurs) { 'Red' } else { 'Green' })
Write-Host ''
Write-Host 'Répartition des fuseaux actuels (TimeZone avant) :' -ForegroundColor Cyan
$report | Group-Object -Property TimeZoneAvant | Sort-Object -Property Count -Descending | ForEach-Object {
    $name = if ($_.Name) { $_.Name } else { '(non défini)' }
    Write-Host ("  {0,-40} {1,6}" -f $name, $_.Count)
}
Write-Host ''
Write-Host ("Rapport CSV : {0}" -f $ReportPath) -ForegroundColor Cyan
