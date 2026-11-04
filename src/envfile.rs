//! Byte-preserving, non-executing reader and atomic writer for the one credential file.
//! Values are never included in diagnostics. Files must be owned regular files,
//! mode 0600, at most 1 MiB. Directory descriptors prevent symlink traversal.

use std::ffi::CString;
use std::fmt;
use std::fs::{self, File, Metadata};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use zeroize::{Zeroize, Zeroizing};

pub const MAX_SIZE: u64 = 1_048_576;
pub const NEW_FILE_HEADER: &str = "# Godmode credential inventory. One KEY=value per line, mode 0600.\n# Managed by `godmode`; never commit, print, or copy this file.\n";

#[derive(Clone, PartialEq, Eq)]
pub enum Line {
    Blank(String),
    Comment(String),
    Assignment {
        prefix: String,
        key: String,
        pre_eq: String,
        raw_value: String,
        comment: Option<String>,
    },
    Opaque(String),
}

impl Line {
    pub fn redacted(&self) -> String {
        match self {
            Self::Blank(_) => "blank".into(),
            Self::Comment(_) => "comment".into(),
            Self::Assignment { key, .. } => format!("assignment {key}"),
            Self::Opaque(_) => "unparseable line".into(),
        }
    }
}

impl fmt::Debug for Line {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.redacted())
    }
}

impl Drop for Line {
    fn drop(&mut self) {
        match self {
            Self::Blank(s) | Self::Comment(s) | Self::Opaque(s) => s.zeroize(),
            Self::Assignment {
                raw_value, comment, ..
            } => {
                raw_value.zeroize();
                if let Some(s) = comment {
                    s.zeroize();
                }
            }
        }
    }
}

pub enum Lookup {
    Absent,
    Blank,
    Present(Zeroizing<String>),
    Duplicate(usize),
    Malformed(&'static str),
}

impl fmt::Debug for Lookup {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Absent => f.write_str("Absent"),
            Self::Blank => f.write_str("Blank"),
            Self::Present(_) => f.write_str("Present([REDACTED])"),
            Self::Duplicate(n) => write!(f, "Duplicate({n})"),
            Self::Malformed(reason) => write!(f, "Malformed({reason})"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SetOutcome {
    Created,
    Replaced,
    ReplacedAndDeduplicated(usize),
}

#[derive(Debug, Clone)]
pub struct EnvFile {
    lines: Vec<Line>,
    endings: Vec<&'static str>,
    newline: &'static str,
}

impl EnvFile {
    pub fn parse(text: &str) -> Self {
        let mut lines = Vec::new();
        let mut endings = Vec::new();
        for segment in text.split_inclusive('\n') {
            let (raw, ending) = if let Some(raw) = segment.strip_suffix("\r\n") {
                (raw, "\r\n")
            } else if let Some(raw) = segment.strip_suffix('\n') {
                (raw, "\n")
            } else {
                (segment, "")
            };
            lines.push(parse_line(raw));
            endings.push(ending);
        }
        let crlf = endings.iter().filter(|e| **e == "\r\n").count();
        let lf = endings.iter().filter(|e| **e == "\n").count();
        Self {
            lines,
            endings,
            newline: if crlf > lf { "\r\n" } else { "\n" },
        }
    }

    pub fn empty() -> Self {
        Self {
            lines: Vec::new(),
            endings: Vec::new(),
            newline: "\n",
        }
    }

    /// Returned text contains secrets; callers should wrap it in `Zeroizing`.
    pub fn render(&self) -> String {
        let mut output = String::new();
        for (line, ending) in self.lines.iter().zip(&self.endings) {
            match line {
                Line::Blank(s) | Line::Comment(s) | Line::Opaque(s) => output.push_str(s),
                Line::Assignment {
                    prefix,
                    key,
                    pre_eq,
                    raw_value,
                    comment,
                } => {
                    output.push_str(prefix);
                    output.push_str(key);
                    output.push_str(pre_eq);
                    output.push('=');
                    output.push_str(raw_value);
                    if let Some(comment) = comment {
                        output.push_str(comment);
                    }
                }
            }
            output.push_str(ending);
        }
        output
    }

    pub fn lines(&self) -> &[Line] {
        &self.lines
    }

    pub fn keys(&self) -> Vec<&str> {
        self.lines
            .iter()
            .filter_map(|l| match l {
                Line::Assignment { key, .. } => Some(key.as_str()),
                _ => None,
            })
            .collect()
    }

    pub fn get(&self, key: &str) -> Lookup {
        let matching: Vec<_> = self
            .lines
            .iter()
            .filter_map(|line| match line {
                Line::Assignment {
                    key: k, raw_value, ..
                } if k == key => Some(raw_value),
                _ => None,
            })
            .collect();
        if matching.is_empty() {
            return Lookup::Absent;
        }
        if matching.len() > 1 {
            return Lookup::Duplicate(matching.len());
        }
        match shlex_split(matching[0]) {
            Ok(mut parts) if parts.len() == 1 => {
                let value = Zeroizing::new(parts.remove(0));
                if value.is_empty() {
                    Lookup::Blank
                } else if value.contains(['\r', '\n', '\0', '\u{2028}', '\u{2029}']) {
                    Lookup::Malformed("control character")
                } else {
                    Lookup::Present(value)
                }
            }
            Ok(mut parts) => {
                let empty = parts.is_empty();
                parts.zeroize();
                if empty {
                    Lookup::Blank
                } else {
                    Lookup::Malformed("expected one value")
                }
            }
            Err(_) => Lookup::Malformed("invalid quoting"),
        }
    }

    pub fn set(
        &mut self,
        key: &str,
        value: &str,
        section: Option<&str>,
    ) -> Result<SetOutcome, EnvError> {
        if !is_valid_key(key) {
            return Err(EnvError::InvalidKey(key.into()));
        }
        let forbidden = |c: char| c.is_control() || matches!(c, '\u{2028}' | '\u{2029}');
        if value.chars().any(forbidden) || section.is_some_and(|s| s.chars().any(forbidden)) {
            return Err(EnvError::ControlCharacter);
        }
        let mut first = None;
        let mut removed = 0;
        let mut index = 0;
        while index < self.lines.len() {
            if matches!(&self.lines[index], Line::Assignment { key: k, .. } if k == key) {
                if first.is_some() {
                    self.lines.remove(index);
                    self.endings.remove(index);
                    removed += 1;
                    continue;
                }
                first = Some(index);
            }
            index += 1;
        }
        if let Some(index) = first {
            if let Line::Assignment {
                raw_value, comment, ..
            } = &mut self.lines[index]
            {
                let leading =
                    raw_value[..raw_value.len() - raw_value.trim_start().len()].to_owned();
                let trailing = if raw_value.trim().is_empty() {
                    String::new()
                } else {
                    raw_value[raw_value.trim_end().len()..].to_owned()
                };
                raw_value.zeroize();
                // The legacy Google reader interprets unquoted values literally,
                // including inline comments. Force quotation when retaining one.
                if let Some(comment) = comment
                    && comment.starts_with('#')
                {
                    comment.insert(0, ' ');
                }
                let replacement = Zeroizing::new(if comment.is_some() {
                    single_quote(value)
                } else {
                    quote_value(value)
                });
                *raw_value = format!("{leading}{}{trailing}", &*replacement);
            }
            return Ok(if removed == 0 {
                SetOutcome::Replaced
            } else {
                SetOutcome::ReplacedAndDeduplicated(removed)
            });
        }
        if let Some(section) = section {
            let heading = format!("# {section}");
            if !self
                .lines
                .iter()
                .any(|line| matches!(line, Line::Comment(s) if s == &heading))
            {
                self.append(Line::Comment(heading));
            }
        }
        self.append(Line::Assignment {
            prefix: String::new(),
            key: key.into(),
            pre_eq: String::new(),
            raw_value: quote_value(value),
            comment: None,
        });
        Ok(SetOutcome::Created)
    }

    fn append(&mut self, line: Line) {
        if let Some(last) = self.endings.last_mut()
            && last.is_empty()
        {
            *last = self.newline;
        }
        self.lines.push(line);
        self.endings.push(self.newline);
    }

    pub fn unset(&mut self, key: &str) -> usize {
        let mut removed = 0;
        let mut i = 0;
        while i < self.lines.len() {
            if matches!(&self.lines[i], Line::Assignment { key: k, .. } if k == key) {
                self.lines.remove(i);
                self.endings.remove(i);
                removed += 1;
            } else {
                i += 1;
            }
        }
        removed
    }
}

fn parse_line(raw: &str) -> Line {
    let trimmed = raw.trim_start();
    if trimmed.is_empty() {
        return Line::Blank(raw.into());
    }
    if trimmed.starts_with('#') {
        return Line::Comment(raw.into());
    }
    let mut start = raw.len() - trimmed.len();
    if let Some(rest) = trimmed.strip_prefix("export")
        && rest.starts_with(char::is_whitespace)
    {
        start = raw.len() - rest.trim_start().len();
    }
    let Some(eq) = raw[start..].find('=').map(|n| start + n) else {
        return Line::Opaque(raw.into());
    };
    let key = raw[start..eq].trim_end();
    if !is_valid_key(key) {
        return Line::Opaque(raw.into());
    }
    let value = &raw[eq + 1..];
    let (raw_value, comment) = match comment_start(value) {
        Some(mut pos) => {
            while pos > 0 && matches!(value.as_bytes()[pos - 1], b' ' | b'\t') {
                // An escaped space is part of the value, not the comment gap.
                let slashes = value.as_bytes()[..pos - 1]
                    .iter()
                    .rev()
                    .take_while(|b| **b == b'\\')
                    .count();
                if slashes % 2 == 1 {
                    break;
                }
                pos -= 1;
            }
            (value[..pos].into(), Some(value[pos..].into()))
        }
        None => (value.into(), None),
    };
    Line::Assignment {
        prefix: raw[..start].into(),
        key: key.into(),
        pre_eq: raw[start + key.len()..eq].into(),
        raw_value,
        comment,
    }
}

fn comment_start(raw: &str) -> Option<usize> {
    let mut quote = None;
    let mut escaped = false;
    for (i, c) in raw.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        match quote {
            Some('\'') => {
                if c == '\'' {
                    quote = None;
                }
            }
            Some('"') => {
                if c == '"' {
                    quote = None;
                } else if c == '\\' {
                    escaped = true;
                }
            }
            _ => match c {
                '\'' | '"' => quote = Some(c),
                '\\' => escaped = true,
                '#' => return Some(i),
                _ => (),
            },
        }
    }
    None
}

pub fn is_valid_key(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some(c) if c == '_' || c.is_ascii_alphabetic())
        && chars.all(|c| c == '_' || c.is_ascii_alphanumeric())
}

fn single_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

pub fn quote_value(value: &str) -> String {
    if !value.is_empty()
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_.:/@+=-".contains(&b))
    {
        value.into()
    } else {
        single_quote(value)
    }
}

/// Python `shlex.split(raw, comments=True, posix=True)`, without execution.
pub fn shlex_split(raw: &str) -> Result<Vec<String>, ShlexError> {
    #[derive(Clone, Copy)]
    enum State {
        Space,
        Word,
        Single,
        Double,
    }
    let mut state = State::Space;
    let mut token = Zeroizing::new(String::new());
    let mut tokens = Zeroizing::new(Vec::new());
    let mut chars = raw.chars();
    while let Some(c) = chars.next() {
        match state {
            State::Single => {
                if c == '\'' {
                    state = State::Word;
                } else {
                    token.push(c);
                }
            }
            State::Double => match c {
                '"' => state = State::Word,
                '\\' => {
                    let next = chars.next().ok_or(ShlexError::NoEscapedCharacter)?;
                    if next != '"' && next != '\\' {
                        token.push('\\');
                    }
                    token.push(next);
                }
                _ => token.push(c),
            },
            State::Space | State::Word => match c {
                ' ' | '\t' | '\r' | '\n' => {
                    if matches!(state, State::Word) {
                        tokens.push(std::mem::take(&mut *token));
                    }
                    state = State::Space;
                }
                '#' => {
                    for c in chars.by_ref() {
                        if c == '\n' {
                            break;
                        }
                    }
                    if matches!(state, State::Word) {
                        tokens.push(std::mem::take(&mut *token));
                    }
                    state = State::Space;
                }
                '\'' => state = State::Single,
                '"' => state = State::Double,
                '\\' => {
                    token.push(chars.next().ok_or(ShlexError::NoEscapedCharacter)?);
                    state = State::Word;
                }
                _ => {
                    token.push(c);
                    state = State::Word;
                }
            },
        }
    }
    match state {
        State::Single | State::Double => return Err(ShlexError::NoClosingQuotation),
        State::Word => tokens.push(std::mem::take(&mut *token)),
        State::Space => (),
    }
    Ok(std::mem::take(&mut *tokens))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShlexError {
    NoClosingQuotation,
    NoEscapedCharacter,
}
impl fmt::Display for ShlexError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::NoClosingQuotation => "No closing quotation",
            Self::NoEscapedCharacter => "No escaped character",
        })
    }
}

#[derive(Debug, Clone, Default)]
pub struct FileFacts {
    pub exists: bool,
    pub regular: bool,
    pub owned: bool,
    pub mode: Option<u32>,
    pub size: Option<u64>,
    pub symlink_component: Option<PathBuf>,
}
impl FileFacts {
    pub fn strict_ok(&self) -> bool {
        self.exists
            && self.regular
            && self.owned
            && self.mode == Some(0o600)
            && self.size.is_some_and(|s| s <= MAX_SIZE)
            && self.symlink_component.is_none()
    }
}

fn io(context: &'static str, path: &Path, source: std::io::Error) -> EnvError {
    EnvError::Io {
        context,
        path: path.into(),
        source,
    }
}

fn absolute(path: &Path) -> Result<PathBuf, EnvError> {
    if path.components().any(|c| c == Component::ParentDir) {
        return Err(io(
            "parent traversal is not allowed in",
            path,
            std::io::Error::from(std::io::ErrorKind::InvalidInput),
        ));
    }
    if path.is_absolute() {
        Ok(path.into())
    } else {
        std::env::current_dir()
            .map(|p| p.join(path))
            .map_err(|e| io("resolve", path, e))
    }
}

pub fn inspect(path: &Path, stop_at: Option<&Path>) -> Result<FileFacts, EnvError> {
    let full = absolute(path)?;
    let mut walked = PathBuf::new();
    for component in full.components() {
        walked.push(component);
        if stop_at.is_some_and(|stop| stop.starts_with(&walked)) {
            continue;
        }
        match fs::symlink_metadata(&walked) {
            Ok(meta) if meta.file_type().is_symlink() => {
                return Ok(FileFacts {
                    symlink_component: Some(walked),
                    ..Default::default()
                });
            }
            Ok(_) => (),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(FileFacts::default()),
            Err(e) => return Err(io("inspect", &walked, e)),
        }
    }
    let meta = fs::symlink_metadata(&full).map_err(|e| io("inspect", path, e))?;
    Ok(facts(&meta))
}

fn facts(meta: &Metadata) -> FileFacts {
    FileFacts {
        exists: true,
        regular: meta.is_file(),
        owned: meta.uid() == unsafe { libc::geteuid() },
        mode: Some(meta.mode() & 0o7777),
        size: Some(meta.len()),
        symlink_component: None,
    }
}
fn validate(meta: &Metadata, path: &Path, strict: bool) -> Result<(), EnvError> {
    if meta.file_type().is_symlink() {
        return Err(EnvError::Symlink(path.into()));
    }
    if !meta.is_file() {
        return Err(EnvError::NotRegular(path.into()));
    }
    if meta.uid() != unsafe { libc::geteuid() } {
        return Err(EnvError::NotOwned(path.into()));
    }
    if strict && meta.mode() & 0o7777 != 0o600 {
        return Err(EnvError::BadMode(path.into(), meta.mode() & 0o7777));
    }
    if meta.len() > MAX_SIZE {
        return Err(EnvError::TooLarge(path.into(), meta.len()));
    }
    Ok(())
}
fn cname(name: &std::ffi::OsStr, path: &Path) -> Result<CString, EnvError> {
    CString::new(name.as_bytes()).map_err(|_| {
        io(
            "invalid path",
            path,
            std::io::Error::from(std::io::ErrorKind::InvalidInput),
        )
    })
}

/// Open every directory component relative to the preceding descriptor.
/// A concurrently replaced directory cannot redirect a file operation.
fn directory(path: &Path, stop_at: Option<&Path>) -> Result<File, EnvError> {
    let full = absolute(path)?;
    let start = stop_at
        .filter(|p| full.starts_with(p))
        .unwrap_or(Path::new("/"));
    let mut dir = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(start)
        .map_err(|e| io("open directory", start, e))?;
    let mut walked = start.to_path_buf();
    for part in full
        .strip_prefix(start)
        .map_err(|_| EnvError::Raced(path.into()))?
        .components()
    {
        if part == Component::CurDir {
            continue;
        }
        walked.push(part);
        let name = cname(part.as_os_str(), &walked)?;
        let fd = unsafe {
            libc::openat(
                dir.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io(
                "open directory without symlinks",
                &walked,
                std::io::Error::last_os_error(),
            ));
        }
        dir = unsafe { File::from_raw_fd(fd) };
    }
    Ok(dir)
}
/// A destination-inode lock shared by all CLI instances, regardless of their
/// acknowledgement/state directory. Holding the returned descriptor holds the lock.
pub fn lock_directory(path: &Path) -> Result<File, EnvError> {
    let dir = directory(path, None)?;
    let meta = dir
        .metadata()
        .map_err(|e| io("inspect lock directory", path, e))?;
    if meta.uid() != unsafe { libc::geteuid() } {
        return Err(EnvError::NotOwned(path.into()));
    }
    if meta.mode() & 0o022 != 0 {
        return Err(io(
            "directory must not be group/world writable",
            path,
            std::io::Error::from(std::io::ErrorKind::PermissionDenied),
        ));
    }
    if unsafe { libc::flock(dir.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io(
            "another writer may be active; cannot lock directory",
            path,
            std::io::Error::last_os_error(),
        ));
    }
    Ok(dir)
}

fn parent(path: &Path, stop_at: Option<&Path>) -> Result<(File, CString), EnvError> {
    let full = absolute(path)?;
    let dir = full
        .parent()
        .ok_or_else(|| EnvError::NotRegular(path.into()))?;
    let name = full
        .file_name()
        .ok_or_else(|| EnvError::NotRegular(path.into()))?;
    Ok((directory(dir, stop_at)?, cname(name, path)?))
}
fn open_at(dir: &File, name: &CString, flags: i32, path: &Path) -> Result<File, EnvError> {
    let fd = unsafe {
        libc::openat(
            dir.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            0o600,
        )
    };
    if fd < 0 {
        Err(io("open", path, std::io::Error::last_os_error()))
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}

pub struct ReadResult {
    pub file: EnvFile,
    pub facts: FileFacts,
}

pub fn read(path: &Path, stop_at: Option<&Path>, strict: bool) -> Result<ReadResult, EnvError> {
    let pre = inspect(path, stop_at)?;
    if let Some(link) = pre.symlink_component {
        return Err(EnvError::Symlink(link));
    }
    let before = fs::symlink_metadata(path).map_err(|e| io("inspect", path, e))?;
    validate(&before, path, strict)?;
    let (dir, name) = parent(path, stop_at)?;
    let file = open_at(&dir, &name, libc::O_RDONLY, path)?;
    let meta = file
        .metadata()
        .map_err(|e| io("inspect open file", path, e))?;
    validate(&meta, path, strict)?;
    if (meta.dev(), meta.ino()) != (before.dev(), before.ino()) {
        return Err(EnvError::Raced(path.into()));
    }
    let mut bytes = Zeroizing::new(Vec::new());
    file.take(MAX_SIZE + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| io("read", path, e))?;
    if bytes.len() as u64 > MAX_SIZE {
        return Err(EnvError::TooLarge(path.into(), bytes.len() as u64));
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| EnvError::NotUtf8(path.into()))?;
    Ok(ReadResult {
        file: EnvFile::parse(text),
        facts: facts(&meta),
    })
}

struct TempGuard<'a> {
    dir: &'a File,
    name: CString,
}
impl Drop for TempGuard<'_> {
    fn drop(&mut self) {
        unsafe {
            libc::unlinkat(self.dir.as_raw_fd(), self.name.as_ptr(), 0);
        }
    }
}
static TEMP_ID: AtomicU64 = AtomicU64::new(0);

pub fn write_atomic(path: &Path, content: &str, tmp_dir: Option<&Path>) -> Result<(), EnvError> {
    if content.len() as u64 > MAX_SIZE {
        return Err(EnvError::TooLarge(path.into(), content.len() as u64));
    }
    let pre = inspect(path, None)?;
    if let Some(link) = pre.symlink_component {
        return Err(EnvError::Symlink(link));
    }
    if pre.exists {
        validate(
            &fs::symlink_metadata(path).map_err(|e| io("inspect", path, e))?,
            path,
            true,
        )?;
    }
    let (dest_dir, dest_name) = parent(path, None)?;
    let temp_dir = if let Some(temp) = tmp_dir {
        directory(temp, None)?
    } else {
        dest_dir
            .try_clone()
            .map_err(|e| io("duplicate directory", path, e))?
    };
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temp_name = CString::new(format!(
        ".env.godmode.{}.{}.{}.tmp",
        std::process::id(),
        nonce,
        TEMP_ID.fetch_add(1, Ordering::Relaxed)
    ))
    .expect("generated ASCII filename");
    let guard = TempGuard {
        dir: &temp_dir,
        name: temp_name,
    };
    let mut temp = open_at(
        &temp_dir,
        &guard.name,
        libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
        path,
    )?;
    temp.set_permissions(fs::Permissions::from_mode(0o600))
        .map_err(|e| io("set private permissions", path, e))?;
    temp.write_all(content.as_bytes())
        .map_err(|e| io("write temporary file for", path, e))?;
    temp.sync_all()
        .map_err(|e| io("sync temporary file for", path, e))?;
    // Recheck immediately before commit; cooperative callers also hold a lock.
    let now = inspect(path, None)?;
    if let Some(link) = now.symlink_component {
        return Err(EnvError::Symlink(link));
    }
    if now.exists {
        validate(
            &fs::symlink_metadata(path).map_err(|e| io("inspect", path, e))?,
            path,
            true,
        )?;
    }
    let result = unsafe {
        libc::renameat(
            temp_dir.as_raw_fd(),
            guard.name.as_ptr(),
            dest_dir.as_raw_fd(),
            dest_name.as_ptr(),
        )
    };
    if result < 0 {
        let error = std::io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::EXDEV) && tmp_dir.is_some() {
            drop(temp);
            drop(guard);
            return write_atomic(path, content, None);
        }
        return Err(io("replace", path, error));
    }
    dest_dir
        .sync_all()
        .map_err(|e| io("sync directory for", path, e))?;
    let final_file = open_at(&dest_dir, &dest_name, libc::O_RDONLY, path)?;
    let meta = final_file.metadata().map_err(|e| io("verify", path, e))?;
    validate(&meta, path, true)?;
    Ok(())
}

pub fn create_empty(path: &Path) -> Result<bool, EnvError> {
    let pre = inspect(path, None)?;
    if let Some(link) = pre.symlink_component {
        return Err(EnvError::Symlink(link));
    }
    if pre.exists {
        validate(
            &fs::symlink_metadata(path).map_err(|e| io("inspect", path, e))?,
            path,
            true,
        )?;
        return Ok(false);
    }
    let (dir, name) = parent(path, None)?;
    let mut file = match open_at(
        &dir,
        &name,
        libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
        path,
    ) {
        Ok(file) => file,
        Err(EnvError::Io { source, .. }) if source.kind() == std::io::ErrorKind::AlreadyExists => {
            // A racing creator gets the same validation as an existing file.
            read(path, None, true)?;
            return Ok(false);
        }
        Err(e) => return Err(e),
    };
    file.set_permissions(fs::Permissions::from_mode(0o600))
        .map_err(|e| io("set private permissions", path, e))?;
    file.write_all(NEW_FILE_HEADER.as_bytes())
        .map_err(|e| io("initialize", path, e))?;
    file.sync_all().map_err(|e| io("sync", path, e))?;
    dir.sync_all()
        .map_err(|e| io("sync directory for", path, e))?;
    Ok(true)
}

pub enum EnvError {
    Symlink(PathBuf),
    NotRegular(PathBuf),
    NotOwned(PathBuf),
    BadMode(PathBuf, u32),
    TooLarge(PathBuf, u64),
    NotUtf8(PathBuf),
    InvalidKey(String),
    ControlCharacter,
    Raced(PathBuf),
    Io {
        context: &'static str,
        path: PathBuf,
        source: std::io::Error,
    },
}
impl fmt::Display for EnvError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Symlink(p) => write!(f, "{} is or contains a symlink; refusing", p.display()),
            Self::NotRegular(p) => write!(f, "{} is not a regular file", p.display()),
            Self::NotOwned(p) => write!(f, "{} is not owned by the current user", p.display()),
            Self::BadMode(p, m) => write!(
                f,
                "{} has mode {m:04o}; it must be 0600 (chmod 600)",
                p.display()
            ),
            Self::TooLarge(p, s) => write!(
                f,
                "{} is {s} bytes; readers refuse files over {MAX_SIZE} bytes",
                p.display()
            ),
            Self::NotUtf8(p) => write!(f, "{} is not valid UTF-8", p.display()),
            Self::InvalidKey(_) => f.write_str("invalid key name; expected [A-Za-z_][A-Za-z0-9_]*"),
            Self::ControlCharacter => {
                f.write_str("value or section contains a control character; refusing")
            }
            Self::Raced(p) => write!(
                f,
                "{} changed while it was being opened; retry",
                p.display()
            ),
            Self::Io {
                context,
                path,
                source,
            } => write!(f, "{context} {}: {source}", path.display()),
        }
    }
}
impl fmt::Debug for EnvError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        fmt::Display::fmt(self, f)
    }
}
impl std::error::Error for EnvError {}
