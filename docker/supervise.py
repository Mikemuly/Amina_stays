#!/usr/bin/env python3
"""Entrypoint of the all-in-one Amina Stays image (the Dockerfile at the repo root), made for the
Africa's Talking Marketplace: one container, one port.

The Next.js server listens on 0.0.0.0:$PORT (default 8080) and proxies /api, /at (Africa's Talking
callbacks), /admin, /static, /media and /health to gunicorn on 127.0.0.1:$BACKEND_PORT (default 8000,
fixed when the image is built); the scheduler runs alongside.

Start-up:
  1. Settings. DATABASE_URL is composed from DB_*, POSTGRES_* or PG* variables when it isn't set.
     PUBLIC_URL and FRONTEND_URL default to each other; ALLOWED_HOSTS to the loopback names, the
     PUBLIC_URL host, .africastalking.marketplace.dev and the container's own addresses; BACKEND_URL
     to gunicorn's address.
  2. Secrets, when DEBUG is off. ID_ENCRYPTION_KEY (a Fernet key) is required: without it guest ID
     numbers are encrypted with a key derived from SECRET_KEY and become unreadable once SECRET_KEY
     changes. SECRET_KEY is required too, except with DEMO=1, which gets a random one per start
     (logins and login codes then reset whenever the instance restarts).
  3. Wait for PostgreSQL (DB_WAIT_SECONDS, default 60). Then, under a Postgres advisory lock so that
     instances starting together take turns: migrate; load the demo data when the database has no
     homes yet and DEMO=1 or SEED_DEMO=1 (never with SEED_DEMO=0); give AMINA_PHONE the owner role,
     so the host can log in to /host.
  4. Start gunicorn, then the Next.js server once the API answers, then the scheduler, and print the
     go-live warnings (`check --deploy --tag security`) in the background. SIGTERM/SIGINT are forwarded
     to every process and whatever still runs after STOP_TIMEOUT seconds (default 5) is killed. If a
     process dies, the others are stopped and the container exits non-zero, so the platform restarts it.

`supervise.py COMMAND...` runs a one-off command in backend/ with the same settings instead, e.g.
`docker run --rm -e DATABASE_URL=... IMAGE python manage.py tick`.

AMINA_BACKEND_DIR and AMINA_FRONTEND_DIR (the Next.js standalone folder, with server.js) override the
image layout, to run this script outside the image. Python standard library only.
"""

import base64
import binascii
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit

APP_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(os.environ.get("AMINA_BACKEND_DIR") or APP_DIR / "backend")
FRONTEND_DIR = Path(os.environ.get("AMINA_FRONTEND_DIR") or APP_DIR / "frontend")
PYTHON = sys.executable

DEV_SECRET = "dev-only-insecure-secret-key-change-me-before-deploying"  # settings.py's DEBUG-only fallback
DEMO_PHONE = "+254700000001"  # the AMINA_PHONE default in settings.py and the demo data
MARKETPLACE_HOSTS = ".africastalking.marketplace.dev"
BOOTSTRAP_LOCK = 4_206_2027  # Postgres advisory lock id (the scheduler's passes use 4_206_2026)
POSTGRES_SCHEMES = ("postgres", "postgresql", "pgsql", "postgis")
NEW_FERNET_KEY = 'python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
NEW_SECRET_KEY = 'python3 -c "import secrets; print(secrets.token_urlsafe(50))"'

# host, port, database, user, password, sslmode (the first name set wins), one set per naming convention
DB_VARIABLE_SETS = (
    (
        ("DB_HOST",),
        ("DB_PORT",),
        ("DB_NAME", "DB_DATABASE"),
        ("DB_USER", "DB_USERNAME"),
        ("DB_PASSWORD", "DB_PASS"),
        ("DB_SSLMODE",),
    ),
    (
        ("POSTGRES_HOST",),
        ("POSTGRES_PORT",),
        ("POSTGRES_DB", "POSTGRES_DATABASE"),
        ("POSTGRES_USER", "POSTGRES_USERNAME"),
        ("POSTGRES_PASSWORD",),
        ("POSTGRES_SSLMODE",),
    ),
    (("PGHOST",), ("PGPORT",), ("PGDATABASE",), ("PGUSER",), ("PGPASSWORD",), ("PGSSLMODE",)),
)

# Both run with the backend's Python in backend/: Django and psycopg are only installed there.
DB_PROBE = """
import os
import dj_database_url, psycopg
c = dj_database_url.parse(os.environ["DATABASE_URL"])
params = {"host": c.get("HOST"), "port": c.get("PORT"), "dbname": c.get("NAME"), "user": c.get("USER"),
          "password": c.get("PASSWORD")}
params = {k: v for k, v in params.items() if v not in (None, "")}
params.update(c.get("OPTIONS") or {})
psycopg.connect(connect_timeout=5, **params).close()
"""

BOOTSTRAP = """
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection

lock, seed, demo_phone = int(sys.argv[1]), sys.argv[2] == "1", sys.argv[3]


def ensure_owner():
    raw = os.environ.get("AMINA_PHONE", "").strip()
    if not raw:
        print("AMINA_PHONE is not set: no host login was set up (the demo data has its own)")
        return
    from apps.accounts.models import User
    from apps.core.utils import normalize_phone

    phone = normalize_phone(raw)
    if not phone:
        print(f"AMINA_PHONE {raw!r} isn't a phone number: no host login was set up", file=sys.stderr)
    elif phone == demo_phone and not settings.DEMO:
        print(f"AMINA_PHONE is the demo number {phone}: set the host's own number to log in to /host", file=sys.stderr)
    else:
        user = User.objects.filter(phone=phone).first()
        if user is None:
            User.objects.create_user(phone, role="owner", is_staff=True)
            print(f"Host login: {phone} (new owner account)")
        elif user.role != "owner" or not user.is_staff:
            user.role, user.is_staff = "owner", True
            user.save(update_fields=["role", "is_staff"])
            print(f"Host login: {phone} (now the owner)")
        else:
            print(f"Host login: {phone}")


with connection.cursor() as cursor:
    cursor.execute("SELECT pg_advisory_lock(%s)", [lock])  # waits while another instance runs this
try:
    print("manage.py migrate --noinput", flush=True)
    call_command("migrate", interactive=False)
    from apps.properties.models import Unit

    if not seed:
        print("Demo data: not loading it (DEMO=1 or SEED_DEMO=1 would; SEED_DEMO=0 never does)")
    elif Unit.objects.exists():
        print("Demo data: the database already has homes, not seeding")
    else:
        print("manage.py seed_demo", flush=True)
        call_command("seed_demo")
    ensure_owner()
finally:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [lock])
"""

_print_lock = threading.Lock()
_stop = {"signum": None}
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via HTTP_PROXY


def log(message):
    with _print_lock:
        sys.stderr.write(f"[supervise] {message}\n")
        sys.stderr.flush()


def env(key, default=None):
    """Like settings.env(): unset, empty and blank values all mean "not set"; values are stripped."""
    value = os.environ.get(key)
    return default if value is None or not value.strip() else value.strip()


def env_bool(key, default=False):
    value = env(key)
    return default if value is None else value.lower() in ("1", "true", "yes", "on")


def env_int(key, default, problems):
    try:
        return int(env(key, str(default)))
    except ValueError:
        problems.append(f"{key} must be a whole number, not {env(key)!r}.")
        return default


def first(names, strip=True):
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip() if strip else value
    return None


# ---------- settings ----------


def database_url():
    """DATABASE_URL, or one composed from the first DB_*, POSTGRES_* or PG* set that names a host."""
    url = env("DATABASE_URL")
    if url:
        return url, "DATABASE_URL"
    for hosts, ports, names, users, passwords, sslmodes in DB_VARIABLE_SETS:
        host = first(hosts)
        if not host:
            continue
        user, password = first(users), first(passwords, strip=False)
        name = first(names) or user or ""
        if host.startswith("/"):  # a Unix socket directory
            netloc = quote(host, safe="")
        elif ":" in host and not host.startswith("["):  # IPv6
            netloc = f"[{host}]"
        else:
            netloc = host
        auth = ""
        if user:
            auth = quote(user, safe="") + (":" + quote(password, safe="") if password else "") + "@"
        url = f"postgres://{auth}{netloc}:{first(ports) or '5432'}/{quote(name, safe='')}"
        sslmode = first(sslmodes)
        if sslmode:
            url += "?sslmode=" + quote(sslmode, safe="")
        return url, f"{hosts[0][:-4]}* variables"
    return None, None


def masked(url):
    parts = urlsplit(url)
    if parts.password is None:
        return url
    return f"{parts.scheme}://{parts.username or ''}:***@{parts.netloc.rpartition('@')[2]}{parts.path}"


def with_scheme(url):
    url = url.strip().rstrip("/")
    return url if "://" in url else "https://" + url


def own_addresses():
    """The container's name and IPs: platform probes may send them as the Host header."""
    found = []
    try:
        name = socket.gethostname()
        found += [name, *socket.gethostbyname_ex(name)[2]]
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # sends nothing: only picks the interface of the default route
            found.append(s.getsockname()[0])
    except OSError:
        pass
    return found


def is_fernet_key(key):
    """What cryptography's Fernet(key) accepts: 32 bytes, url-safe base64."""
    try:
        return len(base64.urlsafe_b64decode(key.encode())) == 32
    except (binascii.Error, ValueError):
        return False


def configure(port, backend_port):
    """Fill in the environment every process inherits. Returns the problems that prevent starting."""
    problems = []

    url, source = database_url()
    if not url:
        problems.append(
            "No database is configured: set DATABASE_URL, or DB_HOST, DB_PORT, DB_NAME, DB_USER and DB_PASSWORD "
            "(the POSTGRES_* and PG* equivalents work too)."
        )
    elif urlsplit(url).scheme.lower() not in POSTGRES_SCHEMES:
        problems.append(f"Amina Stays needs PostgreSQL, but the database is {masked(url)}.")
    else:
        os.environ["DATABASE_URL"] = url
        log(f"Database: {masked(url)} (from {source})")

    public_env, frontend_env = env("PUBLIC_URL"), env("FRONTEND_URL")
    if public_env or frontend_env:
        public = with_scheme(public_env or frontend_env)
    else:
        public = f"http://localhost:{port}"
        log(
            "WARNING: PUBLIC_URL is not set. Set it to this instance's https address: until then logins and "
            f"bookings from the browser fail Django's CSRF check, and links sent by SMS point to {public}."
        )
    os.environ["PUBLIC_URL"] = with_scheme(public_env) if public_env else public
    os.environ["FRONTEND_URL"] = with_scheme(frontend_env) if frontend_env else public

    hosts = [h.strip() for h in (env("ALLOWED_HOSTS") or "").split(",") if h.strip()]
    if not hosts:
        for value in (os.environ["PUBLIC_URL"], os.environ["FRONTEND_URL"]):
            host = urlsplit(value).hostname
            if host:
                hosts.append(f"[{host}]" if ":" in host else host)
        hosts += [MARKETPLACE_HOSTS, *own_addresses()]
    # the health check reaches Django through 127.0.0.1, so loopback stays allowed even when ALLOWED_HOSTS is set
    os.environ["ALLOWED_HOSTS"] = ",".join(dict.fromkeys(["localhost", "127.0.0.1", "[::1]", *hosts]))

    if not env("BACKEND_URL"):
        os.environ["BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"

    # the marketplace's bulk environment editor drops everything from a "#" on, as a comment
    ussd = env("AT_USSD_CODE")
    if ussd and ussd.startswith("*") and not ussd.endswith("#"):
        os.environ["AT_USSD_CODE"] = ussd + "#"
        log(f"AT_USSD_CODE {ussd} has no closing '#': using {ussd}#")

    if env_bool("DEBUG"):
        log("WARNING: DEBUG is on: error pages show code and settings. Never on a public instance.")
    else:
        key = env("ID_ENCRYPTION_KEY")
        if not key:
            problems.append(
                "ID_ENCRYPTION_KEY is not set. It encrypts guests' ID numbers; without it they're encrypted with "
                "a key derived from SECRET_KEY and become unreadable whenever SECRET_KEY changes. Create one "
                f"with: {NEW_FERNET_KEY}"
            )
        elif not is_fernet_key(key):
            problems.append(
                "ID_ENCRYPTION_KEY isn't a Fernet key (32 url-safe base64-encoded bytes: 44 characters ending "
                f"in '='). Create one with: {NEW_FERNET_KEY}"
            )
        secret = env("SECRET_KEY")
        if not secret or secret == DEV_SECRET:
            if env_bool("DEMO"):
                os.environ["SECRET_KEY"] = secrets.token_urlsafe(50)
                log(
                    "WARNING: SECRET_KEY is not set, so this DEMO=1 run uses a random one: logins and login "
                    "codes reset whenever the instance restarts (scaling to zero restarts it). Set SECRET_KEY "
                    "to keep them."
                )
            else:
                problems.append(
                    f"SECRET_KEY is not set (required when DEBUG is off). Create one with: {NEW_SECRET_KEY}"
                )
    if env_bool("DEMO"):
        log("DEMO=1: the Demo Lab is open and login codes show on screen, so anyone can log in as the host.")

    if port == backend_port:
        problems.append(f"PORT and BACKEND_PORT are both {port}: the API listens on BACKEND_PORT inside the container.")
    return problems


# ---------- processes ----------


class Child:
    """A process in its own session, its output passed through to ours with a [name] prefix."""

    def __init__(self, name, args, cwd, child_env):
        self.name, self.returncode = name, None
        self.proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # a terminal's Ctrl-C reaches only this script, which forwards it
        )
        self.pid = self.proc.pid
        prefix = f"[{name}] ".encode()
        self.pumps = [
            threading.Thread(target=self._pump, args=(self.proc.stdout, sys.stdout, prefix), daemon=True),
            threading.Thread(target=self._pump, args=(self.proc.stderr, sys.stderr, prefix), daemon=True),
        ]
        for thread in self.pumps:
            thread.start()

    @staticmethod
    def _pump(source, target, prefix):
        with source:
            for line in iter(source.readline, b""):
                if not line.endswith(b"\n"):
                    line += b"\n"
                with _print_lock:
                    try:
                        target.buffer.write(prefix + line)
                        target.flush()
                    except (OSError, ValueError):
                        pass

    @property
    def alive(self):
        return self.returncode is None

    def group_alive(self):
        """The process or anything left in its process group (e.g. gunicorn workers whose master died)."""
        if self.alive:
            return True
        try:
            os.killpg(self.pid, 0)
            return True
        except (ProcessLookupError, PermissionError):  # EPERM: not our processes any more
            return False

    def signal_group(self, signum):
        # Linux doesn't reuse a process group id while the group has members, so this never hits a stranger
        try:
            os.killpg(self.pid, signum)
        except (ProcessLookupError, PermissionError):
            pass

    def finish_output(self):
        for thread in self.pumps:
            thread.join(timeout=1)


def reap(children):
    """Collect every exited child: ours, and orphans adopted while running as PID 1 in a container."""
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return
        for child in children:
            if child.pid == pid:
                child.returncode = child.proc.returncode = os.waitstatus_to_exitcode(status)


def stop_requested():
    return _stop["signum"] is not None


def on_signal(signum, frame):
    if _stop["signum"] is None:
        _stop["signum"] = signum


def shutdown(children, timeout):
    running = [c for c in children if c.group_alive()]
    signum = signal.SIGINT if _stop["signum"] == signal.SIGINT else signal.SIGTERM
    if running:
        log(f"Stopping {', '.join(c.name for c in running)} ({signal.Signals(signum).name})")
    for child in running:
        child.signal_group(signum)
    deadline = time.monotonic() + timeout
    while any(c.group_alive() for c in children) and time.monotonic() < deadline:
        time.sleep(0.05)
        reap(children)
    for child in children:
        if child.group_alive():
            # e.g. run_scheduler, which only notices SIGTERM once its sleep between passes ends
            log(f"{child.name} still running after {timeout}s: killing it")
            child.signal_group(signal.SIGKILL)
    deadline = time.monotonic() + 5
    while any(c.group_alive() for c in children) and time.monotonic() < deadline:
        time.sleep(0.05)
        reap(children)
    for child in children:
        child.finish_output()
        if child in running:
            log(f"{child.name} stopped ({child.returncode})")


def finish(children, extras, timeout):
    """Stop everything. 0 after a requested stop; non-zero when a process died on its own or never came up."""
    reap(children + extras)
    crashed = [c for c in children if not c.alive]
    for child in crashed:
        log(f"{child.name} exited ({child.returncode}): stopping the rest")
    # one-off processes that finished long ago have nothing left to stop (and their ids may be reused)
    shutdown(children + [c for c in extras if c.alive], timeout)
    if stop_requested() and not crashed:
        log("Stopped")
        return 0
    return next((c.returncode for c in crashed if c.returncode and c.returncode > 0), 1)


def wait_until(children, ready, timeout, what):
    """Poll ready(); False as soon as a child dies or a stop is requested, or when time runs out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        reap(children)
        if stop_requested() or any(not c.alive for c in children):
            return False
        if ready():
            return True
        time.sleep(0.2)
    log(f"Timed out after {timeout}s waiting for {what}")
    return False


def http_ok(url):
    try:
        with _direct.open(url, timeout=2) as response:
            return response.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except OSError:
        return False


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def port_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_for_database(child_env, timeout):
    log(f"Waiting for the database (up to {timeout}s)")
    deadline, said_at, reason = time.monotonic() + timeout, 0.0, ""
    while not stop_requested():
        try:
            probe = subprocess.run(
                [PYTHON, "-c", DB_PROBE], cwd=BACKEND_DIR, env=child_env, capture_output=True, text=True, timeout=20
            )
            if probe.returncode == 0:
                log("Database is up")
                return True
            lines = [line.strip() for line in probe.stderr.splitlines() if line.strip()]
            reason = ([line for line in lines if "Error: " in line] or lines or ["no output"])[-1]
        except subprocess.TimeoutExpired:
            reason = "no answer in 20s"
        if time.monotonic() >= deadline:
            log(f"ERROR: the database isn't reachable: {reason}")
            return False
        if time.monotonic() - said_at >= 10:
            log(f"Database not ready yet: {reason}")
            said_at = time.monotonic()
        time.sleep(2)
    return False


def gunicorn_args(backend_port, workers, graceful_timeout):
    args = [PYTHON, "-m", "gunicorn", "config.wsgi", "--bind", f"127.0.0.1:{backend_port}"]
    args += ["--workers", str(workers), "--threads", "4", "--graceful-timeout", str(graceful_timeout)]
    # --keep-alive 0: one connection per proxied request, so Next.js never reuses one gunicorn is closing
    args += ["--keep-alive", "0", "--access-logfile", "-"]
    if os.access("/dev/shm", os.W_OK):
        args += ["--worker-tmp-dir", "/dev/shm"]  # worker heartbeats in memory rather than on the container disk
    if (Path(PYTHON).parent / "gunicornc").exists():
        args.append("--no-control-socket")  # gunicorn 25.1+ would open a control socket in $HOME
    return args


def main():
    problems = []
    port = env_int("PORT", 8080, problems)
    backend_port = env_int("BACKEND_PORT", 8000, problems)
    workers = env_int("WEB_CONCURRENCY", 2, problems)
    stop_timeout = env_int("STOP_TIMEOUT", 5, problems)
    db_wait = env_int("DB_WAIT_SECONDS", 60, problems)
    if workers < 1:
        problems.append("WEB_CONCURRENCY must be at least 1.")
    problems += configure(port, backend_port)

    if len(sys.argv) > 1:  # a one-off command with the same settings
        for problem in problems:
            log(f"ERROR: {problem}")
        if problems:
            return 2
        os.chdir(BACKEND_DIR)
        os.execvp(sys.argv[1], sys.argv[1:])

    node = shutil.which("node")
    if not node:
        problems.append("node isn't on PATH.")
    if not (FRONTEND_DIR / "server.js").is_file():
        problems.append(f"{FRONTEND_DIR}/server.js is missing (AMINA_FRONTEND_DIR: the Next.js standalone build).")
    if not (BACKEND_DIR / "manage.py").is_file():
        problems.append(f"{BACKEND_DIR}/manage.py is missing (AMINA_BACKEND_DIR: the Django project).")
    for name, host, number in (("BACKEND_PORT", "127.0.0.1", backend_port), ("PORT", "0.0.0.0", port)):
        if not port_free(host, number):
            problems.append(f"{name} {number} is already in use.")
    for problem in problems:
        log(f"ERROR: {problem}")
    if problems:
        return 2

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(signum, on_signal)

    base_env = dict(os.environ, PYTHONUNBUFFERED="1")
    seed = env_bool("SEED_DEMO") if env("SEED_DEMO") is not None else env_bool("DEMO")
    log(
        f"Amina Stays: web on 0.0.0.0:{port}, API on 127.0.0.1:{backend_port} ({workers} workers), "
        f"PUBLIC_URL {os.environ['PUBLIC_URL']}"
    )
    if not wait_for_database(base_env, db_wait):
        return 0 if stop_requested() else 1

    started = []  # everything spawned, so nothing outlives this script whatever happens below
    try:
        setup_args = [PYTHON, "-c", BOOTSTRAP, str(BOOTSTRAP_LOCK), "1" if seed else "0", DEMO_PHONE]
        setup = Child("setup", setup_args, BACKEND_DIR, base_env)
        started.append(setup)
        while setup.alive and not stop_requested():
            time.sleep(0.1)
            reap([setup])
        if setup.alive:
            shutdown([setup], stop_timeout)
            return 0
        setup.finish_output()
        if setup.returncode != 0:
            log(f"ERROR: setup failed ({setup.returncode})")
            return 1

        children = [Child("api", gunicorn_args(backend_port, workers, max(1, stop_timeout - 1)), BACKEND_DIR, base_env)]
        started += children
        if not wait_until(children, lambda: http_ok(f"http://127.0.0.1:{backend_port}/health"), 120, "the API"):
            return finish(children, [], stop_timeout)

        web_env = dict(base_env, HOSTNAME="0.0.0.0", PORT=str(port), NODE_ENV="production", NEXT_TELEMETRY_DISABLED="1")
        # longer than any proxy's idle timeout, so a proxy in front never reuses a connection Node is closing
        web_env.setdefault("KEEP_ALIVE_TIMEOUT", "650000")
        children.append(Child("web", [node, "server.js"], FRONTEND_DIR, web_env))
        started.append(children[-1])
        if not wait_until(children, lambda: port_open(port), 60, "the web server"):
            return finish(children, [], stop_timeout)

        children.append(Child("scheduler", [PYTHON, "manage.py", "run_scheduler"], BACKEND_DIR, base_env))
        started.append(children[-1])
        log(f"Ready on port {port}")
        # the go-live warnings (amina.W0xx) and Django's security ones, without drf-spectacular's schema noise
        checks = Child("check", [PYTHON, "manage.py", "check", "--deploy", "--tag", "security"], BACKEND_DIR, base_env)
        started.append(checks)

        while not stop_requested() and all(c.alive for c in children):
            time.sleep(0.25)
            reap(started)
        return finish(children, [checks], stop_timeout)
    finally:
        for child in started:
            if child.alive:  # only after an unexpected error: everything is stopped and reaped otherwise
                child.signal_group(signal.SIGKILL)


if __name__ == "__main__":
    sys.exit(main())
