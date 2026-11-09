# Ejecuta una consulta DAX contra el Power BI Desktop abierto e imprime el resultado (TSV).
# Uso: powershell -File powerbi_consultar.ps1 -dax "EVALUATE ROW(""x"", [Población])"
param([Parameter(Mandatory=$true)][string]$dax)
$ErrorActionPreference = "Stop"
try { Add-Type -Path "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll" } catch { }
$raiz = "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"
$ws = Get-ChildItem $raiz -Directory | Sort-Object LastWriteTime -Descending |
      Where-Object { Test-Path "$($_.FullName)\Data\msmdsrv.port.txt" } | Select-Object -First 1
$port = (Get-Content "$($ws.FullName)\Data\msmdsrv.port.txt" -Encoding Unicode).Trim()
$c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$port"
$c.Open()
$k = $c.CreateCommand(); $k.CommandText = $dax
$r = $k.ExecuteReader()
$n = $r.FieldCount
($(0..($n-1) | ForEach-Object { $r.GetName($_) }) -join "`t")
while ($r.Read()) { ($(0..($n-1) | ForEach-Object { $v = $r.GetValue($_); if ($v -is [string] -and $v.Length -gt 160) { "[texto " + $v.Length + " car.] " + $v.Substring(0,90) } else { $v } }) -join "`t") }
$r.Close(); $c.Close()
