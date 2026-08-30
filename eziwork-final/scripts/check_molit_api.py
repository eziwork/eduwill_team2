#!/usr/bin/env python3
"""Check MOLIT/data.go.kr credentials and API connectivity without exposing the key."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_ENDPOINT = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/"
    "getRTMSDataSvcAptTradeDev"
)
KEYCHAIN_SERVICE = "eziwork-final.molit-api-key"
SUCCESS_CODES = {"", "0", "00", "000", "NORMAL_CODE", "NORMAL SERVICE."}


def emit(payload: dict, exit_code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def read_windows_key() -> tuple[str | None, str | None]:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    key_store = Path(__file__).with_name("molit_api_key_store.ps1")
    if not shell or not key_store.is_file():
        return None, None
    escaped = str(key_store).replace("'", "''")
    command = (
        f". '{escaped}'; $k = Get-MolitApiKey; "
        "if (-not [string]::IsNullOrWhiteSpace($k)) { [Console]::Out.Write($k) }"
    )
    args = [shell, "-NoProfile", "-NonInteractive"]
    if Path(shell).name.lower().startswith("powershell"):
        args.extend(["-ExecutionPolicy", "Bypass"])
    args.extend(["-Command", command])
    completed = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    key = completed.stdout.strip()
    return (key, "WINDOWS_DPAPI_CURRENT_USER") if key else (None, None)


def read_macos_key() -> tuple[str | None, str | None]:
    security = Path("/usr/bin/security")
    if not security.is_file():
        return None, None
    completed = subprocess.run(
        [
            str(security),
            "find-generic-password",
            "-a",
            getpass.getuser(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    key = completed.stdout.strip()
    return (key, "MACOS_KEYCHAIN_CURRENT_USER") if completed.returncode == 0 and key else (None, None)


def read_service_key() -> tuple[str | None, str | None]:
    environment_key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if environment_key:
        return environment_key, "ENV_DATA_GO_KR_SERVICE_KEY"
    if os.name == "nt":
        return read_windows_key()
    if sys.platform == "darwin":
        return read_macos_key()
    return None, None


def parse_response(body: bytes) -> tuple[str, str, int | None]:
    text = body.decode("utf-8", errors="replace").lstrip()
    if text.startswith("{"):
        data = json.loads(text)
        response = data.get("response", data)
        header = response.get("header", {})
        result_code = str(header.get("resultCode", "")).strip()
        result_message = str(header.get("resultMsg", "")).strip()
        body_node = response.get("body", {})
        total_count = body_node.get("totalCount")
        return result_code, result_message, int(total_count) if total_count is not None else None

    root = ET.fromstring(text)
    result_code = (root.findtext(".//resultCode") or "").strip()
    result_message = (root.findtext(".//resultMsg") or "").strip()
    total_text = (root.findtext(".//totalCount") or "").strip()
    return result_code, result_message, int(total_text) if total_text.isdigit() else None


def is_success(code: str, message: str) -> bool:
    return code.upper() in SUCCESS_CODES or message.upper() in SUCCESS_CODES


def key_encodings(key: str, force_encoded: bool) -> list[tuple[str, str]]:
    if force_encoded:
        return [("encoded", key)]
    encoded = urllib.parse.quote(key, safe="")
    if re.search(r"%[0-9A-Fa-f]{2}", key):
        return [("encoded", key), ("decoded", encoded)]
    return [("decoded", encoded)]


def probe(
    endpoint: str,
    key: str,
    lawd_cd: str,
    deal_ym: str,
    timeout: float,
    force_encoded: bool,
) -> dict:
    last_api_error: dict | None = None
    common = urllib.parse.urlencode(
        {"LAWD_CD": lawd_cd, "DEAL_YMD": deal_ym, "pageNo": 1, "numOfRows": 1}
    )
    for encoding_name, key_value in key_encodings(key, force_encoded):
        url = f"{endpoint}?serviceKey={key_value}&{common}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "eziwork-final-molit-preflight/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            return {
                "status": "CONNECTION_FAILED",
                "http_status": exc.code,
                "message": "국토교통부 API가 HTTP 오류를 반환했습니다.",
            }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "status": "CONNECTION_FAILED",
                "message": f"국토교통부 API에 연결하지 못했습니다: {type(exc).__name__}",
            }

        try:
            result_code, result_message, total_count = parse_response(body)
        except (ET.ParseError, json.JSONDecodeError, ValueError, TypeError):
            return {
                "status": "INVALID_RESPONSE",
                "message": "국토교통부 API 응답 형식을 확인할 수 없습니다.",
            }

        if is_success(result_code, result_message):
            return {
                "status": "CONNECTED",
                "api_connected": True,
                "result_code": result_code,
                "probe_total_count": total_count,
                "probe_data_available": bool(total_count and total_count > 0),
                "key_encoding_used": encoding_name,
                "message": "국토교통부 API 인증과 연결이 정상입니다.",
            }
        last_api_error = {
            "status": "AUTH_OR_API_FAILED",
            "api_connected": True,
            "result_code": result_code,
            "message": "API가 인증 또는 요청 오류를 반환했습니다.",
        }

    return last_api_error or {
        "status": "AUTH_OR_API_FAILED",
        "api_connected": True,
        "message": "API 인증 상태를 확인할 수 없습니다.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--lawd-cd", default="11110")
    parser.add_argument("--deal-ym", default=dt.date.today().strftime("%Y%m"))
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--service-key-is-encoded", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()

    checked_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    base = {
        "checked_at": checked_at,
        "platform": platform.system(),
        "endpoint": args.endpoint,
        "probe_scope": {"lawd_cd": args.lawd_cd, "deal_ym": args.deal_ym},
        "service_key_logged": False,
    }

    if not re.fullmatch(r"\d{5}", args.lawd_cd):
        return emit(
            base
            | {
                "status": "INVALID_ARGUMENT",
                "message": "lawd_cd는 5자리 숫자여야 합니다.",
            },
            5,
        )
    if not re.fullmatch(r"\d{6}", args.deal_ym):
        return emit(
            base
            | {
                "status": "INVALID_ARGUMENT",
                "message": "deal_ym은 YYYYMM 형식이어야 합니다.",
            },
            5,
        )

    key, source = read_service_key()
    if not key:
        return emit(
            base
            | {
                "status": "KEY_MISSING",
                "credential_available": False,
                "message": "국토교통부 실거래 API 인증키를 찾지 못했습니다.",
                "next_action": (
                    "공공데이터포털에서 발급받은 인증키를 채팅으로 요청하고, "
                    "응답에 다시 표시하지 않은 채 표준입력으로 저장하세요."
                ),
            },
            2,
        )

    if args.no_network:
        return emit(
            base
            | {
                "status": "KEY_AVAILABLE",
                "credential_available": True,
                "credential_source": source,
                "message": "인증키는 확인했지만 네트워크 점검은 생략했습니다.",
            },
            0,
        )

    result = probe(
        args.endpoint,
        key,
        args.lawd_cd,
        args.deal_ym,
        args.timeout,
        args.service_key_is_encoded,
    )
    result["credential_available"] = True
    result["credential_source"] = source
    if result["status"] == "CONNECTED":
        result["next_action"] = (
            "대상 조건으로 수집을 진행하세요. 대상 조회가 0건이면 0건 응답을 보존하고 "
            "사용자에게 정규화 자료 또는 조회범위 변경 여부를 요청하세요."
        )
        return emit(base | result, 0)
    result["next_action"] = (
        "인증키를 다시 요청하거나 사용자가 제공한 공식 실거래 CSV·JSON으로 진행하세요."
    )
    return emit(base | result, 3 if result["status"] == "AUTH_OR_API_FAILED" else 4)


if __name__ == "__main__":
    raise SystemExit(main())
