Add-Type -AssemblyName System.Drawing

$assetsDir = 'c:\Users\USER\veronica\apps\desktop\assets'
if (-not (Test-Path $assetsDir)) {
    New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null
}

$size = 64
$bmp = New-Object System.Drawing.Bitmap $size, $size
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::FromArgb(5, 8, 17))

# Outer Glow & Ring
$cyanPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(0, 243, 255)), 4
$g.DrawEllipse($cyanPen, 4, 4, 55, 55)

# Inner Ring
$bluePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(0, 119, 255)), 3
$g.DrawEllipse($bluePen, 14, 14, 35, 35)

# Center Core
$coreBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(0, 243, 255))
$g.FillEllipse($coreBrush, 24, 24, 15, 15)

# Tick marks
$tickPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(180, 0, 243, 255)), 2
$g.DrawLine($tickPen, 32, 4, 32, 12)
$g.DrawLine($tickPen, 32, 51, 32, 59)
$g.DrawLine($tickPen, 4, 32, 12, 32)
$g.DrawLine($tickPen, 51, 32, 59, 32)

$hIcon = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hIcon)
$icoPath = Join-Path $assetsDir 'veronica.ico'
$fileStream = [System.IO.File]::Open($icoPath, [System.IO.FileMode]::Create)
$icon.Save($fileStream)
$fileStream.Close()
$bmp.Dispose()
$g.Dispose()

Write-Host "Veronica Tray Icon generated: $icoPath"
