$jdkPath = "C:\Users\Rafael\.jdks\jbr-21.0.11"
$env:JAVA_HOME = $jdkPath
$env:Path = "$jdkPath\bin;$($env:Path)"
Set-Location "c:\Users\Rafael\OneDrive\Documentos\Mark-LV-main\Mark-LV-main\mobile_app"

Write-Host "Iniciando compilacao do APK..." -ForegroundColor Cyan
& .\gradlew.bat assembleDebug

if (Test-Path "app\build\outputs\apk\debug\app-debug.apk") {
    Copy-Item -Path "app\build\outputs\apk\debug\app-debug.apk" -Destination "Evie-poco-x7.apk" -Force
    Write-Host "APK compilado com sucesso e atualizado em Evie-poco-x7.apk!" -ForegroundColor Green
} else {
    Write-Host "Erro: app-debug.apk nao encontrado." -ForegroundColor Red
    exit 1
}
