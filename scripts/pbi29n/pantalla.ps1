# Utilidades de pantalla para capturar Power BI Desktop.
#   pantalla.ps1 -accion captura -salida C:\ruta\img.png
#   pantalla.ps1 -accion clic -x 640 -y 700
#   pantalla.ps1 -accion maximizar -proceso PBIDesktop
param([string]$accion = "captura", [string]$salida = "", [int]$x = 0, [int]$y = 0, [string]$proceso = "PBIDesktop")
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W32 {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[W32]::SetProcessDPIAware() | Out-Null
switch ($accion) {
  "captura" {
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $bmp.Save($salida, [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
    "$($b.Width)x$($b.Height) -> $salida"
  }
  "ventana" {
    # Captura la ventana del proceso aunque esté detrás de otras (PrintWindow con PW_RENDERFULLCONTENT).
    $p = Get-Process $proceso -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { "sin ventana"; break }
    $r = New-Object W32+RECT; [W32]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
    [W32]::PrintWindow($p.MainWindowHandle, $hdc, 2) | Out-Null
    $g.ReleaseHdc($hdc); $bmp.Save($salida, [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
    "ventana ${w}x${h} -> $salida"
  }
  "clic" {
    [W32]::SetCursorPos($x, $y) | Out-Null; Start-Sleep -Milliseconds 120
    [W32]::mouse_event(0x02, 0, 0, 0, [UIntPtr]::Zero); [W32]::mouse_event(0x04, 0, 0, 0, [UIntPtr]::Zero)
    [W32]::SetCursorPos(5, 5) | Out-Null
    "clic $x,$y"
  }
  "maximizar" {
    $p = Get-Process $proceso -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { [W32]::ShowWindow($p.MainWindowHandle, 3) | Out-Null; [W32]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; "maximizada: $($p.MainWindowTitle)" } else { "sin ventana" }
  }
}
