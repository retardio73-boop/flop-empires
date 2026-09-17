from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .readiness import readiness_report
from .season0_runner import ACTIVATION_PATH, DB_PATH, MANIFEST_PATH, RUNTIME_DIR, STATUS_PATH, ROOT
from .store import Store

WATCHDOG_STATUS = RUNTIME_DIR / "watchdog-status.json"
WORLD_PATH = ROOT / "season" / "world-season-0-v1.json"


def _priority() -> None:
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


def main() -> int:
    _priority(); RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        store = Store(DB_PATH, readonly=True)
        try: report = readiness_report(store, MANIFEST_PATH, ACTIVATION_PATH, WORLD_PATH, STATUS_PATH)
        finally: store.close()
        payload = {"watchdog": "OK" if report["ok"] else "ALERT", "checked_at": int(time.time()), **report}
    except Exception as exc:
        payload = {"watchdog": "ERROR", "checked_at": int(time.time()), "error_type": type(exc).__name__, "safe_error": str(exc)[:160]}
    temporary = WATCHDOG_STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')), encoding='utf-8')
    os.replace(temporary, WATCHDOG_STATUS)
    return 0 if payload.get('watchdog') == 'OK' else 2


if __name__ == '__main__':
    raise SystemExit(main())
