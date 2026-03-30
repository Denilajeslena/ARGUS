import json
import threading
from pathlib import Path

current_alerts = []
ALERTS_FILE = Path(__file__).resolve().with_name("alerts.json")
_alerts_lock = threading.Lock()


def set_alerts(alerts):
    global current_alerts
    with _alerts_lock:
        next_alerts = list(alerts)
        if next_alerts == current_alerts:
            return
        current_alerts = next_alerts
        payload = {"alerts": current_alerts}
        try:
            ALERTS_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass


def get_alerts():
    with _alerts_lock:
        in_memory = list(current_alerts)

    if ALERTS_FILE.exists():
        try:
            payload = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
            return payload.get("alerts", [])
        except (json.JSONDecodeError, OSError):
            return in_memory
    return in_memory