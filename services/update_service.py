"""自动更新服务：基于 GitHub Releases 的检查更新、下载、替换"""

import os
import sys
import json
import ssl
import tempfile
import shutil
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal


# GitHub API 地址
GITHUB_API_LATEST = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_API_TAGS = "https://api.github.com/repos/{owner}/{repo}/tags"


def _compare_versions(local: str, remote: str) -> int:
    """比较版本号。返回 >0 表示远程更新，0 相同，<0 本地更新。

    支持格式: "1.4", "v1.5", "1.5.1" 等
    """
    def _parse(v: str):
        v = v.strip().lstrip("vV")
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return parts

    local_parts = _parse(local)
    remote_parts = _parse(remote)

    # 补齐长度
    max_len = max(len(local_parts), len(remote_parts))
    local_parts.extend([0] * (max_len - len(local_parts)))
    remote_parts.extend([0] * (max_len - len(remote_parts)))

    for l, r in zip(local_parts, remote_parts):
        if r > l:
            return 1
        elif r < l:
            return -1
    return 0


def _get_exe_path() -> Optional[str]:
    """获取当前运行的 EXE 路径（仅打包后有效）"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return None


def _create_ssl_contexts():
    """创建 SSL 上下文列表（先验证，后不验证），用于请求时按序尝试"""
    contexts = []
    # 1) 默认证书验证
    try:
        contexts.append(ssl.create_default_context())
    except Exception:
        pass
    # 2) 降级为不验证（仅用于 GitHub API，安全风险可控）
    try:
        contexts.append(ssl._create_unverified_context())
    except Exception:
        pass
    # 3) 兜底 None
    if not contexts:
        contexts.append(None)
    return contexts


def _urlopen_with_retry(req, timeout=15):
    """依次尝试多个 SSL 上下文发起请求，解决部分环境证书校验失败的问题"""
    contexts = _create_ssl_contexts()
    last_error = None
    for ctx in contexts:
        try:
            return urlopen(req, context=ctx, timeout=timeout)
        except (URLError, ssl.SSLError) as e:
            last_error = e
            continue
    raise last_error


class UpdateCheckResult:
    """检查更新的结果"""
    def __init__(self, has_update: bool = False, latest_version: str = "",
                 release_notes: str = "", download_url: str = "",
                 error: str = ""):
        self.has_update = has_update
        self.latest_version = latest_version
        self.release_notes = release_notes
        self.download_url = download_url
        self.error = error


class UpdateChecker(QObject):
    """后台线程检查更新 Worker"""

    check_finished = Signal(object)  # UpdateCheckResult

    def __init__(self, owner: str, repo: str, current_version: str, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._repo = repo
        self._current_version = current_version

    def run(self):
        """在后台线程执行检查（优先 Release，回退 Tags）"""

        # ---- 第一步：尝试 releases/latest ----
        release_result, release_error = self._check_release()
        if release_result is not None and release_result.has_update:
            self.check_finished.emit(release_result)
            return

        # ---- 第二步：Tags 回退 ----
        tag_result, tag_error = self._check_tags()
        if tag_result is not None and tag_result.has_update:
            self.check_finished.emit(tag_result)
            return

        # ---- 两边都没有更新 ----
        if release_result is not None:
            self.check_finished.emit(release_result)
        elif tag_result is not None:
            self.check_finished.emit(tag_result)
        elif release_error:
            self.check_finished.emit(UpdateCheckResult(error=release_error))
        elif tag_error:
            self.check_finished.emit(UpdateCheckResult(error=tag_error))
        else:
            self.check_finished.emit(UpdateCheckResult(error="尚无发布版本"))

    # ------------------------------------------------------------------
    def _check_release(self):
        """通过 releases/latest 检查。返回 (result_or_None, error_str_or_None)"""
        try:
            url = GITHUB_API_LATEST.format(owner=self._owner, repo=self._repo)
            req = Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("User-Agent", "TexturesAtlasView-Updater")

            with _urlopen_with_retry(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag = data.get("tag_name", "")
            body = data.get("body", "")
            assets = data.get("assets", [])

            # 查找 EXE 下载链接
            download_url = ""
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break

            # 如果没有找到 EXE，使用第一个 asset
            if not download_url and assets:
                download_url = assets[0].get("browser_download_url", "")

            has_update = _compare_versions(self._current_version, tag) > 0

            return UpdateCheckResult(
                has_update=has_update,
                latest_version=tag.lstrip("vV"),
                release_notes=body,
                download_url=download_url,
            ), None
        except HTTPError as e:
            if e.code == 404:
                return None, None  # 没有 release，回退到 tags
            return None, f"HTTP 错误: {e.code}"
        except URLError as e:
            reason = str(e.reason) if hasattr(e, 'reason') else str(e)
            return None, f"网络连接失败，请检查网络设置（{reason}）"
        except Exception as e:
            return None, str(e)

    # ------------------------------------------------------------------
    def _check_tags(self):
        """通过 tags 列表检查（回退方案）。返回 (result_or_None, error_str_or_None)"""
        try:
            url = GITHUB_API_TAGS.format(owner=self._owner, repo=self._repo)
            req = Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("User-Agent", "TexturesAtlasView-Updater")

            with _urlopen_with_retry(req, timeout=15) as resp:
                tags_data = json.loads(resp.read().decode("utf-8"))

            if not tags_data:
                return None, None

            # 找到最高版本的 tag
            best_tag = ""
            best_cmp = 0
            for item in tags_data:
                t = item.get("name", "")
                cmp = _compare_versions(self._current_version, t)
                if cmp > best_cmp:
                    best_cmp = cmp
                    best_tag = t
                elif cmp == 0 and not best_tag:
                    best_tag = t

            if not best_tag:
                # 没有比当前更新的 tag，取列表第一个作为展示
                best_tag = tags_data[0].get("name", "")

            has_update = _compare_versions(self._current_version, best_tag) > 0

            # Tags 没有 release notes / 下载链接，构造 GitHub Release 页面链接
            release_page = f"https://github.com/{self._owner}/{self._repo}/releases/tag/{best_tag}"

            return UpdateCheckResult(
                has_update=has_update,
                latest_version=best_tag.lstrip("vV"),
                release_notes=f"发现新 Tag {best_tag}，请前往 GitHub 查看详情。\n{release_page}" if has_update else "",
                download_url="",
            ), None
        except Exception as e:
            return None, str(e)


class UpdateDownloader(QObject):
    """后台线程下载更新 Worker"""

    progress = Signal(int, int)   # downloaded_bytes, total_bytes
    finished = Signal(str)        # temp_file_path
    error = Signal(str)

    def __init__(self, download_url: str, parent=None):
        super().__init__(parent)
        self._download_url = download_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        """在后台线程执行下载"""
        try:
            req = Request(self._download_url)
            req.add_header("User-Agent", "TexturesAtlasView-Updater")

            with _urlopen_with_retry(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                self.progress.emit(0, total)

                # 下载到临时文件
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe.tmp")
                try:
                    with os.fdopen(tmp_fd, "wb") as tmp_file:
                        downloaded = 0
                        chunk_size = 64 * 1024  # 64KB chunks
                        while True:
                            if self._cancelled:
                                os.unlink(tmp_path)
                                return

                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            tmp_file.write(chunk)
                            downloaded += len(chunk)
                            self.progress.emit(downloaded, total)
                except Exception:
                    # 清理临时文件
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise

            self.finished.emit(tmp_path)

        except Exception as e:
            self.error.emit(str(e))


def apply_update(temp_exe_path: str) -> Tuple[bool, str]:
    """应用更新：重命名当前 EXE → 移动新 EXE 到位

    Returns:
        (success, message)
    """
    current_exe = _get_exe_path()
    if not current_exe:
        return False, "非打包环境，无法自动更新"

    current_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)
    old_exe = current_exe + ".old"

    try:
        # 1. 将当前运行中的 EXE 重命名为 .old
        if os.path.exists(old_exe):
            os.remove(old_exe)
        os.rename(current_exe, old_exe)

        # 2. 将下载的新 EXE 移动到原位置
        shutil.move(temp_exe_path, current_exe)

        return True, "更新成功！请重启应用以使用新版本。"

    except Exception as e:
        # 回滚：尝试恢复旧 EXE
        try:
            if not os.path.exists(current_exe) and os.path.exists(old_exe):
                os.rename(old_exe, current_exe)
        except Exception:
            pass
        return False, f"更新失败: {e}"


def cleanup_old_exe():
    """启动时清理上次更新遗留的 .old 文件"""
    current_exe = _get_exe_path()
    if not current_exe:
        return
    old_exe = current_exe + ".old"
    if os.path.exists(old_exe):
        try:
            os.remove(old_exe)
        except Exception:
            pass  # 可能还被占用，下次再清理
