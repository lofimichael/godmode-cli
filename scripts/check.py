#!/usr/bin/env python3
"""Run Godmode's local checks once, with bounded workers and explicit coverage."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHELL_FILES = ("install.sh", "scripts/build-native.sh",
               "scripts/build-license-test.sh", "tests/install.sh", "tests/install-update.sh")


@dataclass
class Job:
    name: str
    commands: list
    timeout: float = 600
    environment: dict = field(default_factory=dict)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".tmp")
    staging.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(staging), str(path))


def process_snapshot():
    """Read identities, not command lines (which could contain credentials)."""
    result = subprocess.run(["ps", "-axo", "pid=,ppid=,pgid=,lstart="],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, timeout=2, check=True)
    processes = {}
    for line in result.stdout.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4:
            processes[int(fields[0])] = (int(fields[1]), int(fields[2]), fields[3])
    return processes


def track_descendants(parent, tracked):
    try:
        snapshot = process_snapshot()
    except (OSError, ValueError, subprocess.SubprocessError):
        return
    owned = {pid for pid, identity in tracked.items() if pid in snapshot and snapshot[pid][2] == identity}
    owned.add(parent)
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _pgid, identity) in snapshot.items():
            if ppid in owned and pid not in owned:
                owned.add(pid)
                tracked[pid] = identity
                changed = True


def signal_descendants(tracked, signum):
    try:
        snapshot = process_snapshot()
    except (OSError, ValueError, subprocess.SubprocessError):
        return
    for pid, identity in tracked.items():
        if pid in snapshot and snapshot[pid][2] == identity:
            try:
                os.kill(pid, signum)
            except ProcessLookupError:
                pass


def stop_process(process, tracked=None):
    """Stop the job group and its observed descendants, including new sessions."""
    tracked = tracked or {}
    track_descendants(process.pid, tracked)
    signal_descendants(tracked, signal.SIGTERM)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    signal_descendants(tracked, signal.SIGKILL)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_job(job, cwd, environment, logs, cancelled=None):
    cancelled = cancelled or threading.Event()
    started = time.monotonic()
    logs = Path(logs)
    logs.mkdir(parents=True, exist_ok=True)
    result = {"name": job.name, "status": "passed", "returncode": 0,
              "log": str(logs / (job.name + ".log")), "commands": job.commands}
    with open(result["log"], "w", encoding="utf-8") as output:
        for command in job.commands:
            if cancelled.is_set():
                result.update(status="cancelled", returncode=130)
                break
            remaining = job.timeout - (time.monotonic() - started)
            if remaining <= 0:
                result.update(status="timeout", returncode=124)
                break
            output.write("$ " + " ".join(command) + "\n")
            output.flush()
            try:
                process = subprocess.Popen(command, cwd=str(cwd),
                                           env=dict(environment, **job.environment),
                                           stdin=subprocess.DEVNULL, stdout=output,
                                           stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as error:
                output.write(str(error) + "\n")
                result.update(status="failed", returncode=127, failed_command=command)
                break
            deadline = started + job.timeout
            descendants = {}
            next_snapshot = 0
            while process.poll() is None:
                if cancelled.is_set() or time.monotonic() >= deadline:
                    stop_process(process, descendants)
                    result.update(status="cancelled" if cancelled.is_set() else "timeout",
                                  returncode=130 if cancelled.is_set() else 124,
                                  failed_command=command)
                    break
                if time.monotonic() >= next_snapshot:
                    track_descendants(process.pid, descendants)
                    next_snapshot = time.monotonic() + 0.5
                cancelled.wait(min(0.1, max(0, deadline - time.monotonic())))
            if result["status"] != "passed":
                break
            if process.returncode:
                stop_process(process, descendants)
                result.update(status="failed", returncode=process.returncode, failed_command=command)
                break
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def run_batch(jobs, workers, cwd, environment, logs, cancelled=None):
    """Keep result order stable while independent phases use bounded workers."""
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = [executor.submit(run_job, job, cwd, environment, logs, cancelled) for job in jobs]
        return [future.result() for future in pending]


def test_report(result):
    skipped = [{"test": test.id(), "reason": reason} for test, reason in result.skipped]
    successful = result.wasSuccessful() and result.testsRun > 0 and not skipped
    return {"status": "passed" if successful else "failed", "tests_run": result.testsRun,
            "failures": len(result.failures), "errors": len(result.errors),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses), "skipped": skipped}


def python_tests(summary):
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = test_report(result)
    report["seconds"] = round(time.monotonic() - started, 3)
    write_json(summary, report)
    for item in report["skipped"]:
        print("Mandatory test skipped: " + item["test"] + ": " + item["reason"], file=sys.stderr)
    return 0 if report["status"] == "passed" else 1


def inspect_python_report(path):
    """A zero child exit alone cannot prove that mandatory discovery ran."""
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, "Python test report is missing or unreadable: " + str(error)
    if not isinstance(report, dict):
        return None, "Python test report must be an object"
    if report.get("status") != "passed":
        return report, "Python test report does not report success"
    count = report.get("tests_run")
    if type(count) is not int or count <= 0:
        return report, "Python test report must include nonempty discovery"
    for field in ("failures", "errors", "unexpected_successes"):
        if type(report.get(field)) is not int or report[field] != 0:
            return report, "Python test report contains missing or unsuccessful " + field
    skipped = report.get("skipped")
    if not isinstance(skipped, list) or skipped:
        return report, "Python test report must explicitly report zero skipped tests"
    return report, None


def environment_for(home, cache, jobs, toolchain_root=None):
    # Never inherit provider credentials, Godmode selections or startup hooks.
    allowed = ("PATH", "TMPDIR", "SYSTEMROOT", "SDKROOT", "DEVELOPER_DIR")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                       XDG_CACHE_HOME=str(home / "cache"), XDG_DATA_HOME=str(home / "data"),
                       CODEX_HOME=str(home / ".codex"), COPILOT_HOME=str(home / ".copilot"),
                       SHELL="/bin/sh", TERM="dumb", LC_ALL="C", PYTHONDONTWRITEBYTECODE="1",
                       GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", GOENV="off",
                       GOCACHE=str(cache), CGO_ENABLED="0", GOMAXPROCS=str(jobs), GOFLAGS="-p=" + str(jobs))
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "/usr/bin:/bin")
    if toolchain_root is not None:
        environment["GOROOT"] = str(toolchain_root)
        environment["PATH"] = str(toolchain_root / "bin") + os.pathsep + environment["PATH"]
    return environment


def preflight(args):
    errors = []
    if sys.version_info < (3, 9):
        errors.append("Python 3.9 or newer is required.")
    if os.name != "posix":
        errors.append("The PTY and installer tests require macOS or Linux.")
    for command in ("go", "git", "sh", "ps"):
        if not shutil.which(command):
            errors.append("Missing command: " + command)
    missing = [module for module in ("pyte", "PIL", "wcwidth") if importlib.util.find_spec(module) is None]
    if missing:
        errors.append("Missing terminal test dependencies (" + ", ".join(missing) +
                      "). Install with: " + sys.executable + " -m pip install -r scripts/demo-requirements.txt")
    if args.require_shellcheck and not shutil.which("shellcheck"):
        errors.append("shellcheck is required by --require-shellcheck.")
    return errors


def exit_status(code):
    return code if code > 0 else 128 - code


def go_toolchain():
    # Resolve the already-installed pinned compiler before isolating HOME;
    # otherwise a cached Go toolchain under ~/go disappears from Go's lookup.
    pinned = next(line.split()[1] for line in (ROOT / "go.mod").read_text().splitlines() if line.startswith("go "))
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "GOCACHE", "GOMODCACHE", "TMPDIR") if key in os.environ}
    environment.update(GOENV="off", GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off")
    fields = ["GOROOT", "GOCACHE", "GOVERSION", "GOMODCACHE", "GOOS", "GOARCH"]
    result = subprocess.run(["go", "env", "-json", *fields],
                            cwd=str(ROOT), env=environment, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, timeout=15)
    toolchain = json.loads(result.stdout)
    if toolchain.get("GOVERSION") != "go" + pinned:
        # Go's automatic selection verifies its module even when it is cached;
        # call the cached compiler itself to make this lookup strictly offline.
        module_cache = Path(toolchain.get("GOMODCACHE", ""))
        installed = module_cache / ("golang.org/toolchain@v0.0.1-go" + pinned + "." +
                                    toolchain.get("GOOS", "") + "-" + toolchain.get("GOARCH", ""))
        compiler = installed / "bin/go"
        if not module_cache.is_absolute() or not compiler.is_file():
            raise ValueError("Install the compiler pinned in go.mod: go" + pinned)
        environment["GOROOT"] = str(installed)
        result = subprocess.run([str(compiler), "env", "-json", *fields], cwd=str(ROOT),
                                env=environment, check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=15)
        toolchain = json.loads(result.stdout)
    if toolchain.get("GOVERSION") != "go" + pinned:
        raise ValueError("Install the compiler pinned in go.mod: go" + pinned)
    for name in ("GOROOT", "GOCACHE"):
        if not isinstance(toolchain.get(name), str) or not Path(toolchain[name]).is_absolute():
            raise ValueError("go env " + name + " must resolve to an absolute path")
    return toolchain


def show_failure(result):
    print("Failure log: " + result["log"], file=sys.stderr, flush=True)
    with open(result["log"], "rb") as source:
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(max(0, size - 16384))
        tail = source.read().decode("utf-8", "replace").splitlines()[-80:]
    print("\n".join(tail), file=sys.stderr, flush=True)


def check(args):
    started = time.monotonic()
    summary = Path(args.summary).resolve()
    # Separate logs per run; keep the requested JSON location stable for CI.
    log_parent = ROOT / "target/checks"
    log_parent.mkdir(parents=True, exist_ok=True)
    logs = Path(tempfile.mkdtemp(prefix="run-", dir=str(log_parent)))
    report = {"schema": 1, "mode": "full" if args.full else "standard", "jobs": args.jobs,
              "status": "failed", "phases": [], "python": sys.version.split()[0],
              "optional_dependencies": {"shellcheck": bool(shutil.which("shellcheck"))},
              "logs": str(logs)}

    def finish(code):
        report["status"] = "passed" if code == 0 else "failed"
        report["seconds"] = round(time.monotonic() - started, 3)
        write_json(summary, report)
        print("Checks " + report["status"] + " in " + str(report["seconds"]) + "s; summary: " + str(summary), flush=True)
        return code

    errors = preflight(args)
    if errors:
        report["phases"].append({"name": "preflight", "status": "failed", "errors": errors})
        for error in errors:
            print(error, file=sys.stderr)
        return finish(1)
    try:
        toolchain = go_toolchain()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message = "Cannot resolve the installed Go compiler pinned in go.mod (network downloads are disabled): " + str(error)
        report["phases"].append({"name": "preflight", "status": "failed", "errors": [message]})
        print(message, file=sys.stderr)
        return finish(1)
    report["go"] = toolchain["GOVERSION"]
    cancelled = threading.Event()
    handlers = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        handlers[signum] = signal.signal(signum, lambda _signum, _frame: cancelled.set())
    try:
        with tempfile.TemporaryDirectory(prefix="godmode-check-home-") as temporary:
            environment = environment_for(Path(temporary), Path(toolchain["GOCACHE"]), args.jobs, Path(toolchain["GOROOT"]))
            # Generation/build steps share source files and must be sequential.
            prepare = [
                Job("source", [[sys.executable, "scripts/build.py", "--verify", "internal/core/core.py"],
                               ["go", "version"]], 60),
                Job("build-native", [["sh", "scripts/build-native.sh"]]),
                Job("build-license", [["sh", "scripts/build-license-test.sh"]]),
            ]
            python_summary = logs / "python.json"
            python_command = [sys.executable, "scripts/check.py", "--python-tests", "--summary", str(python_summary)]
            static_commands = [["sh", "-n", name] for name in SHELL_FILES]
            if shutil.which("shellcheck"):
                static_commands.append(["shellcheck", "-s", "sh", *SHELL_FILES])
            phases = [
                Job("python", [python_command], args.timeout),
                Job("go", [["go", "test", "-mod=vendor", "-count=1", "-timeout=5m", "./..."],
                           ["go", "test", "-mod=vendor", "-count=1", "-timeout=2m", "./vendor/github.com/charmbracelet/ultraviolet", "-run", "TestGodmode"],
                           ["go", "vet", "-mod=vendor", "./..."]], args.timeout),
                Job("installer", [["sh", "tests/install.sh"], ["sh", "tests/install-update.sh"]], args.timeout,
                    {"GODMODE_TEST_NATIVE_BINARY": str(ROOT / "target/godmode-native")}),
                Job("shell", static_commands, 120),
            ]
            if args.full:
                phases.append(Job("go-race", [["go", "test", "-race", "-mod=vendor", "-count=1", "-timeout=5m", "./..."]],
                                  args.timeout, {"CGO_ENABLED": "1"}))
                version = (ROOT / "VERSION").read_text().strip()
                for system in ("darwin", "linux"):
                    for cpu in ("arm64", "amd64"):
                        name = system + "-" + cpu
                        output = logs / name
                        commands = [["go", "build", "-mod=vendor", "-trimpath", "-buildvcs=false",
                                     "-ldflags=-buildid= -X main.version=" + version,
                                     "-o", str(output / "godmode"), "./cmd/godmode"]]
                        phases.append(Job("cross-" + name, commands, args.timeout, {"GOOS": system, "GOARCH": cpu}))
            for index, job in enumerate(prepare):
                print("Running " + job.name + "...", flush=True)
                result = run_job(job, ROOT, environment, logs, cancelled)
                report["phases"].append(result)
                print(job.name + ": " + result["status"] + " (" + str(result["seconds"]) + "s)", flush=True)
                if result["status"] != "passed":
                    for pending in prepare[index + 1:] + phases:
                        report["phases"].append({"name": pending.name, "status": "blocked", "reason": job.name + " did not pass"})
                    show_failure(result)
                    return finish(130 if cancelled.is_set() else exit_status(result["returncode"]))
            print("Running " + ", ".join(job.name for job in phases) + " with " + str(args.jobs) + " workers...", flush=True)
            results = run_batch(phases, args.jobs, ROOT, environment, logs, cancelled)
            python_report, report_error = inspect_python_report(python_summary)
            if python_report is not None:
                report["python_tests"] = python_report
            if report_error:
                python_result = next(result for result in results if result["name"] == "python")
                if python_result["status"] == "passed":
                    python_result.update(status="failed", returncode=1)
                with open(python_result["log"], "a", encoding="utf-8") as output:
                    output.write("\n" + report_error + "\n")
            report["phases"].extend(results)
            for result in results:
                print(result["name"] + ": " + result["status"] + " (" + str(result["seconds"]) + "s)" +
                      ("; " + result["log"] if result["status"] != "passed" else ""), flush=True)
                if result["status"] != "passed":
                    show_failure(result)
            failed = next((result for result in results if result["status"] != "passed"), None)
            return finish(130 if cancelled.is_set() else (exit_status(failed["returncode"]) if failed else 0))
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Also run race tests and all four native target builds.")
    parser.add_argument("--jobs", type=int, default=2, help="Concurrent phases and maximum Go build workers (default: 2).")
    parser.add_argument("--timeout", type=float, default=1200, help="Deadline in seconds for each test phase (default: 1200).")
    parser.add_argument("--summary", default="target/checks/summary.json", help="Machine-readable JSON results.")
    parser.add_argument("--require-shellcheck", action="store_true", help="Fail if shellcheck is unavailable.")
    parser.add_argument("--python-tests", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    if not 0 < args.timeout <= 7200:
        parser.error("--timeout must be between 0 and 7200 seconds")
    if args.python_tests:
        return python_tests(args.summary)
    return check(args)


if __name__ == "__main__":
    sys.exit(main())
