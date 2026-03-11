@echo off
chcp 65001 >nul 2>&1
d:
cd "d:\codm\工具开发\合图规划工具"
git add -A
git commit -m "chore: remove temp build scripts"
git push origin main
git tag -d v1.6.1 2>nul
git push origin :refs/tags/v1.6.1 2>nul
git tag v1.6.1
git push origin v1.6.1
echo CLEANUP_DONE
