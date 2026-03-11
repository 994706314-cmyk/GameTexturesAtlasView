@echo off
chcp 65001 >nul 2>&1
d:
cd "d:\codm\工具开发\合图规划工具"
git add -A
git status --short
git commit -m "fix: grid display in smooth mode + title version + update checker SSL + auto-restart (V1.6.1)"
git push origin main
echo.
git tag -d v1.6.0 2>nul
git push origin :refs/tags/v1.6.0 2>nul
git tag v1.6.1
git push origin v1.6.1
echo PUSH_DONE
