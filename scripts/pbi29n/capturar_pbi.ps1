# Captura páginas del tablero en Power BI Desktop, una por vez (equipos con poca RAM).
# Requiere haber guardado antes el proyecto con datos (SemanticModel\.pbi\cache.abf).
# Uso: powershell -File capturar_pbi.ps1 -paginas "p01_panel,p02_mapa|Organización gobernante 2023=Participación 2023" -salida C:\carpeta
#      cada página admite cambios de segmentador tras "|" separados por "|" (valor_actual=valor_nuevo)
param([string]$paginas, [string]$salida, [int]$espera = 35, [string]$clics = "")
$raiz = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pan = Join-Path $PSScriptRoot "pantalla.ps1"
New-Item -ItemType Directory -Force $salida | Out-Null
$i = 0
foreach ($item in $paginas.Split(",")) {
  $i++
  $partes = $item.Split("|"); $pg = $partes[0]; $cambios = @($partes | Select-Object -Skip 1)
  Push-Location $raiz; python scripts/pbi29n/pbi_una_pagina.py $pg @cambios | Out-Null; Pop-Location
  Start-Process "C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe" -ArgumentList ('"' + "$raiz\reports\powerbi_29n\captura\ATLAS_captura.pbip" + '"')
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    $p = Get-Process PBIDesktop -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -match 'ATLAS' } | Select-Object -First 1
    if ($p) { break }; Start-Sleep 2
  }
  powershell -NoProfile -File $pan -accion maximizar | Out-Null
  Start-Sleep $espera
  if ($clics) { foreach ($c in $clics.Split(";")) { $xy = $c.Split(","); powershell -NoProfile -File $pan -accion clic -x $xy[0] -y $xy[1] | Out-Null; Start-Sleep 2 } ; Start-Sleep 6 }
  $vivo = [bool](Get-Process PBIDesktop -ErrorAction SilentlyContinue)
  $f = Join-Path $salida ("{0:D2}_{1}.png" -f $i, $pg)
  powershell -NoProfile -File $pan -accion ventana -salida $f | Out-Null
  "$pg -> $f (Power BI vivo: $vivo, $([int]((Get-Date)-$t0).TotalSeconds) s)"
  Get-Process PBIDesktop, msmdsrv -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep 4
}
