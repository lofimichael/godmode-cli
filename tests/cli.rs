use std::{
    fs,
    io::Write,
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::{Command, Output, Stdio},
};
struct Fixture {
    _root: tempfile::TempDir,
    config: PathBuf,
    state: PathBuf,
}
impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let p = root.path().canonicalize().unwrap();
        Self {
            _root: root,
            config: p.join("config"),
            state: p.join("state"),
        }
    }
    fn command(&self, args: &[&str]) -> Command {
        let mut c = Command::new(env!("CARGO_BIN_EXE_godmode"));
        c.args([
            "--config-dir",
            self.config.to_str().unwrap(),
            "--state-dir",
            self.state.to_str().unwrap(),
        ])
        .args(args)
        .env_remove("GODMODE_REGISTRY")
        .stdin(Stdio::null());
        c
    }
    fn run(&self, args: &[&str]) -> Output {
        self.command(args).output().unwrap()
    }
    fn init(&self) {
        assert!(self.run(&["init", "--accept-disclaimer"]).status.success());
    }
    fn set(&self, key: &str, value: &str) -> Output {
        let mut c = self
            .command(&["set", key, "--stdin"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        c.stdin.take().unwrap().write_all(value.as_bytes()).unwrap();
        c.wait_with_output().unwrap()
    }
    fn env(&self) -> PathBuf {
        self.config.join(".env.godmode")
    }
}
fn no_leak(out: &Output, secret: &str) {
    assert!(!String::from_utf8_lossy(&out.stdout).contains(secret));
    assert!(!String::from_utf8_lossy(&out.stderr).contains(secret));
}
#[test]
fn init_does_not_overwrite_existing_configuration() {
    let f = Fixture::new();
    fs::create_dir(&f.config).unwrap();
    fs::write(f.config.join("AGENTS.md"), "existing rules").unwrap();
    let original = "# existing\nCUSTOM_TOKEN='leave me alone'\n";
    fs::write(f.env(), original).unwrap();
    fs::set_permissions(f.env(), fs::Permissions::from_mode(0o600)).unwrap();
    f.init();
    f.init();
    assert_eq!(fs::read_to_string(f.env()).unwrap(), original);
    assert_eq!(
        fs::read_to_string(f.config.join("AGENTS.md")).unwrap(),
        "existing rules"
    );
}
#[test]
fn arbitrary_keys_and_never_values_in_output() {
    let f = Fixture::new();
    f.init();
    let secret = "sentinel_Secret_%_12345";
    let saved = f.set("CUSTOM_ACCOUNT_WRITE_TOKEN", secret);
    assert!(saved.status.success());
    no_leak(&saved, secret);
    for args in [
        vec!["status"],
        vec!["status", "--json"],
        vec!["doctor", "--json"],
        vec!["has", "CUSTOM_ACCOUNT_WRITE_TOKEN"],
        vec!["providers", "--json"],
    ] {
        let out = f.run(&args);
        assert!(out.status.success());
        no_leak(&out, secret);
    }
    assert_eq!(
        fs::metadata(f.env()).unwrap().permissions().mode() & 0o777,
        0o600
    );
    assert!(
        f.run(&["unset", "CUSTOM_ACCOUNT_WRITE_TOKEN"])
            .status
            .success()
    );
    assert_eq!(
        f.run(&["has", "CUSTOM_ACCOUNT_WRITE_TOKEN"]).status.code(),
        Some(1)
    );
}
#[test]
fn refuses_value_arguments_and_writes_without_acknowledgement() {
    let f = Fixture::new();
    let secret = "sentinelNeverInArgv_998";
    let out = f.run(&["set", "MY_TOKEN", secret]);
    assert!(!out.status.success());
    no_leak(&out, secret);
    assert!(!f.env().exists());
    assert!(!f.set("MY_TOKEN", secret).status.success());
    assert!(!f.env().exists());
}
#[test]
fn compacts_multiline_json_and_refuses_wrong_stripe_environment() {
    let f = Fixture::new();
    f.init();
    let json = "{\n  \"private_key\": \"fixture-only\\nsecond-line\",\n  \"type\": \"service_account\"\n}\n";
    let out = f.set("GOOGLE_ADS_SERVICE_ACCOUNT_JSON", json);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!fs::read_to_string(f.env()).unwrap().contains("\n  "));
    let before = fs::read(f.env()).unwrap();
    let out = f.set("STRIPE_TEST_SECRET_KEY", "sk_live_fixture_only");
    assert!(!out.status.success());
    no_leak(&out, "sk_live_fixture_only");
    assert_eq!(fs::read(f.env()).unwrap(), before);
    let out = f.set(
        "GOOGLE_ADS_SERVICE_ACCOUNT_JSON",
        "{\"secret\": \"sentinel_invalid_json",
    );
    assert!(!out.status.success());
    no_leak(&out, "sentinel_invalid_json");
}
#[test]
fn run_only_injects_selected_keys_and_preserves_exit_code() {
    let f = Fixture::new();
    f.init();
    assert!(f.set("FIRST_SECRET", "fixture_one").status.success());
    assert!(f.set("SECOND_SECRET", "fixture_two").status.success());
    let out=f.command(&["run","--with","FIRST_SECRET=CHOSEN","--","/bin/sh","-c","test \"$CHOSEN\" = fixture_one && test -z \"${SECOND_SECRET+x}\" && test -z \"${INHERITED_SECRET+x}\" && exit 7"]).env("INHERITED_SECRET","must_not_inherit").output().unwrap();
    assert_eq!(out.status.code(), Some(7));
    assert!(out.stdout.is_empty());
    assert!(out.stderr.is_empty());
}
#[test]
fn refuses_unsafe_permissions_and_symlinks_without_changing_them() {
    let f = Fixture::new();
    f.init();
    f.set("SECRET", "sentinel_mode");
    fs::set_permissions(f.env(), fs::Permissions::from_mode(0o644)).unwrap();
    let before = fs::read(f.env()).unwrap();
    for out in [
        f.run(&["doctor", "--json"]),
        f.run(&["status"]),
        f.set("NEW", "fixture"),
    ] {
        assert!(!out.status.success());
        no_leak(&out, "sentinel_mode");
    }
    assert_eq!(fs::read(f.env()).unwrap(), before);
    fs::remove_file(f.env()).unwrap();
    let target = f.config.join("outside");
    fs::write(&target, "leave alone").unwrap();
    std::os::unix::fs::symlink(&target, f.env()).unwrap();
    assert!(!f.set("NEW", "fixture").status.success());
    assert_eq!(fs::read_to_string(target).unwrap(), "leave alone");
}
#[test]
fn detects_duplicates_and_preserves_unrelated_lines() {
    let f = Fixture::new();
    f.init();
    let source = "# keep this\r\nOTHER='unrelated'\nDUP=old\nDUP=older\n";
    fs::write(f.env(), source).unwrap();
    assert_eq!(f.run(&["doctor"]).status.code(), Some(1));
    assert!(f.set("DUP", "new'value #with spaces").status.success());
    let now = fs::read_to_string(f.env()).unwrap();
    assert!(now.starts_with("# keep this\r\nOTHER='unrelated'\n"));
    assert_eq!(now.matches("DUP=").count(), 1);
    assert!(f.run(&["doctor"]).status.success());
}
#[test]
fn git_checkout_requires_ignored_untracked_credential_file() {
    let f = Fixture::new();
    fs::create_dir(&f.config).unwrap();
    assert!(
        Command::new("git")
            .args(["init", "-q"])
            .arg(&f.config)
            .status()
            .unwrap()
            .success()
    );
    assert!(!f.run(&["init", "--accept-disclaimer"]).status.success());
    assert!(!f.env().exists());
    fs::write(f.config.join(".gitignore"), ".env.godmode\n").unwrap();
    f.init();
    assert!(
        Command::new("git")
            .arg("-C")
            .arg(&f.config)
            .args(["add", "-f", ".env.godmode"])
            .status()
            .unwrap()
            .success()
    );
    assert!(!f.set("KEY", "fixture").status.success());
}
#[test]
fn overlay_is_extensible_and_invalid_content_is_never_echoed() {
    let f = Fixture::new();
    f.init();
    let template = f.run(&["providers-template"]);
    fs::write(f.config.join("providers.toml"), &template.stdout).unwrap();
    let out = f.run(&["guide", "example"]);
    assert!(out.status.success());
    assert!(String::from_utf8_lossy(&out.stdout).contains("EXAMPLE_ACCOUNT_ADMIN_TOKEN"));
    fs::write(
        f.config.join("providers.toml"),
        "sentinelBadCatalog_998 = [bad input",
    )
    .unwrap();
    let out = f.run(&["providers"]);
    assert!(!out.status.success());
    no_leak(&out, "sentinelBadCatalog_998");
}
#[test]
fn same_configuration_lock_is_shared_across_state_overrides() {
    use std::os::fd::AsRawFd;
    let f = Fixture::new();
    f.init();
    let dir = std::fs::File::open(&f.config).unwrap();
    assert_eq!(
        unsafe { libc::flock(dir.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
        0
    );
    let alternate = f._root.path().canonicalize().unwrap().join("other-state");
    let out = Command::new(env!("CARGO_BIN_EXE_godmode"))
        .args([
            "--config-dir",
            f.config.to_str().unwrap(),
            "--state-dir",
            alternate.to_str().unwrap(),
            "init",
            "--accept-disclaimer",
        ])
        .env_remove("GODMODE_REGISTRY")
        .output()
        .unwrap();
    assert!(!out.status.success());
    assert_eq!(unsafe { libc::flock(dir.as_raw_fd(), libc::LOCK_UN) }, 0);
    assert!(f.run(&["init", "--accept-disclaimer"]).status.success());
}
#[test]
fn symlink_status_is_an_error_not_a_missing_key() {
    let f = Fixture::new();
    f.init();
    let target = f.config.join("original");
    fs::rename(f.env(), &target).unwrap();
    std::os::unix::fs::symlink(target, f.env()).unwrap();
    assert!(!f.run(&["status", "--json"]).status.success());
}
#[test]
fn git_environment_cannot_redirect_credential_checks() {
    let f = Fixture::new();
    fs::create_dir(&f.config).unwrap();
    assert!(
        Command::new("git")
            .args(["init", "-q"])
            .arg(&f.config)
            .status()
            .unwrap()
            .success()
    );
    let other = tempfile::tempdir().unwrap();
    assert!(
        Command::new("git")
            .args(["init", "-q"])
            .arg(other.path())
            .status()
            .unwrap()
            .success()
    );
    fs::write(other.path().join(".gitignore"), ".env.godmode\n").unwrap();
    let out = f
        .command(&["init", "--accept-disclaimer"])
        .env("GIT_DIR", other.path().join(".git"))
        .env("GIT_WORK_TREE", other.path())
        .output()
        .unwrap();
    assert!(!out.status.success());
    assert!(!f.env().exists());
}

#[test]
fn from_file_refuses_fifo_and_input_limits_leave_file_unchanged() {
    use std::os::unix::ffi::OsStrExt;
    let f = Fixture::new();
    f.init();
    let before = fs::read(f.env()).unwrap();
    let fifo = f.config.join("input-fifo");
    let name = std::ffi::CString::new(fifo.as_os_str().as_bytes()).unwrap();
    assert_eq!(unsafe { libc::mkfifo(name.as_ptr(), 0o600) }, 0);
    assert!(
        !f.run(&["set", "TOKEN", "--from-file", fifo.to_str().unwrap()])
            .status
            .success()
    );
    let oversized = f.config.join("oversized-input");
    fs::write(&oversized, vec![b'x'; 1_048_577]).unwrap();
    assert!(
        !f.run(&["set", "TOKEN", "--from-file", oversized.to_str().unwrap()])
            .status
            .success()
    );
    assert!(!f.set("TOKEN", "line\u{2028}separator").status.success());
    assert!(!f.set("TOKEN", "").status.success());
    assert_eq!(fs::read(f.env()).unwrap(), before);
}

#[test]
fn picard_link_bypasses_credentials_and_registry_without_writes() {
    let f = Fixture::new();
    fs::create_dir(&f.config).unwrap();
    fs::write(f.config.join("providers.toml"), "broken registry").unwrap();
    let out = f.run(&["picard", "link"]);
    assert!(out.status.success());
    assert_eq!(
        String::from_utf8(out.stdout).unwrap().trim(),
        "https://picard.ytmnd.com/"
    );
    assert!(!f.env().exists());
    assert!(!f.state.exists());
    let out = f.run(&["picard", "stop"]);
    assert!(out.status.success());
    assert!(!f.env().exists());
    assert!(!f.state.exists());
}

#[test]
fn picard_show_requires_terminal_before_network_or_storage() {
    let f = Fixture::new();
    fs::create_dir(&f.config).unwrap();
    fs::write(f.config.join("providers.toml"), "broken registry").unwrap();
    let out = f.run(&["picard", "show"]);
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8(out.stderr).unwrap().contains("terminal"));
    assert!(!f.env().exists());
    assert!(!f.state.exists());
}

#[test]
fn new_setup_warning_precedes_init_and_is_not_repeated_for_existing_setup() {
    let f = Fixture::new();
    let declined = f.run(&["init"]);
    assert!(!declined.status.success());
    assert!(String::from_utf8_lossy(&declined.stderr).contains("No existing Godmode setup found"));
    assert!(!f.config.exists());
    assert!(!f.state.exists());
    let accepted = f.run(&["init", "--accept-disclaimer"]);
    assert!(accepted.status.success());
    assert!(String::from_utf8_lossy(&accepted.stderr).contains("No existing Godmode setup found"));
    let original = fs::read(f.env()).unwrap();
    let repeated = f.run(&["init", "--accept-disclaimer"]);
    assert!(repeated.status.success());
    assert!(!String::from_utf8_lossy(&repeated.stderr).contains("No existing Godmode setup found"));
    assert_eq!(fs::read(f.env()).unwrap(), original);

    let legacy = Fixture::new();
    fs::create_dir(&legacy.config).unwrap();
    fs::write(legacy.config.join("AGENTS.md"), "existing operator rules").unwrap();
    let out = legacy.run(&["init", "--accept-disclaimer"]);
    assert!(out.status.success());
    assert!(!String::from_utf8_lossy(&out.stderr).contains("No existing Godmode setup found"));
}

#[test]
fn setup_refuses_redirected_input_without_creating_files() {
    let f = Fixture::new();
    let out = f.run(&["setup"]);
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("Setup needs a terminal"));
    assert!(!f.config.exists());
    assert!(!f.state.exists());
}

#[test]
fn setup_unknown_provider_does_not_echo_input_or_create_files() {
    let f = Fixture::new();
    let value = "SYNTHETIC_MISPLACED_SECRET_5823";
    let out = f.run(&["setup", value]);
    assert_eq!(out.status.code(), Some(2));
    no_leak(&out, value);
    assert!(!f.config.exists());
    assert!(!f.state.exists());
}
