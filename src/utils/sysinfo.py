# src/utils/sysinfo.py
from __future__ import annotations

import os
import re
import json
import shutil
import subprocess
import platform
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

try:
    import psutil  # optional
except Exception:
    psutil = None  # type: ignore


@dataclass
class ToolInfo:
    name: str
    version: str = ""
    path: str = ""
    ok: bool = False
    notes: str = ""


@dataclass
class GpuInfo:
    name: str
    driver: str = ""
    vram: str = ""
    vendor: str = ""
    raw: str = ""


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _run(cmd: List[str]) -> Tuple[bool, str]:
    try:
        si = None
        cf = 0
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            cf = subprocess.CREATE_NO_WINDOW

        out = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=si,
            creationflags=cf,
        )
        return True, out.strip()
    except Exception:
        return False, ""


def _first_line(s: str) -> str:
    return (s or "").splitlines()[0] if s else ""


def _parse_version_line(s: str) -> str:
    # keep it pragmatic; many tools print versions differently
    line = _first_line(s)
    m = re.search(r"(\d+\.\d+(?:\.\d+)?(?:[-\w.]+)?)", line)
    return m.group(1) if m else line


def _probe_tool(cmd: str, args: List[str], pretty: Optional[str] = None) -> ToolInfo:
    pretty = pretty or cmd
    p = _which(cmd)
    if not p:
        return ToolInfo(name=pretty, ok=False, notes="not found")
    ok, out = _run([p, *args])
    return ToolInfo(
        name=pretty,
        version=_parse_version_line(out) if ok else "",
        path=p,
        ok=ok,
        notes="" if ok else "error running --version"
    )


def get_languages_and_tools() -> Dict[str, List[ToolInfo]]:
    langs: List[ToolInfo] = []
    web: List[ToolInfo] = []
    build: List[ToolInfo] = []
    vcs: List[ToolInfo] = []

    # Languages / runtimes
    langs += [
        _probe_tool("python", ["--version"], "Python"),
        _probe_tool("py", ["-V"], "Python (py launcher)"),
        _probe_tool("java", ["-version"], "Java"),
        _probe_tool("javac", ["-version"], "Javac"),
        _probe_tool("node", ["-v"], "Node.js"),
        _probe_tool("deno", ["--version"], "Deno"),
        _probe_tool("bun", ["--version"], "Bun"),
        _probe_tool("go", ["version"], "Go"),
        _probe_tool("rustc", ["--version"], "Rust (rustc)"),
        _probe_tool("dotnet", ["--info"], ".NET"),
        _probe_tool("powershell", ["-Version"], "PowerShell"),
    ]

    # Web toolchain
    web += [
        _probe_tool("npm", ["-v"], "npm"),
        _probe_tool("pnpm", ["-v"], "pnpm"),
        _probe_tool("yarn", ["-v"], "yarn"),
        _probe_tool("pip", ["--version"], "pip"),
        _probe_tool("pipx", ["--version"], "pipx"),
    ]

    # C/C++ & build
    build += [
        _probe_tool("gcc", ["--version"], "gcc"),
        _probe_tool("g++", ["--version"], "g++"),
        _probe_tool("clang", ["--version"], "clang"),
        _probe_tool("clang++", ["--version"], "clang++"),
        _probe_tool("cmake", ["--version"], "CMake"),
        _probe_tool("make", ["--version"], "make"),
        _probe_tool("ninja", ["--version"], "ninja"),
        _probe_tool("cargo", ["--version"], "Cargo"),
        _probe_tool("mvn", ["-v"], "Maven"),
        _probe_tool("gradle", ["-v"], "Gradle"),
        _probe_tool("msbuild", ["/version"], "MSBuild"),
    ]

    # Version control
    vcs += [
        _probe_tool("git", ["--version"], "git"),
        _probe_tool("hg", ["--version"], "Mercurial"),
        _probe_tool("svn", ["--version"], "Subversion"),
    ]

    # De-dup by name keeping the one that ran successfully
    def dedup(items: List[ToolInfo]) -> List[ToolInfo]:
        seen: Dict[str, ToolInfo] = {}
        for t in items:
            if t.name not in seen or (not seen[t.name].ok and t.ok):
                seen[t.name] = t
        return list(seen.values())

    return {
        "Languages & Runtimes": dedup(langs),
        "Web / Package Managers": dedup(web),
        "Build Tools": dedup(build),
        "VCS": dedup(vcs),
    }


def get_gpu_info() -> List[GpuInfo]:
    gpus: List[GpuInfo] = []

    # 1) NVIDIA SMI
    nvsmi = _which("nvidia-smi")
    if nvsmi:
        ok, out = _run([nvsmi, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
        if ok and out:
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                name = parts[0] if len(parts) > 0 else "NVIDIA GPU"
                drv = parts[1] if len(parts) > 1 else ""
                mem = parts[2] if len(parts) > 2 else ""
                gpus.append(GpuInfo(name=name, driver=drv, vram=mem, vendor="NVIDIA", raw=line))
            return gpus

    # 2) Windows CIM/WMI
    if platform.system().lower() == "windows":
        # Try PowerShell CIM
        ps = _which("powershell")
        if ps:
            ok, out = _run([
                ps, "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name,DriverVersion,AdapterRAM | ConvertTo-Json"
            ])
            if ok and out:
                try:
                    data = json.loads(out)
                    if isinstance(data, dict):
                        data = [data]
                    for d in data:
                        name = d.get("Name", "")
                        drv = d.get("DriverVersion", "")
                        vram = d.get("AdapterRAM", "")
                        if isinstance(vram, int):
                            # bytes -> MB
                            vram = f"{vram/1024/1024:.0f} MB"
                        gpus.append(GpuInfo(name=name, driver=drv, vram=vram, vendor="", raw=str(d)))
                    if gpus:
                        return gpus
                except Exception:
                    pass
        # legacy wmic fallback
        wmic = _which("wmic")
        if wmic:
            ok, out = _run([wmic, "path", "win32_VideoController", "get", "Name,DriverVersion,AdapterRAM", "/format:csv"])
            if ok and out:
                for line in out.splitlines():
                    if not line or line.lower().startswith("node"):
                        continue
                    cols = [c.strip() for c in line.split(",")]
                    if len(cols) >= 4:
                        name, drv, ram = cols[2], cols[3], cols[1]
                        try:
                            ram_int = int(ram)
                            ram = f"{ram_int/1024/1024:.0f} MB"
                        except Exception:
                            pass
                        gpus.append(GpuInfo(name=name, driver=drv, vram=ram, vendor="", raw=line))
                if gpus:
                    return gpus

    # 3) macOS
    if platform.system().lower() == "darwin":
        ok, out = _run(["system_profiler", "SPDisplaysDataType", "-json"])
        if ok and out:
            try:
                data = json.loads(out)
                gpus_raw = data.get("SPDisplaysDataType", [])
                for g in gpus_raw:
                    name = g.get("_name", "")
                    vram = g.get("spdisplays_vram", "") or g.get("spdisplays_vram_shared", "")
                    gpus.append(GpuInfo(name=name, driver="", vram=vram, vendor="", raw=json.dumps(g)))
                if gpus:
                    return gpus
            except Exception:
                pass

    # 4) Linux (best effort)
    if platform.system().lower() == "linux":
        ok, out = _run(["bash", "-lc", "lspci | grep -iE 'vga|3d|display'"])
        if ok and out:
            for line in out.splitlines():
                gpus.append(GpuInfo(name=line, raw=line))
            if gpus:
                return gpus
        ok, out = _run(["bash", "-lc", "glxinfo -B"])
        if ok and out:
            name = ""
            for ln in out.splitlines():
                if "Device:" in ln or "OpenGL renderer string:" in ln:
                    name = ln.split(":", 1)[-1].strip()
            if name:
                gpus.append(GpuInfo(name=name, raw=out))
                return gpus

    # Fallback: none
    return gpus


def get_system_summary() -> Dict[str, str]:
    uname = platform.uname()
    info = {
        "OS": f"{uname.system} {uname.release} ({uname.version})",
        "Machine": f"{uname.machine}",
        "Processor": platform.processor() or "",
        "Python": platform.python_version(),
    }
    if psutil:
        try:
            total = psutil.virtual_memory().total
            info["RAM"] = f"{total/1024/1024/1024:.2f} GB"
        except Exception:
            pass
        try:
            cores = psutil.cpu_count(logical=False)
            threads = psutil.cpu_count(logical=True)
            info["CPU Cores/Threads"] = f"{cores}/{threads}"
        except Exception:
            pass
    return info


def build_report() -> Dict[str, object]:
    data: Dict[str, object] = {}
    data["System"] = get_system_summary()
    data["GPUs"] = [asdict(g) for g in get_gpu_info()]
    cats = get_languages_and_tools()
    for k, v in cats.items():
        data[k] = [asdict(t) for t in v]
    return data
