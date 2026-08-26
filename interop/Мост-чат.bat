@echo off
rem Zapusk prosmotra perepiski Claude-Codex (dvojnoj klik)
start "most-claude-codex" /min python "%USERPROFILE%\.claude\scripts\interop_chat_server.py"
timeout /t 1 >nul
start "" http://127.0.0.1:7343
