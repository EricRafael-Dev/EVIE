@echo off
title Evie Mobile - Compilador de APK
cd /d "%~dp0"

echo ========================================================
echo        COMPILADOR DE APK NATIVO - EVIE MOBILE
echo ========================================================
echo.

if "%JAVA_HOME%"=="" (
    if exist "%USERPROFILE%\.jdks\jbr-21.0.11" (
        set "JAVA_HOME=%USERPROFILE%\.jdks\jbr-21.0.11"
        set "PATH=%USERPROFILE%\.jdks\jbr-21.0.11\bin;%PATH%"
    ) else if exist "C:\Program Files\Android\Android Studio\jbr" (
        set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
        set "PATH=C:\Program Files\Android\Android Studio\jbr\bin;%PATH%"
    )
)

where java >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [AVISO] Java JDK nao detectado no PATH do sistema.
    echo Para compilar o APK, certifique-se de ter o JDK 17 e o Android SDK instalados,
    echo ou abra a pasta 'mobile_app' diretamente no Android Studio.
    echo.
    pause
    exit /b 1
)

echo Iniciando compilacao Gradle...
call gradlew.bat assembleDebug

if exist "app\build\outputs\apk\debug\app-debug.apk" (
    copy /y "app\build\outputs\apk\debug\app-debug.apk" "Evie-poco-x7.apk"
    echo.
    echo ========================================================
    echo [SUCESSO] APK compilado com sucesso!
    echo Arquivo pronto para instalar no seu Poco X7:
    echo %~dp0Evie-poco-x7.apk
    echo ========================================================
) else (
    echo [ERRO] Falha ao gerar o arquivo APK. Verifique os logs acima.
)

echo.
pause
