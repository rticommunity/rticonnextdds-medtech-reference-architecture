@echo off
REM Store the "-s" argument if provided
set "SEC_FLAG=%1"

REM Set up XML-related variables (QoS, XML App Creation, etc.)
call ".\scripts\variables.bat"
call ".\scripts\common.bat" %SEC_FLAG%

REM Start the process
%NDDSHOME%\bin\rtiroutingservice -cfgFile ".\xml_config\RsConfigPassive.xml" -cfgName RsConfigPassive