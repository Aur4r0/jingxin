"""单机、同工作目录排他锁；由操作系统在退出时释放。"""
import os


def acquire():
    handle = open('.runtime.lock', 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if handle.seek(0, 2) == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        raise RuntimeError('已有运行实例；禁止多 worker 或重复启动') from None
