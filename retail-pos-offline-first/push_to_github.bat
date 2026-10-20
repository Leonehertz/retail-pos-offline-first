@echo off
title Subir Proyecto a GitHub - Felipe Poblete
color 0b
echo =====================================================================
echo  SUBIENDO ARQUITECTURA DISTRIBUIDA POS A GITHUB (Leonehertz)
echo =====================================================================
echo.
cd /d "%~dp0"

echo 1. Inicializando repositorio Git local...
git init
echo.

echo 2. Agregando archivos limpios y sanitizados...
git add .
echo.

echo 3. Creando Commit inicial profesional...
git commit -m "feat: Initial architecture showcase for Distributed Offline-First Retail POS"
git branch -M main
echo.

echo =====================================================================
echo PASO FINAL:
echo Ve a tu GitHub (https://github.com/new) y crea un nuevo repositorio
echo con el nombre exacto: retail-pos-offline-first
echo (Dejalo Publico y NO marques agregar README ni .gitignore).
echo =====================================================================
echo.
pause

echo.
echo 4. Vinculando con tu cuenta de GitHub (github.com/Leonehertz)...
git remote remove origin 2>nul
git remote add origin https://github.com/Leonehertz/retail-pos-offline-first.git

echo.
echo 5. Subiendo codigo a GitHub...
git push -u origin main

echo.
echo =====================================================================
echo Proceso finalizado con exito!
echo Revisa tu perfil en: https://github.com/Leonehertz/retail-pos-offline-first
echo =====================================================================
pause
