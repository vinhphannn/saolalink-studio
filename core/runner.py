"""One cancellable process group at a time; UI receives events through a queue."""
import os
import queue
import shlex
import signal
import subprocess
import threading
from datetime import datetime
from pathlib import Path

class OperationRunner:
    def __init__(self, log_dir: Path, env=None):
        self.log_dir = log_dir
        self.env = env
        self.events = queue.Queue()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._running = False
        self._process = None
        self.last_success = None

    @property
    def running(self):
        with self._lock:
            return self._running

    def start(self, name, commands, cwd, on_success=None):
        commands = [list(c) for c in commands]
        with self._lock:
            if self._running:
                self.events.put(('log', '[BUSY] Wait for the current operation.\n'))
                return False
            self._running = True
            self._cancel.clear()
            self.last_success = None
        threading.Thread(target=self._run, args=(name, commands, cwd, on_success), daemon=True).start()
        return True

    def _run(self, name, commands, cwd, on_success):
        success = False
        log = None
        def emit(message):
            if log is not None:
                log.write(message)
                log.flush()
            self.events.put(('log', message))
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / f'{datetime.now():%Y%m%d-%H%M%S-%f}-{name}.log'
            log = log_path.open('w', encoding='utf-8')
            self.events.put(('started', str(log_path)))
            for command in commands:
                with self._lock:
                    if self._cancel.is_set():
                        raise RuntimeError('Operation cancelled')
                    emit('> ' + (subprocess.list2cmdline(command) if os.name == 'nt' else shlex.join(command)) + '\n')
                    self._process = subprocess.Popen(
                        command, cwd=cwd, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', env=self.env,
                        bufsize=1, start_new_session=(os.name == 'posix'),
                        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0)
                    process = self._process
                for line in process.stdout:
                    emit(line)
                process.stdout.close()
                code = process.wait()
                with self._lock:
                    self._process = None
                if self._cancel.is_set():
                    raise RuntimeError('Operation cancelled')
                if code:
                    raise RuntimeError(f'Command exited with status {code}')
            if self._cancel.is_set():
                raise RuntimeError('Operation cancelled')
            if on_success:
                message = on_success()
                if message:
                    emit(message + '\n')
            emit('[SUCCESS] Operation complete.\n')
            success = True
        except Exception as error:
            emit(f'[ERROR] {error}\n')
        finally:
            if log is not None:
                log.close()
            with self._lock:
                self._process = None
                self.last_success = success
                self._running = False
            self.events.put(('finished', success))

    def stop(self):
        with self._lock:
            self._cancel.set()
            process = self._process
            if process and process.poll() is None:
                try:
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        # Stop CMake/Ninja/compiler descendants too, without blocking Tk.
                        threading.Thread(target=self._windows_stop, args=(process,), daemon=True).start()
                    threading.Thread(target=self._force_stop, args=(process,), daemon=True).start()
                except ProcessLookupError:
                    pass

    @staticmethod
    def _windows_stop(process):
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            if process.poll() is None:
                process.kill()

    @staticmethod
    def _force_stop(process):
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
