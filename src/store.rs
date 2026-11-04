use crate::{
    envfile::{self, EnvFile, Lookup},
    registry::Registry,
};
use std::{
    fs::{self, File, OpenOptions},
    hash::{Hash, Hasher},
    os::{
        fd::AsRawFd,
        unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt},
    },
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
};
use zeroize::Zeroizing;

pub const DISCLAIMER: &str = "Before you start

Godmode keeps provider credentials in one .env.godmode file so your agents can use them. Depending on the permissions you give them, those agents can deploy code, delete infrastructure, send mail, publish things and spend money. If that is more access than you intended, change the permissions at the provider before saving the key here.

The file is plaintext, with mode 0600. Other ordinary users cannot read it, but programs running as you can, as can privileged processes. Godmode does not sandbox those programs or enforce a spending limit. Storing a live key does not authorize live charges or public actions; use only credentials you are entitled to use, and revoke any that leak.

`run` passes the keys you select to a command. It does not filter that command's output, so a program that prints its environment can still disclose them. Keep the credential file out of Git, bug reports and terminal transcripts.

The CLI sends no telemetry and does not check credentials with providers. Picard media is fetched from YTMND only when requested; browser links also open only on request.

Existing credentials and operating rules are kept. Accepting creates the credential file if it is missing and records this acknowledgement locally. Type GODMODE to continue, or press Esc to leave.";

struct WriteGuard {
    _config: File,
    _state: File,
}

pub struct Store {
    pub env_path: PathBuf,
    pub config_dir: PathBuf,
    pub state_dir: PathBuf,
    scope: String,
}
impl Store {
    pub fn new(config_dir: PathBuf, state_dir: PathBuf) -> Result<Self, String> {
        let config_dir = absolute(config_dir)?;
        let state_dir = absolute(state_dir)?;
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        config_dir.hash(&mut hasher);
        Ok(Self {
            env_path: config_dir.join(".env.godmode"),
            config_dir,
            state_dir,
            scope: format!("{:016x}", hasher.finish()),
        })
    }
    fn receipt(&self) -> PathBuf {
        self.state_dir.join(format!("ack-v1-{}", self.scope))
    }
    pub fn is_initialized(&self) -> bool {
        let p = self.receipt();
        matches!(envfile::read(&p,None,true), Ok(r) if matches!(r.file.get("ACKNOWLEDGED"),Lookup::Present(v) if *v == "GODMODE-v1"))
    }
    pub fn acknowledge(&self) -> Result<(), String> {
        let _lock = self.lock()?;
        private_dir(&self.config_dir)?;
        self.git_guard()?;
        if self.env_path.symlink_metadata().is_ok() {
            envfile::read(&self.env_path, None, true).map_err(|e| e.to_string())?;
        } else {
            envfile::create_empty(&self.env_path).map_err(|e| e.to_string())?;
        }
        envfile::write_atomic(&self.receipt(), "ACKNOWLEDGED=GODMODE-v1\n", None)
            .map_err(|e| e.to_string())
    }
    pub fn load(&self) -> Result<EnvFile, String> {
        let facts = envfile::inspect(&self.env_path, None).map_err(|e| e.to_string())?;
        if facts.symlink_component.is_some() {
            return Err("Credential path contains a symlink; refusing".into());
        }
        if !facts.exists {
            return Ok(EnvFile::empty());
        }
        envfile::read(&self.env_path, None, true)
            .and_then(|r| {
                if !r.facts.strict_ok() {
                    return Err(envfile::EnvError::Raced(self.env_path.clone()));
                }
                Ok(r.file)
            })
            .map_err(|e| e.to_string())
    }
    pub fn set(&self, key: &str, value: &str, registry: &Registry) -> Result<(), String> {
        valid_key(key)?;
        if !self.is_initialized() {
            return Err(
                "Run `godmode init` to acknowledge the destination and credential disclaimer first"
                    .into(),
            );
        }
        let value = normalize(key, value, registry)?;
        let _lock = self.lock()?;
        self.git_guard()?;
        let mut file = self.load()?;
        file.set(key, &value, None).map_err(|e| e.to_string())?;
        let text = Zeroizing::new(file.render());
        envfile::write_atomic(&self.env_path, &text, Some(&self.state_dir))
            .map_err(|e| e.to_string())
    }
    pub fn unset(&self, key: &str) -> Result<bool, String> {
        valid_key(key)?;
        if !self.is_initialized() {
            return Err("Run `godmode init` before editing credentials".into());
        }
        let _lock = self.lock()?;
        self.git_guard()?;
        let mut file = self.load()?;
        let removed = file.unset(key) > 0;
        if removed {
            let text = Zeroizing::new(file.render());
            envfile::write_atomic(&self.env_path, &text, Some(&self.state_dir))
                .map_err(|e| e.to_string())?;
        }
        Ok(removed)
    }
    fn lock(&self) -> Result<WriteGuard, String> {
        private_dir(&self.config_dir)?;
        let config = envfile::lock_directory(&self.config_dir).map_err(|e| e.to_string())?;
        private_dir(&self.state_dir)?;
        let state_meta =
            fs::symlink_metadata(&self.state_dir).map_err(|_| "Cannot inspect state directory")?;
        if state_meta.uid() != unsafe { libc::geteuid() } || state_meta.mode() & 0o077 != 0 {
            return Err("State directory must be owned by you and private (mode 0700)".into());
        }
        let p = self.state_dir.join(format!("write-{}.lock", self.scope));
        let f = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(p)
            .map_err(|_| "Cannot open local writer lock")?;
        let m = f.metadata().map_err(|_| "Cannot inspect writer lock")?;
        if !m.is_file()
            || m.uid() != unsafe { libc::geteuid() }
            || m.mode() & 0o777 != 0o600
            || m.nlink() != 1
        {
            return Err("Unsafe writer lock".into());
        }
        if unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err("Another Godmode writer is active; retry after it finishes".into());
        }
        Ok(WriteGuard {
            _config: config,
            _state: f,
        })
    }
    fn git_guard(&self) -> Result<(), String> {
        if !self.config_dir.ancestors().any(|p| p.join(".git").exists()) {
            return Ok(());
        }
        let run = |args: &[&str]| {
            Command::new("git")
                .env_clear()
                .env("PATH", std::env::var_os("PATH").unwrap_or_default())
                .env("GIT_CONFIG_NOSYSTEM", "1")
                .env("GIT_CONFIG_GLOBAL", "/dev/null")
                .arg("-c")
                .arg("core.hooksPath=/dev/null")
                .arg("-c")
                .arg("core.fsmonitor=false")
                .arg("-C")
                .arg(&self.config_dir)
                .args(args)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
        };
        let tracked = run(&["ls-files", "--error-unmatch", "--", ".env.godmode"])
            .map_err(|_| "Git is required to verify credential exclusion")?;
        if tracked.success() {
            return Err("Credential file is tracked by Git; refusing to write".into());
        }
        if tracked.code() != Some(1) {
            return Err("Could not establish whether the credential file is tracked".into());
        }
        if !run(&["check-ignore", "-q", "--", ".env.godmode"])
            .map_err(|_| "Cannot check Git exclusion")?
            .success()
        {
            return Err(
                "Add .env.godmode to this checkout's .gitignore before writing credentials".into(),
            );
        }
        Ok(())
    }
}

pub fn valid_key(key: &str) -> Result<(), String> {
    if envfile::is_valid_key(key) {
        Ok(())
    } else {
        Err("Invalid key name; use letters, numbers and underscores, starting with a letter or underscore".into())
    }
}
fn absolute(path: PathBuf) -> Result<PathBuf, String> {
    let p = if path.is_absolute() {
        path
    } else {
        std::env::current_dir()
            .map_err(|_| "Cannot resolve current directory")?
            .join(path)
    };
    let mut clean = PathBuf::new();
    for part in p.components() {
        match part {
            Component::CurDir => {}
            Component::ParentDir => {
                return Err("Use paths without parent traversal (..)".into());
            }
            other => clean.push(other.as_os_str()),
        }
    }
    Ok(clean)
}
pub fn private_dir(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        private_dir(parent)?;
    }
    match fs::symlink_metadata(path) {
        Ok(m) => {
            if m.file_type().is_symlink() || !m.is_dir() {
                return Err(
                    "Configuration/state directory contains a symlink or non-directory".into(),
                );
            }
            // Shared ancestors such as /tmp are allowed; the final directory is checked below by callers.
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            fs::DirBuilder::new()
                .mode(0o700)
                .create(path)
                .map_err(|_| "Cannot create private directory")?;
        }
        Err(_) => return Err("Cannot inspect configuration/state directory".into()),
    }
    Ok(())
}
pub fn normalize(key: &str, value: &str, registry: &Registry) -> Result<Zeroizing<String>, String> {
    if value.len() > envfile::MAX_SIZE as usize {
        return Err("Credential exceeds the size limit".into());
    }
    let meta = registry.find_key(key);
    let mut output = Zeroizing::new(value.to_string());
    if meta.is_some_and(|m| m.json) {
        let parsed: serde_json::Value =
            serde_json::from_str(&output).map_err(|_| "Invalid JSON; no value was saved")?;
        if !parsed.is_object() {
            return Err("Expected a JSON object".into());
        }
        *output = serde_json::to_string(&parsed).map_err(|_| "Cannot compact JSON")?;
    }
    if output.is_empty() {
        return Err("Empty credential; use `unset` to remove a key".into());
    }
    if output.chars().any(char::is_control) {
        return Err("Credential contains control characters; JSON keys accept raw JSON and compact it automatically".into());
    }
    if meta.is_some_and(|m| m.forbid_prefixes.iter().any(|p| output.starts_with(p))) {
        return Err(
            "Credential belongs to the wrong environment for this key; nothing saved".into(),
        );
    }
    Ok(output)
}

/// Only basic terminal/process context is inherited. All other variables must be selected explicitly.
pub fn run_selected(store: &Store, mappings: &[String], argv: &[String]) -> Result<i32, String> {
    if argv.is_empty() {
        return Err("Provide a command after --".into());
    }
    let file = store.load()?;
    let mut command = Command::new(&argv[0]);
    command.args(&argv[1..]).env_clear();
    for (key, value) in std::env::vars_os() {
        let k = key.to_string_lossy();
        if matches!(
            k.as_ref(),
            "PATH"
                | "HOME"
                | "USER"
                | "LOGNAME"
                | "SHELL"
                | "TERM"
                | "COLORTERM"
                | "LANG"
                | "TMPDIR"
                | "TZ"
        ) || k.starts_with("LC_")
        {
            command.env(key, value);
        }
    }
    let mut targets = std::collections::HashSet::new();
    for mapping in mappings {
        let (key, target) = mapping.split_once('=').unwrap_or((mapping, mapping));
        valid_key(key)?;
        valid_key(target)?;
        if !targets.insert(target) {
            return Err("Duplicate target environment variable".into());
        }
        match file.get(key) {
            Lookup::Present(value) => {
                command.env(target, &*value);
            }
            _ => return Err(format!("{key} is missing, blank, duplicated or malformed")),
        }
    }
    let status = command
        .status()
        .map_err(|_| "Could not launch the requested command")?;
    use std::os::unix::process::ExitStatusExt;
    Ok(status
        .code()
        .unwrap_or_else(|| 128 + status.signal().unwrap_or(1)))
}
