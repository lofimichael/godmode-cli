//! Explicit, local playback of the original YTMND Picard excerpt.
//! The recording is fetched from YTMND only after `play`; it is never bundled.
//! Playback owns its child process. Cross-process stop uses a private Unix socket,
//! never a PID file or a signal sent to an unrelated process.

use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::{
        fd::AsRawFd,
        unix::{
            fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt},
            net::{UnixListener, UnixStream},
        },
    },
    path::{Component, Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

pub const SOURCE_URL: &str = "https://picard.ytmnd.com/";
pub const AUDIO_URL: &str =
    "https://users.content.ytmnd.com/d/0/3/d0330b0d03957ad58853427a6513e793.wav";
const AUDIO_SHA256: &str = "d69a477ba3b9a8d454512db12b2ce3da05ec72ffa36d7ab313b0ed8aff764db8";
const AUDIO_BYTES: usize = 351_860;
const MAX_DOWNLOAD: u64 = 1_048_576;
const CACHE_NAME: &str = "picard-d0330b0d.wav";
const SOCKET_NAME: &str = "p.sock";

pub struct Player {
    child: Option<Child>,
    backend: Backend,
    audio: PathBuf,
    listener: Option<UnixListener>,
    socket_path: PathBuf,
    socket_identity: (u64, u64),
    _lock: File,
    stopped: bool,
}

#[derive(Clone)]
struct Backend {
    program: PathBuf,
    args: Vec<&'static str>,
}

impl Player {
    pub fn start_cancellable(
        state_dir: &Path,
        mut cancel: impl FnMut() -> bool,
    ) -> Result<Self, String> {
        if cancel() {
            return Err("Picard playback canceled".into());
        }
        let backend = find_backend()?;
        let root = media_dir(state_dir)?;
        crate::store::private_dir(&root)?;
        private_directory(&root)?;
        let lock = crate::envfile::lock_directory(&root).map_err(|_| {
            "Picard is already playing or its state directory cannot be locked; use picard stop"
                .to_string()
        })?;
        // Establish the stop endpoint before doing any potentially slow work.
        let mut player = Self::controller(root.clone(), root.join(CACHE_NAME), backend, lock)?;
        player.audio = cached_audio(&root, &mut player, &mut cancel)?;
        if player.poll_cancel(&mut cancel)? {
            return Err("Picard playback canceled".into());
        }
        player.child = Some(player.spawn_child()?);
        Ok(player)
    }

    #[cfg(test)]
    fn start_owned(
        root: PathBuf,
        audio: PathBuf,
        backend: Backend,
        lock: File,
    ) -> Result<Self, String> {
        let mut player = Self::controller(root, audio, backend, lock)?;
        player.child = Some(player.spawn_child()?);
        Ok(player)
    }

    fn controller(
        root: PathBuf,
        audio: PathBuf,
        backend: Backend,
        lock: File,
    ) -> Result<Self, String> {
        let socket_path = root.join(SOCKET_NAME);
        if socket_metadata(&socket_path)?.is_some() {
            if UnixStream::connect(&socket_path).is_ok() {
                return Err("Picard is already playing; use picard stop".into());
            }
            // Holding the directory lock proves no cooperating player owns it.
            fs::remove_file(&socket_path).map_err(|_| "Cannot clear a stale Picard socket")?;
        }
        let listener = UnixListener::bind(&socket_path)
            .map_err(|_| "Cannot create Picard control socket; try a shorter --state-dir path")?;
        fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))
            .map_err(|_| "Cannot make Picard control socket private")?;
        listener
            .set_nonblocking(true)
            .map_err(|_| "Cannot configure Picard control socket")?;
        let meta = socket_metadata(&socket_path)?.ok_or("Picard control socket disappeared")?;
        Ok(Self {
            child: None,
            backend,
            audio,
            listener: Some(listener),
            socket_path,
            socket_identity: (meta.dev(), meta.ino()),
            _lock: lock,
            stopped: false,
        })
    }

    fn poll_cancel(&mut self, cancel: &mut dyn FnMut() -> bool) -> Result<bool, String> {
        if cancel() {
            self.stop()?;
        }
        self.stop_requested()
    }

    fn stop_requested(&mut self) -> Result<bool, String> {
        if self.stopped {
            return Ok(true);
        }
        if let Some(listener) = &self.listener {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let _ = stream.set_read_timeout(Some(Duration::from_millis(100)));
                    let _ = stream.set_write_timeout(Some(Duration::from_millis(100)));
                    let mut request = [0u8; 5];
                    if stream.read_exact(&mut request).is_ok() && &request == b"STOP\n" {
                        self.stop()?;
                        let _ = stream.write_all(b"OK\n");
                        return Ok(true);
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => (),
                Err(_) => {
                    let _ = self.stop();
                    return Err("Picard control socket failed; playback stopped".into());
                }
            }
        }
        Ok(false)
    }

    /// Service a stop request and repeat the eight-second excerpt after a clean
    /// completion. Returns false once stopped. Caller must call regularly.
    pub fn tick(&mut self) -> Result<bool, String> {
        if self.stop_requested()? {
            return Ok(false);
        }
        let status = match self.child.as_mut().map(Child::try_wait) {
            Some(Ok(status)) => status,
            _ => {
                let _ = self.stop();
                return Err("Cannot inspect Picard playback process; playback stopped".into());
            }
        };
        if let Some(status) = status {
            self.child = None;
            if !status.success() {
                let _ = self.stop();
                return Err("Audio player could not play the Picard excerpt; check your audio output or use picard link".into());
            }
            match self.spawn_child() {
                Ok(child) => self.child = Some(child),
                Err(e) => {
                    let _ = self.stop();
                    return Err(e);
                }
            }
        }
        Ok(true)
    }

    pub fn stop(&mut self) -> Result<(), String> {
        self.stopped = true;
        let result = if let Some(mut child) = self.child.take() {
            stop_child(&mut child)
        } else {
            Ok(())
        };
        self.listener = None;
        // Never delete a replacement socket belonging to a newer controller.
        if let Ok(Some(meta)) = socket_metadata(&self.socket_path)
            && (meta.dev(), meta.ino()) == self.socket_identity
        {
            let _ = fs::remove_file(&self.socket_path);
        }
        // Release explicitly, rather than only on fd close: another thread's
        // fork can briefly inherit a CLOEXEC descriptor before exec completes.
        // It must not keep a stopped controller's lock alive.
        unsafe {
            libc::flock(self._lock.as_raw_fd(), libc::LOCK_UN);
        }
        result
    }

    fn spawn_child(&self) -> Result<Child, String> {
        let mut cmd = clean_command(&self.backend.program, true);
        cmd.args(&self.backend.args)
            .arg(&self.audio)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        cmd.spawn().map_err(|_| {
            "Cannot launch an audio player; use picard link to open the original".to_string()
        })
    }
}

impl Drop for Player {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

fn stop_child(child: &mut Child) -> Result<(), String> {
    if child
        .try_wait()
        .map_err(|_| "Cannot inspect owned audio process")?
        .is_none()
    {
        // An unreaped child retains its PID; no persisted PID is ever signalled.
        if child.kill().is_err() && child.try_wait().ok().flatten().is_none() {
            return Err("Could not stop the owned audio process".into());
        }
    }
    child
        .wait()
        .map_err(|_| "Could not reap the owned audio process")?;
    Ok(())
}

/// A temporary foreground controller. No daemon, autostart, or PID file.
pub fn play_foreground(state_dir: &Path) -> Result<(), String> {
    let interrupted = Arc::new(AtomicBool::new(false));
    struct SignalGuard(Vec<signal_hook::SigId>);
    impl Drop for SignalGuard {
        fn drop(&mut self) {
            for id in self.0.drain(..) {
                signal_hook::low_level::unregister(id);
            }
        }
    }
    let mut signals = SignalGuard(Vec::new());
    for signal in [signal_hook::consts::SIGINT, signal_hook::consts::SIGTERM] {
        signals.0.push(
            signal_hook::flag::register(signal, Arc::clone(&interrupted))
                .map_err(|_| "Cannot install playback stop handler")?,
        );
    }
    let mut player = Player::start_cancellable(state_dir, || interrupted.load(Ordering::Relaxed))?;
    println!(
        "Playing the original Picard YTMND excerpt on repeat. Ctrl-C or `godmode picard stop` stops it."
    );
    while !interrupted.load(Ordering::Relaxed) && player.tick()? {
        std::thread::sleep(Duration::from_millis(50));
    }
    player.stop()
}

/// Ask a live controller to stop. Missing state is a no-op and creates nothing.
pub fn stop(state_dir: &Path) -> Result<bool, String> {
    let root = media_dir(state_dir)?;
    match fs::symlink_metadata(&root) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err("Cannot inspect Picard state".into()),
        Ok(_) => private_directory(&root)?,
    }
    let path = root.join(SOCKET_NAME);
    if socket_metadata(&path)?.is_none() {
        return Ok(false);
    }
    let mut stream = match UnixStream::connect(&path) {
        Ok(stream) => stream,
        Err(e)
            if matches!(
                e.kind(),
                std::io::ErrorKind::ConnectionRefused | std::io::ErrorKind::NotFound
            ) =>
        {
            return Ok(false);
        }
        Err(_) => return Err("Cannot contact Picard playback controller".into()),
    };
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|_| "Cannot configure Picard stop request")?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .map_err(|_| "Cannot configure Picard stop request")?;
    stream
        .write_all(b"STOP\n")
        .map_err(|_| "Cannot send Picard stop request")?;
    let mut response = [0u8; 3];
    stream
        .read_exact(&mut response)
        .map_err(|_| "Picard controller did not confirm stop; close its foreground session")?;
    if &response != b"OK\n" {
        return Err("Unexpected Picard controller response".into());
    }
    Ok(true)
}

pub fn open_source() -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let program = PathBuf::from("/usr/bin/open");
    #[cfg(not(target_os = "macos"))]
    let program =
        executable("xdg-open").ok_or("No browser opener found; visit https://picard.ytmnd.com/")?;
    let status = clean_command(&program, true)
        .arg(SOURCE_URL)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| "Cannot open the original; visit https://picard.ytmnd.com/")?;
    if !status.success() {
        return Err("Browser could not open the original; visit https://picard.ytmnd.com/".into());
    }
    Ok(())
}

fn media_dir(state: &Path) -> Result<PathBuf, String> {
    if state.components().any(|c| c == Component::ParentDir) {
        return Err("Use a state directory without parent traversal".into());
    }
    let absolute = if state.is_absolute() {
        state.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|_| "Cannot resolve Picard state directory")?
            .join(state)
    };
    Ok(absolute.join("picard"))
}

fn private_directory(path: &Path) -> Result<(), String> {
    let facts =
        crate::envfile::inspect(path, None).map_err(|_| "Cannot inspect Picard state directory")?;
    if facts.symlink_component.is_some() {
        return Err("Picard state path contains a symlink; refusing".into());
    }
    let meta = fs::symlink_metadata(path).map_err(|_| "Cannot inspect Picard state directory")?;
    if !meta.is_dir() || meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o777 != 0o700 {
        return Err("Picard state directory must be owned by you with mode 0700".into());
    }
    Ok(())
}

fn socket_metadata(path: &Path) -> Result<Option<fs::Metadata>, String> {
    match fs::symlink_metadata(path) {
        Ok(meta)
            if meta.file_type().is_socket()
                && meta.uid() == unsafe { libc::geteuid() }
                && meta.mode() & 0o777 == 0o600 =>
        {
            Ok(Some(meta))
        }
        Ok(_) => Err("Unsafe Picard control socket; refusing".into()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => Err("Cannot inspect Picard control socket".into()),
    }
}

fn valid_audio(bytes: &[u8]) -> bool {
    bytes.len() == AUDIO_BYTES && format!("{:x}", Sha256::digest(bytes)) == AUDIO_SHA256
}

fn cached_audio(
    root: &Path,
    player: &mut Player,
    cancel: &mut dyn FnMut() -> bool,
) -> Result<PathBuf, String> {
    if player.poll_cancel(cancel)? {
        return Err("Picard playback canceled".into());
    }
    let path = root.join(CACHE_NAME);
    let facts =
        crate::envfile::inspect(&path, None).map_err(|_| "Cannot inspect Picard audio cache")?;
    if facts.symlink_component.is_some() {
        return Err("Picard audio cache contains a symlink; refusing".into());
    }
    if facts.exists {
        if !facts.strict_ok() {
            return Err(
                "Picard audio cache must be an owned private regular file under 1 MiB".into(),
            );
        }
        let before =
            fs::symlink_metadata(&path).map_err(|_| "Cannot inspect Picard audio cache")?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
            .map_err(|_| "Cannot read Picard audio cache")?;
        let after = file
            .metadata()
            .map_err(|_| "Cannot inspect open Picard audio cache")?;
        if (before.dev(), before.ino()) != (after.dev(), after.ino()) {
            return Err("Picard audio cache changed; retry".into());
        }
        let mut bytes = Vec::new();
        file.take(MAX_DOWNLOAD + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "Cannot read Picard audio cache")?;
        if !valid_audio(&bytes) {
            return Err("Picard audio cache failed its source checksum; remove the Picard cache to download it again".into());
        }
        return Ok(path);
    }
    let curl = executable("curl")
        .ok_or("Picard playback needs curl to fetch its audio; use picard link")?;
    let child = clean_command(&curl, false)
        .args([
            "-q",
            "--fail",
            "--silent",
            "--proto",
            "=https",
            "--connect-timeout",
            "5",
            "--max-time",
            "20",
            "--max-filesize",
            "1048576",
            "--",
            AUDIO_URL,
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "Cannot fetch the Picard excerpt; use picard link")?;
    let bytes = download_bytes(child, player, cancel)?;
    if !valid_audio(&bytes) {
        return Err(
            "Downloaded audio did not match the original Picard excerpt; nothing cached".into(),
        );
    }
    let temp_path = root.join("download.part");
    // Under the held directory lock, a prior interrupted partial is safe to
    // remove only if it remains an owned private regular file.
    if let Ok(meta) = fs::symlink_metadata(&temp_path) {
        if !meta.is_file()
            || meta.uid() != unsafe { libc::geteuid() }
            || meta.mode() & 0o777 != 0o600
        {
            return Err("Unsafe partial Picard download; refusing".into());
        }
        fs::remove_file(&temp_path).map_err(|_| "Cannot clear interrupted Picard download")?;
    }
    struct Partial(PathBuf);
    impl Drop for Partial {
        fn drop(&mut self) {
            let _ = fs::remove_file(&self.0);
        }
    }
    let mut temp = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&temp_path)
        .map_err(|_| "Cannot create private Picard audio cache")?;
    let _partial = Partial(temp_path.clone());
    temp.set_permissions(fs::Permissions::from_mode(0o600))
        .map_err(|_| "Cannot make Picard audio cache private")?;
    temp.write_all(&bytes)
        .and_then(|_| temp.sync_all())
        .map_err(|_| "Cannot save Picard audio cache")?;
    fs::rename(&temp_path, &path).map_err(|_| "Cannot finish Picard audio cache")?;
    Ok(path)
}

// Nonblocking reads keep both the stop socket and foreground/UI cancellation
// responsive while a remote server is silent. The controller owns the curl child
// for the entire download, so stop also kills/reaps that exact process.
fn download_bytes(
    child: Child,
    player: &mut Player,
    cancel: &mut dyn FnMut() -> bool,
) -> Result<Vec<u8>, String> {
    player.child = Some(child);
    let mut output = player
        .child
        .as_mut()
        .and_then(|c| c.stdout.take())
        .ok_or("Cannot read audio download")?;
    let fd = output.as_raw_fd();
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        let _ = player.stop();
        return Err("Cannot configure cancelable audio download".into());
    }
    let deadline = Instant::now() + Duration::from_secs(25);
    let mut bytes = Vec::new();
    let mut buffer = [0u8; 8192];
    let mut eof = false;
    loop {
        if player.poll_cancel(cancel)? {
            return Err("Picard playback canceled".into());
        }
        if Instant::now() >= deadline {
            let _ = player.stop();
            return Err("Picard audio download timed out".into());
        }
        if !eof {
            match output.read(&mut buffer) {
                Ok(0) => eof = true,
                Ok(count) => {
                    if bytes.len() as u64 + count as u64 > MAX_DOWNLOAD {
                        let _ = player.stop();
                        return Err("Picard audio download exceeded 1 MiB".into());
                    }
                    bytes.extend_from_slice(&buffer[..count]);
                    continue;
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::WouldBlock | std::io::ErrorKind::Interrupted
                    ) => {}
                Err(_) => {
                    let _ = player.stop();
                    return Err("Cannot read Picard audio download".into());
                }
            }
        }
        if eof {
            match player.child.as_mut().map(Child::try_wait) {
                Some(Ok(Some(status))) => {
                    player.child = None;
                    if !status.success() {
                        return Err("Could not fetch the original Picard audio; use picard link or try again later".into());
                    }
                    return Ok(bytes);
                }
                Some(Ok(None)) => (),
                _ => {
                    let _ = player.stop();
                    return Err("Cannot finish Picard audio download".into());
                }
            }
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn executable(name: &str) -> Option<PathBuf> {
    std::env::var_os("PATH").and_then(|path| {
        std::env::split_paths(&path)
            .filter(|dir| dir.is_absolute())
            .map(|dir| dir.join(name))
            .find(|candidate| {
                fs::metadata(candidate).is_ok_and(|m| m.is_file() && m.mode() & 0o111 != 0)
            })
    })
}

fn find_backend() -> Result<Backend, String> {
    #[cfg(target_os = "macos")]
    if Path::new("/usr/bin/afplay").is_file() {
        return Ok(Backend {
            program: PathBuf::from("/usr/bin/afplay"),
            args: vec!["-v", "0.5"],
        });
    }
    for (name, args) in [
        ("paplay", vec!["--volume=32768"]),
        ("aplay", vec!["-q"]),
        (
            "ffplay",
            vec![
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-volume",
                "50",
            ],
        ),
        (
            "mpv",
            vec![
                "--no-config",
                "--no-video",
                "--no-terminal",
                "--input-terminal=no",
                "--volume=50",
            ],
        ),
    ] {
        if let Some(program) = executable(name) {
            return Ok(Backend { program, args });
        }
    }
    Err("No audio player found. macOS uses afplay; Linux needs paplay, aplay, ffplay, or mpv. Use picard link instead.".into())
}

fn clean_command(program: &Path, desktop: bool) -> Command {
    let mut command = Command::new(program);
    command.env_clear();
    for key in [
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
    ] {
        if let Some(value) = std::env::var_os(key) {
            command.env(key, value);
        }
    }
    if desktop {
        for key in [
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "DBUS_SESSION_BUS_ADDRESS",
            "PULSE_SERVER",
            "PULSE_COOKIE",
            "XDG_CURRENT_DESKTOP",
        ] {
            if let Some(value) = std::env::var_os(key) {
                command.env(key, value);
            }
        }
    }
    command
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp() -> tempfile::TempDir {
        // Keep below the macOS Unix-domain-socket path length limit.
        #[cfg(target_os = "macos")]
        let base = "/private/tmp";
        #[cfg(not(target_os = "macos"))]
        let base = "/tmp";
        tempfile::Builder::new()
            .prefix("gm-picard-")
            .tempdir_in(base)
            .unwrap()
    }

    fn silent_player(root: &Path) -> Player {
        crate::store::private_dir(root).unwrap();
        let lock = crate::envfile::lock_directory(root).unwrap();
        Player::start_owned(
            root.to_path_buf(),
            PathBuf::from("30"),
            Backend {
                program: PathBuf::from("/bin/sleep"),
                args: vec![],
            },
            lock,
        )
        .unwrap()
    }

    #[test]
    fn stop_when_absent_does_not_create_state() {
        let tmp = temp();
        let state = tmp.path().join("absent");
        assert!(!stop(&state).unwrap());
        assert!(!state.exists());
    }

    #[test]
    fn socket_stops_only_owned_child_and_cleanup_releases_lock() {
        let tmp = temp();
        let root = tmp.path().join("picard");
        let mut unrelated = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let mut player = silent_player(&root);
        assert!(crate::envfile::lock_directory(&root).is_err());
        let state = tmp.path().to_path_buf();
        let request = std::thread::spawn(move || stop(&state));
        for _ in 0..40 {
            if !player.tick().unwrap() {
                break;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(request.join().unwrap().unwrap());
        assert!(player.stopped);
        assert!(unrelated.try_wait().unwrap().is_none());
        assert!(!root.join(SOCKET_NAME).exists());
        stop_child(&mut unrelated).unwrap();
        drop(player);
        assert!(crate::envfile::lock_directory(&root).is_ok());
    }

    #[test]
    fn dropping_player_stops_child_and_removes_socket() {
        let tmp = temp();
        let root = tmp.path().join("picard");
        let player = silent_player(&root);
        // Models a descriptor inherited between fork and exec in another thread.
        let _inherited = player._lock.try_clone().unwrap();
        drop(player);
        assert!(!root.join(SOCKET_NAME).exists());
        assert!(crate::envfile::lock_directory(&root).is_ok());
    }

    #[test]
    fn malformed_cache_and_control_path_are_refused_without_network() {
        let tmp = temp();
        let root = tmp.path().join("picard");
        crate::store::private_dir(&root).unwrap();
        let cache = root.join(CACHE_NAME);
        fs::write(&cache, b"not audio").unwrap();
        fs::set_permissions(&cache, fs::Permissions::from_mode(0o600)).unwrap();
        let lock = crate::envfile::lock_directory(&root).unwrap();
        let mut controller = Player::controller(
            root.clone(),
            cache,
            Backend {
                program: PathBuf::from("/bin/sleep"),
                args: vec![],
            },
            lock,
        )
        .unwrap();
        assert!(
            cached_audio(&root, &mut controller, &mut || false)
                .unwrap_err()
                .contains("checksum")
        );
        drop(controller);
        let control = root.join(SOCKET_NAME);
        fs::write(&control, b"not a socket").unwrap();
        assert!(stop(tmp.path()).is_err());
        assert_eq!(fs::read(&control).unwrap(), b"not a socket");
    }

    #[test]
    fn state_symlink_is_refused_and_never_removed() {
        let tmp = temp();
        let target = tmp.path().join("target");
        fs::create_dir(&target).unwrap();
        std::os::unix::fs::symlink(&target, tmp.path().join("picard")).unwrap();
        assert!(stop(tmp.path()).is_err());
        assert!(tmp.path().join("picard").is_symlink());
    }

    fn download_controller(root: &Path) -> Player {
        crate::store::private_dir(root).unwrap();
        let lock = crate::envfile::lock_directory(root).unwrap();
        Player::controller(
            root.to_path_buf(),
            root.join(CACHE_NAME),
            Backend {
                program: PathBuf::from("/bin/sleep"),
                args: vec![],
            },
            lock,
        )
        .unwrap()
    }

    fn blocked_download() -> Child {
        Command::new("/bin/sleep")
            .arg("30")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap()
    }

    #[test]
    fn external_stop_cancels_blocked_download_before_playback() {
        let tmp = temp();
        let root = tmp.path().join("picard");
        let mut controller = download_controller(&root);
        let mut unrelated = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let download = blocked_download();
        let state = tmp.path().to_path_buf();
        let request = std::thread::spawn(move || stop(&state));
        let started = Instant::now();
        assert_eq!(
            download_bytes(download, &mut controller, &mut || false).unwrap_err(),
            "Picard playback canceled"
        );
        assert!(request.join().unwrap().unwrap());
        assert!(started.elapsed() < Duration::from_secs(2));
        assert!(controller.stopped);
        assert!(controller.child.is_none());
        assert!(!root.join(CACHE_NAME).exists());
        assert!(!root.join(SOCKET_NAME).exists());
        assert!(unrelated.try_wait().unwrap().is_none());
        stop_child(&mut unrelated).unwrap();
    }

    #[test]
    fn local_cancel_cancels_blocked_download_without_network_or_audio() {
        let tmp = temp();
        let root = tmp.path().join("picard");
        let mut controller = download_controller(&root);
        let download = blocked_download();
        let mut polls = 0;
        let mut cancel = || {
            polls += 1;
            polls >= 3
        };
        let started = Instant::now();
        assert_eq!(
            download_bytes(download, &mut controller, &mut cancel).unwrap_err(),
            "Picard playback canceled"
        );
        assert!(started.elapsed() < Duration::from_secs(2));
        assert!(controller.stopped);
        assert!(controller.child.is_none());
        assert!(!root.join(CACHE_NAME).exists());
        assert!(!root.join(SOCKET_NAME).exists());
    }

    #[test]
    fn cancel_before_start_does_not_create_state() {
        let tmp = temp();
        let state = tmp.path().join("absent");
        assert!(Player::start_cancellable(&state, || true).is_err());
        assert!(!state.exists());
    }

    #[test]
    fn media_checksum_rejects_even_plausible_wav_header() {
        let mut fake = vec![0u8; AUDIO_BYTES];
        fake[..12].copy_from_slice(b"RIFFxxxxWAVE");
        assert!(!valid_audio(&fake));
    }
}
