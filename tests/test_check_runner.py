"""Exercise runner failure/timeout boundaries without building or user state."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("godmode_check_runner", ROOT / "scripts/check.py")
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class CheckRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="godmode-runner-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = {"PATH": os.environ["PATH"], "HOME": str(self.root)}

    def run_job(self, job, cancelled=None):
        return runner.run_job(job, self.root, self.environment, self.root / "logs", cancelled)

    def test_command_failure_preserves_exit_and_stops_dependent_commands(self):
        sentinel = self.root / "must-not-run"
        result = self.run_job(runner.Job("failure", [
            [sys.executable, "-c", "print('diagnostic'); raise SystemExit(7)"],
            [sys.executable, "-c", "from pathlib import Path; Path('must-not-run').touch()"],
        ]))
        self.assertEqual((result["status"], result["returncode"]), ("failed", 7))
        self.assertFalse(sentinel.exists())
        self.assertIn("diagnostic", Path(result["log"]).read_text())

    def test_missing_executable_is_a_failed_phase(self):
        result = self.run_job(runner.Job("missing", [[str(self.root / "missing")]]))
        self.assertEqual((result["status"], result["returncode"]), ("failed", 127))

    def test_timeout_terminates_the_process_group(self):
        marker = self.root / "escaped-child"
        child = "import time; from pathlib import Path; time.sleep(.8); Path('escaped-child').touch()"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1]]); time.sleep(30)"
        result = self.run_job(runner.Job("timeout", [[sys.executable, "-c", parent, child]], timeout=.3))
        self.assertEqual((result["status"], result["returncode"]), ("timeout", 124))
        self.assertLess(result["seconds"], 3)
        time.sleep(.7)
        self.assertFalse(marker.exists(), "job timeout left its child running")

    def test_timeout_also_stops_a_child_in_a_new_session(self):
        marker = self.root / "detached-child"
        child = "import time; from pathlib import Path; time.sleep(.8); Path('detached-child').touch()"
        parent = ("import subprocess,sys,time; "
                  "subprocess.Popen([sys.executable,'-c',sys.argv[1]],start_new_session=True); time.sleep(30)")
        result = self.run_job(runner.Job("detached", [[sys.executable, "-c", parent, child]], timeout=.3))
        self.assertEqual((result["status"], result["returncode"]), ("timeout", 124))
        time.sleep(.7)
        self.assertFalse(marker.exists(), "job timeout left a detached child running")

    def test_failed_command_also_stops_its_observed_detached_child(self):
        marker = self.root / "failed-command-child"
        child = "import time; from pathlib import Path; time.sleep(1.4); Path('failed-command-child').touch()"
        parent = ("import subprocess,sys,time; "
                  "subprocess.Popen([sys.executable,'-c',sys.argv[1]],start_new_session=True); "
                  "time.sleep(.8); raise SystemExit(7)")
        result = self.run_job(runner.Job("failed-child", [[sys.executable, "-c", parent, child]], timeout=5))
        self.assertEqual((result["status"], result["returncode"]), ("failed", 7))
        time.sleep(.8)
        self.assertFalse(marker.exists(), "failed job left its observed detached child running")

    def test_cancelled_job_cannot_report_passed(self):
        cancelled = threading.Event()
        timer = threading.Timer(.15, cancelled.set)
        timer.start()
        self.addCleanup(timer.cancel)
        result = self.run_job(runner.Job("cancel", [[sys.executable, "-c", "import time; time.sleep(30)"]]), cancelled)
        self.assertEqual((result["status"], result["returncode"]), ("cancelled", 130))

    def test_independent_workers_are_bounded_and_keep_failures(self):
        active = 0
        peak = 0
        lock = threading.Lock()

        def work(job, *_args):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(active, peak)
            time.sleep(.04)
            with lock:
                active -= 1
            return {"name": job.name, "status": "failed" if job.name == "2" else "passed"}

        jobs = [runner.Job(str(index), []) for index in range(5)]
        with mock.patch.object(runner, "run_job", side_effect=work):
            results = runner.run_batch(jobs, 2, self.root, self.environment, self.root)
        self.assertEqual(peak, 2)
        self.assertEqual([result["name"] for result in results], [str(index) for index in range(5)])
        self.assertEqual(results[2]["status"], "failed")

    def test_missing_core_tests_and_empty_discovery_fail_closed(self):
        class MissingCore(unittest.TestCase):
            def runTest(self):
                self.skipTest("Build the native candidate first.")

        result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([MissingCore()]))
        report = runner.test_report(result)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(report["skipped"]), 1)
        self.assertEqual(runner.test_report(unittest.TestResult())["status"], "failed")

    def test_every_skip_fails_even_when_unittest_reports_success(self):
        test = mock.Mock()
        test.id.return_value = "fixture.OptionalDependency.test_feature"
        result = unittest.TestResult()
        result.testsRun = 1
        result.addSkip(test, "optional dependency absent")
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(runner.test_report(result)["status"], "failed")

    def test_sanitized_environment_excludes_keys_and_agent_selection(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "synthetic", "GODMODE_HOME": "/wrong",
                                          "GODMODE_ENV": "wrong", "PYTHONPATH": "/wrong",
                                          "BASH_ENV": "/wrong", "CGO_ENABLED": "1"}):
            environment = runner.environment_for(self.root, self.root / "go-cache", 2)
        for name in ("GH_TOKEN", "GODMODE_HOME", "GODMODE_ENV", "PYTHONPATH", "BASH_ENV"):
            self.assertNotIn(name, environment)
        self.assertEqual(environment["HOME"], str(self.root))
        self.assertEqual(environment["CGO_ENABLED"], "0")
        self.assertEqual(environment["GOMAXPROCS"], "2")

    def test_resolved_compiler_remains_available_after_home_isolation(self):
        toolchain = self.root / "cached-go"
        environment = runner.environment_for(self.root / "home", self.root / "cache", 2, toolchain)
        self.assertEqual(environment["GOROOT"], str(toolchain))
        self.assertEqual(environment["PATH"].split(os.pathsep)[0], str(toolchain / "bin"))

    def test_toolchain_resolution_rejects_wrong_version_without_forwarding_keys(self):
        output = mock.Mock(stdout=json.dumps({"GOVERSION": "go0.1.0", "GOROOT": "/fixture/go", "GOCACHE": "/fixture/cache"}))
        with mock.patch.dict(os.environ, {"GH_TOKEN": "synthetic"}), \
                mock.patch.object(runner.subprocess, "run", return_value=output) as invoke:
            with self.assertRaisesRegex(ValueError, "compiler pinned"):
                runner.go_toolchain()
        environment = invoke.call_args.kwargs["env"]
        self.assertNotIn("GH_TOKEN", environment)
        self.assertEqual(environment["GOPROXY"], "off")

    def test_descendant_cleanup_refuses_reused_process_id(self):
        with mock.patch.object(runner, "process_snapshot", return_value={12345: (1, 12345, "new-identity")}), \
                mock.patch.object(runner.os, "kill") as kill:
            runner.signal_descendants({12345: "old-identity"}, runner.signal.SIGKILL)
        kill.assert_not_called()

    def test_json_summary_is_complete_and_replaces_old_result(self):
        path = self.root / "results/summary.json"
        runner.write_json(path, {"status": "passed"})
        runner.write_json(path, {"status": "failed", "returncode": 7})
        self.assertEqual(json.loads(path.read_text()), {"status": "failed", "returncode": 7})
        self.assertFalse(path.with_name("summary.json.tmp").exists())

    def test_successful_child_requires_a_valid_nonempty_report(self):
        path = self.root / "python.json"
        self.assertIsNotNone(runner.inspect_python_report(path)[1])
        path.write_text("not json")
        self.assertIsNotNone(runner.inspect_python_report(path)[1])
        valid = {"status": "passed", "tests_run": 2, "failures": 0, "errors": 0,
                 "unexpected_successes": 0, "skipped": []}
        for bad in ([], {}, dict(valid, status="failed"), dict(valid, tests_run=0),
                    dict(valid, tests_run=True), dict(valid, failures=1),
                    dict(valid, errors=None), dict(valid, unexpected_successes=1),
                    dict(valid, skipped=[{"test": "core", "allowed": False}]),
                    dict(valid, skipped=[{"test": "core", "allowed": True}]),
                    dict(valid, skipped=None)):
            with self.subTest(report=bad):
                runner.write_json(path, bad)
                self.assertIsNotNone(runner.inspect_python_report(path)[1])
        runner.write_json(path, valid)
        self.assertEqual(runner.inspect_python_report(path), (valid, None))


if __name__ == "__main__":
    unittest.main()
