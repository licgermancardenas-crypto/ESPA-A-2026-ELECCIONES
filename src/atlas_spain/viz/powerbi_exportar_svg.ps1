# Ejecuta una consulta DAX (leída de un archivo UTF-8) que devuelve una medida SVG y guarda el SVG.
# Uso: powershell -File powerbi_exportar_svg.ps1 -file consulta.dax -out mapa.svg
param([Parameter(Mandatory=$true)][string]$file, [Parameter(Mandatory=$true)][string]$out)
$ErrorActionPreference = "Stop"
try { Add-Type -Path "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll" } catch { }
$dax = [IO.File]::ReadAllText($file, [Text.Encoding]::UTF8)
$raiz = "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"
$ws = Get-ChildItem $raiz -Directory | Sort-Object LastWriteTime -Descending |
      Where-Object { Test-Path "$($_.FullName)\Data\msmdsrv.port.txt" } | Select-Object -First 1
$port = (Get-Content "$($ws.FullName)\Data\msmdsrv.port.txt" -Encoding Unicode).Trim()
$c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$port"; $c.Open()
$k = $c.CreateCommand(); $k.CommandText = $dax; $r = $k.ExecuteReader(); $r.Read() | Out-Null
$v = $r.GetString($r.FieldCount - 1); $r.Close(); $c.Close()
$v = [System.Uri]::UnescapeDataString($v.Substring($v.IndexOf(",") + 1))
[IO.File]::WriteAllText($out, $v, (New-Object System.Text.UTF8Encoding $false))
