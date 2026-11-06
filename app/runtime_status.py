"""进程级运行状态；重启后为未知，不伪造历史成功。"""
from datetime import datetime, timezone
from threading import Lock

_lock = Lock()
_status = {}


def record(name, ok, message=''):
    with _lock:
        previous = _status.get(name, {})
        _status[name] = {'ok': ok, 'checked_at': datetime.now(timezone.utc).isoformat(),
                         'last_success': datetime.now(timezone.utc).isoformat() if ok else previous.get('last_success'),
                         'message': message}


def snapshot():
    with _lock:
        return {k: dict(v) for k,v in _status.items()}
