"""自动更新服务：基于 GitHub Releases 的检查更新、下载、替换

检查策略（按优先级）：
  1. 访问 releases/latest 页面 → 302 重定向获取最新 tag（不走 API，无限流）
  2. 解析 releases.atom feed 获取最新 tag（Atom 不受 API 限流）
  3. 回退到 GitHub API（可能 403）

下载链接直接构造：
  https://github.com/{owner}/{repo}/releases/download/{tag}/TexturesAtlasView.exe
"""

import os
import sys
import re
import ssl
import json
import tempfile
import shutil
from urllib.request import urlopen, Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError, HTTPError
from typing import Optional, Tuple
from xml.etree import ElementTree

from PySide6.QtCore import QObject, QThread, Signal


# ============================================================
#  URL 模板（不使用 API，避免 60次/小时 的限流）
# ============================================================
GITHUB_RELEASE_LATEST = "https://github.com/{owner}/{repo}/releases/latest"
GITHUB_RELEASE_ATOM = "https://github.com/{owner}/{repo}/releases.atom"
# API 仅作最终回退
GITHUB_API_LATEST = "https://api.github.com/repos/{owner}/{repo}/releases/latest"


# ============================================================
#  工具函数
# ============================================================
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

    max_len = max(len(local_parts), len(remote_parts))
    local_parts.extend([0] * (max_len - len(local_parts)))
    remote_parts.extend([0] * (max_len - len(remote_parts)))

    for l_val, r_val in zip(local_parts, remote_parts):
        if r_val > l_val:
            return 1
        elif r_val < l_val:
            return -1
    return 0


def _get_exe_path() -> Optional[str]:
    """获取当前运行的 EXE 路径（仅打包后有效）"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return None


def _create_ssl_contexts():
    """创建 SSL 上下文列表（先验证，后不验证）"""
    contexts = []
    try:
        contexts.append(ssl.create_default_context())
    except Exception:
        pass
    try:
        contexts.append(ssl._create_unverified_context())
    except Exception:
        pass
    if not contexts:
        contexts.append(None)
    return contexts


def _urlopen_with_retry(req, timeout=15):
    """依次尝试多个 SSL 上下文发起请求"""
    contexts = _create_ssl_contexts()
    last_error = None
    for ctx in contexts:
        try:
            return urlopen(req, context=ctx, timeout=timeout)
        except HTTPError:
            raise
        except (URLError, ssl.SSLError) as e:
            last_error = e
            continue
    raise last_error


class _NoRedirectHandler(HTTPRedirectHandler):
    """不跟随重定向，直接返回 302 响应"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_redirect_url(url: str, timeout: int = 10) -> Optional[str]:
    """获取 URL 的 302 重定向目标地址（不跟随重定向）"""
    contexts = _create_ssl_contexts()
    for ctx in contexts:
        try:
            import urllib.request
            handler = _NoRedirectHandler()
            if ctx:
                https_handler = urllib.request.HTTPSHandler(context=ctx)
                opener = build_opener(https_handler, handler)
            else:
                opener = build_opener(handler)
            req = Request(url)
            req.add_header("User-Agent", "TexturesAtlasView-Updater")
            resp = opener.open(req, timeout=timeout)
            # 200 表示没有重定向
            return resp.url if resp.url != url else None
        except HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                return e.headers.get("Location")
            return None
        except (URLError, ssl.SSLError):
            continue
        except Exception:
            return None
    return None


# ============================================================
#  检查更新结果
# ============================================================
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


# ============================================================
#  检查更新 Worker
# ============================================================
class UpdateChecker(QObject):
    """后台线程检查更新"""

    check_finished = Signal(object)  # UpdateCheckResult

    def __init__(self, owner: str, repo: str, current_version: str, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._repo = repo
        self._current_version = current_version

    def run(self):
        """在后台线程执行检查，按优先级尝试多种方式"""
        errors = []

        # 策略 1: releases/latest 页面重定向（最可靠，无限流）
        result, err = self._check_via_redirect()
        if result is not None:
            self.check_finished.emit(result)
            return
        if err:
            errors.append(err)

        # 策略 2: Atom feed（不受 API 限流）
        result, err = self._check_via_atom()
        if result is not None:
            self.check_finished.emit(result)
            return
        if err:
            errors.append(err)

        # 策略 3: GitHub API（可能 403，但作为最终回退）
        result, err = self._check_via_api()
        if result is not None:
            self.check_finished.emit(result)
            return
        if err:
            errors.append(err)

        # 全部失败
        self.check_finished.emit(
            UpdateCheckResult(error="; ".join(errors) if errors else "检查更新失败")
        )

    # ----------------------------------------------------------
    def _check_via_redirect(self):
        """策略 1: 通过 releases/latest 页面 302 重定向获取最新 tag"""
        try:
            url = GITHUB_RELEASE_LATEST.format(owner=self._owner, repo=self._repo)
            redirect_url = _get_redirect_url(url)
            if not redirect_url:
                return None, "releases 页面未重定向"

            # redirect_url 形如: https://github.com/owner/repo/releases/tag/v1.6.3
            match = re.search(r'/releases/tag/([^/]+)$', redirect_url)
            if not match:
                return None, f"无法解析重定向 URL: {redirect_url}"

            tag = match.group(1)
            return self._build_result(tag), None

        except Exception as e:
            return None, f"重定向检查失败: {e}"

    # ----------------------------------------------------------
    def _check_via_atom(self):
        """策略 2: 解析 releases.atom feed 获取最新版本"""
        try:
            url = GITHUB_RELEASE_ATOM.format(owner=self._owner, repo=self._repo)
            req = Request(url)
            req.add_header("User-Agent", "TexturesAtlasView-Updater")

            with _urlopen_with_retry(req, timeout=15) as resp:
                xml_data = resp.read().decode("utf-8")

            root = ElementTree.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)

            if not entries:
                return None, "Atom feed 无 release 条目"

            # 第一个 entry 就是最新版本
            first_entry = entries[0]
            link_el = first_entry.find("atom:link", ns)
            title_el = first_entry.find("atom:title", ns)
            content_el = first_entry.find("atom:content", ns)

            tag = ""
            if link_el is not None:
                href = link_el.get("href", "")
                match = re.search(r'/releases/tag/([^/]+)$', href)
                if match:
                    tag = match.group(1)

            if not tag and title_el is not None:
                tag = title_el.text.strip() if title_el.text else ""

            if not tag:
                return None, "Atom feed 无法提取 tag"

            notes = ""
            if content_el is not None and content_el.text:
                # content 是 HTML，简单去标签
                notes = re.sub(r'<[^>]+>', '', content_el.text).strip()

            return self._build_result(tag, notes), None

        except Exception as e:
            return None, f"Atom feed 检查失败: {e}"

    # ----------------------------------------------------------
    def _check_via_api(self):
        """策略 3: GitHub API（可能触发 403 限流）"""
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

            download_url = ""
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break
            if not download_url and assets:
                download_url = assets[0].get("browser_download_url", "")

            return self._build_result(tag, body, download_url), None

        except HTTPError as e:
            if e.code == 403:
                return None, "GitHub API 限流(403)"
            elif e.code == 404:
                return None, "无 release"
            return None, f"HTTP {e.code}"
        except URLError as e:
            reason = str(e.reason) if hasattr(e, 'reason') else str(e)
            return None, f"网络连接失败({reason})"
        except Exception as e:
            return None, str(e)

    # ----------------------------------------------------------
    def _build_result(self, tag: str, notes: str = "", download_url: str = "") -> UpdateCheckResult:
        """根据 tag 构造 UpdateCheckResult"""
        version = tag.lstrip("vV")
        has_update = _compare_versions(self._current_version, tag) > 0

        # 构造下载链接（如果没有从 API 获取到）
        if not download_url:
            download_url = (
                f"https://github.com/{self._owner}/{self._repo}"
                f"/releases/download/{tag}/TexturesAtlasView.exe"
            )

        if not notes and has_update:
            release_page = (
                f"https://github.com/{self._owner}/{self._repo}/releases/tag/{tag}"
            )
            notes = f"发现新版本 {tag}，请查看详情：\n{release_page}"

        return UpdateCheckResult(
            has_update=has_update,
            latest_version=version,
            release_notes=notes,
            download_url=download_url,
        )


# ============================================================
#  下载更新 Worker
# ============================================================
class UpdateDownloader(QObject):
    """后台线程下载更新"""

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

            with _urlopen_with_retry(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                self.progress.emit(0, total)

                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe.tmp")
                try:
                    with os.fdopen(tmp_fd, "wb") as tmp_file:
                        downloaded = 0
                        chunk_size = 128 * 1024  # 128KB chunks
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
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise

            self.finished.emit(tmp_path)

        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  应用更新 + 自动保存/恢复
# ============================================================
def get_update_state_path() -> str:
    """获取更新状态文件路径（保存更新前的项目路径，用于重启后恢复）"""
    exe = _get_exe_path()
    if exe:
        return os.path.join(os.path.dirname(exe), ".update_state.json")
    # 开发模式下放在项目根目录
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".update_state.json")


def save_update_state(project_path: Optional[str]):
    """更新前保存当前项目路径到状态文件"""
    state_path = get_update_state_path()
    try:
        state = {"project_path": project_path or ""}
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def load_and_clear_update_state() -> Optional[str]:
    """启动时读取并清除更新状态，返回更新前的项目路径（如有）"""
    state_path = get_update_state_path()
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        project_path = state.get("project_path", "")
        return project_path if project_path else None
    except Exception:
        return None
    finally:
        try:
            os.remove(state_path)
        except Exception:
            pass


def apply_update(temp_exe_path: str) -> Tuple[bool, str]:
    """应用更新：重命名当前 EXE → 移动新 EXE 到位

    Returns:
        (success, message)
    """
    current_exe = _get_exe_path()
    if not current_exe:
        return False, "非打包环境，无法自动更新"

    old_exe = current_exe + ".old"

    try:
        if os.path.exists(old_exe):
            os.remove(old_exe)
        os.rename(current_exe, old_exe)
        shutil.move(temp_exe_path, current_exe)
        return True, "更新成功，即将重启应用..."
    except Exception as e:
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
            pass
