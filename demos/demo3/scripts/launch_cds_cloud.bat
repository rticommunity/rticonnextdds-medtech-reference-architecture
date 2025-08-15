@echo off

REM Store the "-s" argument if provided
set "SEC_FLAG=%1"

REM Set up XML-related variables (QoS, XML App Creation, etc.)
call ".\scripts\variables.bat"

REM Apply Security QoS if needed
if "%SEC_FLAG%"=="-s" (
    echo Launching CDS with Security...
    set "CFG_NAME=CdsConfigCloudSecurity"
) else if "%SEC_FLAG%"=="" (
    echo Launching CDS without Security...
    set "CFG_NAME=CdsConfigCloud"
) else (
    echo Unknown argument: %SEC_FLAG%. Use -s to run with Security. Don't use any argument to run without security
    exit /b 1
)

REM Start the process
%NDDSHOME%\bin\rticlouddiscoveryservice -cfgFile ".\xml_config\CdsConfigCloud.xml" -cfgName %CFG_NAME%