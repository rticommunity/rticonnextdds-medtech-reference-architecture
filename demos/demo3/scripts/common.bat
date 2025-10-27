@echo off

REM Store the first argument if provided
set "SEC_FLAG=%1"

REM Apply Security QoS if needed
if "%SEC_FLAG%"=="-s" (
    echo Launching applications with Security...
    set "APPS_QOS_FILE=..\..\system_arch\qos\SecureAppsQos.xml"
) else if "%SEC_FLAG%"=="" (
    echo Launching applications without Security...
    set "APPS_QOS_FILE=..\..\system_arch\qos\NonSecureAppsQos.xml"
) else (
    echo Unknown argument: %SEC_FLAG%. Use -s to run with Security. Don't use any argument to run without security
    exit /b 1
)

set "QOS_FILE=..\..\system_arch\qos\Qos.xml"

set "NDDS_QOS_PROFILES=%QOS_FILE%;%APPS_QOS_FILE%"
