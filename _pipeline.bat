@echo off
chcp 65001 >nul 2>&1
d:
cd "d:\codm\工具开发\合图规划工具"
echo ================================================
echo   V1.6.1 Build + Push Pipeline
echo ================================================

echo.
echo [1/4] Git commit...
git add -A
git commit -m "fix: grid display in smooth mode + title version + update checker SSL + auto-restart (V1.6.1)"
echo.

echo [2/4] Building EXE (this may take 2-3 min)...
python -m PyInstaller --clean --noconfirm TexturesAtlasView.spec
if not exist "dist\TexturesAtlasView.exe" (
    echo [FAIL] Build failed!
    exit /b 1
)
echo [OK] Build succeeded!
for %%A in ("dist\TexturesAtlasView.exe") do echo     Size: %%~zA bytes
echo.

echo [3/4] Git push...
git push origin main
echo.

echo [4/4] Tag v1.6.1...
git tag -d v1.6.0 2>nul
git push origin :refs/tags/v1.6.0 2>nul
git tag v1.6.1
git push origin v1.6.1
echo.

echo ================================================
echo   DONE! EXE: dist\TexturesAtlasView.exe
echo   Next: Create GitHub Release manually
echo   and upload dist\TexturesAtlasView.exe
echo ================================================
