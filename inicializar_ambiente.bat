@echo off

echo Iniciando o ambiente do projeto...

:: 1. Servidor IA
start "Servidor IA" cmd /k "cd /d C:\Users\eduardo\NAO_Projeto && venv\Scripts\activate && cd servidor && python servidor_ia.py"

:: 2. Forge
start "Forge WebUI" cmd /k "cd /d C:\Users\eduardo\Forge && webui-user.bat"

:: 3. Story Client
start "Story Client" cmd /k "cd /d C:\Users\eduardo\NAO_Projeto && venv\Scripts\activate && node story_client.js"

echo Todos os terminais foram abertos!