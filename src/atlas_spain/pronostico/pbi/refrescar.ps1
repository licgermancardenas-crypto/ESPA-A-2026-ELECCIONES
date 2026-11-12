# Refresca tablas del modelo en el Power BI Desktop abierto (servidor local de Analysis Services, XMLA).
# Uso: powershell -File powerbi_refrescar.ps1 -tablas "Noche,Noche UF"     (sin -tablas: todas, una por una)
param([string]$tablas = "")
$ErrorActionPreference = "Stop"
try { Add-Type -Path "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll" } catch { }
$raiz = "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"
$ws = Get-ChildItem $raiz -Directory | Sort-Object LastWriteTime -Descending |
      Where-Object { Test-Path "$($_.FullName)\Data\msmdsrv.port.txt" } | Select-Object -First 1
if (-not $ws) { "sin Power BI abierto"; exit }
$port = (Get-Content "$($ws.FullName)\Data\msmdsrv.port.txt" -Encoding Unicode).Trim()
$c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$port"
$c.Open()
$k = $c.CreateCommand(); $k.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
$r = $k.ExecuteReader(); $r.Read() | Out-Null; $db = $r.GetString(0); $r.Close()
$lista = if ($tablas) { $tablas.Split(",") } else {
  $k.CommandText = "SELECT [Name] FROM `$SYSTEM.TMSCHEMA_TABLES"; $r = $k.ExecuteReader(); $t = @()
  while ($r.Read()) { $t += $r.GetString(0) }; $r.Close(); $t }
foreach ($t in $lista) {
  $cmd = $c.CreateCommand()
  $cmd.CommandText = '{"refresh":{"type":"full","objects":[{"database":"' + $db + '","table":"' + $t.Trim() + '"}]}}'
  $cmd.ExecuteNonQuery() | Out-Null
}
$cmd = $c.CreateCommand(); $cmd.CommandText = '{"refresh":{"type":"calculate","objects":[{"database":"' + $db + '"}]}}'
$cmd.ExecuteNonQuery() | Out-Null
$c.Close()
"ok"
