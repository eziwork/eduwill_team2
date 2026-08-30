#!/usr/bin/env python3
"""Persist a MOLIT/data.go.kr key from standard input on Windows or macOS."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


KEYCHAIN_SERVICE = "eziwork-final.molit-api-key"


def output(status: str, storage: str | None, message: str, exit_code: int) -> int:
    print(
        json.dumps(
            {
                "status": status,
                "storage": storage,
                "message": message,
                "service_key_logged": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return exit_code


def save_windows(key: str) -> int:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    script = Path(__file__).with_name("save_molit_api_key.ps1")
    if not shell or not script.is_file():
        return output(
            "RUNTIME_MISSING",
            None,
            "Windows 인증키 저장에 필요한 PowerShell을 찾지 못했습니다.",
            3,
        )
    args = [shell, "-NoProfile", "-NonInteractive"]
    if Path(shell).name.lower().startswith("powershell"):
        args.extend(["-ExecutionPolicy", "Bypass"])
    args.extend(["-File", str(script)])
    completed = subprocess.run(args, input=key, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        return output(
            "SAVE_FAILED",
            None,
            "Windows 사용자 전용 암호화 저장에 실패했습니다.",
            4,
        )
    return output(
        "SAVED",
        "WINDOWS_DPAPI_CURRENT_USER",
        "인증키를 현재 Windows 사용자 전용 암호화 저장소에 저장했습니다.",
        0,
    )


def save_macos(key: str) -> int:
    security = Path("/usr/bin/security")
    if not security.is_file():
        return output("RUNTIME_MISSING", None, "macOS security 명령을 찾지 못했습니다.", 3)
    completed = subprocess.run(
        [
            str(security),
            "add-generic-password",
            "-U",
            "-a",
            getpass.getuser(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            key,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        return output(
            "SAVE_FAILED",
            "MACOS_KEYCHAIN_CURRENT_USER",
            "macOS 키체인 저장에 실패했습니다. 키체인 잠금과 접근 권한을 확인하세요.",
            4,
        )
    return output(
        "SAVED",
        "MACOS_KEYCHAIN_CURRENT_USER",
        "인증키를 현재 macOS 사용자의 기본 키체인에 저장했습니다.",
        0,
    )


def main() -> int:
    key = sys.stdin.read().strip()
    if not key:
        return output("KEY_REQUIRED", None, "표준입력으로 인증키를 전달해야 합니다.", 2)
    try:
        if os.name == "nt":
            return save_windows(key)
        if sys.platform == "darwin":
            return save_macos(key)
        return output(
            "UNSUPPORTED_PERSISTENCE",
            None,
            "이 운영체제에서는 DATA_GO_KR_SERVICE_KEY 환경변수만 지원합니다.",
            5,
        )
    finally:
        key = ""


if __name__ == "__main__":
    raise SystemExit(main())
