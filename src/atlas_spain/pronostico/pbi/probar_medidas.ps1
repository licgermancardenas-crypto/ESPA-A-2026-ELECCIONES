# Evalúa cada medida del modelo abierto en Power BI Desktop e informa errores o largo del resultado.
# Uso: powershell -File powerbi_probar_medidas.ps1
try { Add-Type -Path "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll" } catch { }
$raiz = "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"
$ws = Get-ChildItem $raiz -Directory | Sort-Object LastWriteTime -Descending |
      Where-Object { Test-Path "$($_.FullName)\Data\msmdsrv.port.txt" } | Select-Object -First 1
$port = (Get-Content "$($ws.FullName)\Data\msmdsrv.port.txt" -Encoding Unicode).Trim()
$c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$port"
$c.Open()
$k = $c.CreateCommand(); $k.CommandText = "SELECT [Name] FROM `$SYSTEM.TMSCHEMA_MEASURES"
$r = $k.ExecuteReader(); $med = @(); while ($r.Read()) { $med += $r.GetString(0) }; $r.Close()
foreach ($m in $med) {
  try {
    $k = $c.CreateCommand(); $k.CommandText = "EVALUATE ROW(""v"", [" + $m.Replace("]", "]]") + "])"
    $r = $k.ExecuteReader(); $r.Read() | Out-Null; $v = $r.GetValue(0); $r.Close()
    $txt = if ($v -is [string] -and $v.Length -gt 80) { "texto de $($v.Length) car." } else { "$v" }
    "OK    $m = $txt"
  } catch {
    $e = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
    "ERROR $m : " + $e.Substring(0, [Math]::Min(260, $e.Length))
  }
}
$c.Close()
