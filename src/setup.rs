//! A small question-and-answer setup flow. Secrets never become terminal text.
use std::{
    io::{self, IsTerminal, Write},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};

use ratatui::crossterm::{
    event::{
        self, DisableBracketedPaste, EnableBracketedPaste, Event, KeyCode, KeyEventKind,
        KeyModifiers,
    },
    execute, terminal,
};
use zeroize::{Zeroize, Zeroizing};

use crate::{
    Store,
    envfile::Lookup,
    output::{Tone, paint},
    registry::{Provider, Registry},
    store::{DISCLAIMER, FIRST_RUN_NOTICE},
};

const CANCELLED: &str = "Setup cancelled. Previously saved keys were kept.";

enum Prompt {
    Choice(Vec<String>),
    Secret,
}

trait Console {
    fn line(&mut self, text: &str) -> Result<(), String>;
    fn styled(&mut self, text: &str, _tone: Tone) -> Result<(), String> {
        self.line(text)
    }
    fn spans(&mut self, spans: &[(&str, Option<Tone>)]) -> Result<(), String> {
        self.line(&spans.iter().map(|(text, _)| *text).collect::<String>())
    }
    fn prompt(&mut self, label: &str, kind: Prompt) -> Result<Zeroizing<String>, String>;
    fn open(&mut self, url: &str) -> Result<(), String>;
}

struct TerminalConsole {
    interrupted: Arc<AtomicBool>,
    signals: Vec<signal_hook::SigId>,
}

impl TerminalConsole {
    fn start() -> Result<Self, String> {
        if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
            return Err("Setup needs a terminal. For scripts, use `init --accept-disclaimer` and `set --stdin`.".into());
        }
        terminal::enable_raw_mode().map_err(|_| "Could not prepare terminal input")?;
        let mut console = Self {
            interrupted: Arc::new(AtomicBool::new(false)),
            signals: Vec::new(),
        };
        for signal in [
            signal_hook::consts::SIGINT,
            signal_hook::consts::SIGTERM,
            signal_hook::consts::SIGHUP,
        ] {
            console.signals.push(
                signal_hook::flag::register(signal, Arc::clone(&console.interrupted))
                    .map_err(|_| "Could not install terminal cleanup handler")?,
            );
        }
        execute!(io::stdout(), EnableBracketedPaste)
            .map_err(|_| "Could not enable terminal paste")?;
        Ok(console)
    }
}

impl Drop for TerminalConsole {
    fn drop(&mut self) {
        let _ = execute!(io::stdout(), DisableBracketedPaste);
        let _ = terminal::disable_raw_mode();
        for id in self.signals.drain(..) {
            signal_hook::low_level::unregister(id);
        }
    }
}

impl Console for TerminalConsole {
    fn line(&mut self, text: &str) -> Result<(), String> {
        write!(io::stdout(), "{}\r\n", text.replace('\n', "\r\n"))
            .and_then(|_| io::stdout().flush())
            .map_err(|_| "Could not write to the terminal".into())
    }

    fn styled(&mut self, text: &str, tone: Tone) -> Result<(), String> {
        self.line(&paint(text, tone))
    }

    fn spans(&mut self, spans: &[(&str, Option<Tone>)]) -> Result<(), String> {
        let text = spans
            .iter()
            .map(|(text, tone)| tone.map_or_else(|| (*text).to_string(), |tone| paint(text, tone)))
            .collect::<String>();
        self.line(&text)
    }

    fn prompt(&mut self, label: &str, kind: Prompt) -> Result<Zeroizing<String>, String> {
        let tone = match kind {
            Prompt::Secret => Tone::Key,
            Prompt::Choice(_) => Tone::Accent,
        };
        self.styled(label, tone)?;
        let mut input = Zeroizing::new(String::new());
        let mut previous_width: usize = 0;
        loop {
            // Measure only the plain masked text. Color sequences never affect
            // width or expose input, and carriage returns also work without color.
            let width = terminal::size().map_or(76, |(cols, _)| cols.saturating_sub(4) as usize);
            let display = input_display(&input, &kind, width);
            let padding = previous_width.saturating_sub(display.chars().count());
            let painted = paint(&display, tone);
            let marker = paint("> ", tone);
            write!(
                io::stdout(),
                "\r{marker}{painted}{}\r{marker}{painted}",
                " ".repeat(padding)
            )
            .and_then(|_| io::stdout().flush())
            .map_err(|_| "Could not write to the terminal")?;
            previous_width = display.chars().count();
            loop {
                if self.interrupted.load(Ordering::Relaxed) {
                    self.line("")?;
                    return Err(CANCELLED.into());
                }
                if event::poll(Duration::from_millis(100))
                    .map_err(|_| "Could not read terminal input")?
                {
                    break;
                }
            }
            match event::read().map_err(|_| "Could not read terminal input")? {
                Event::Key(key) if key.kind != KeyEventKind::Release => {
                    if key.code == KeyCode::Esc
                        || (key.modifiers.contains(KeyModifiers::CONTROL)
                            && matches!(key.code, KeyCode::Char('c' | 'd')))
                    {
                        self.line("")?;
                        return Err(CANCELLED.into());
                    }
                    match key.code {
                        KeyCode::Enter => {
                            self.line("")?;
                            return Ok(input);
                        }
                        KeyCode::Backspace => {
                            input.pop();
                        }
                        KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            input.zeroize();
                        }
                        KeyCode::Char(c)
                            if !key
                                .modifiers
                                .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
                        {
                            let mut bytes = [0; 4];
                            let result =
                                append_input(&mut input, c.encode_utf8(&mut bytes), &kind, false);
                            bytes.zeroize();
                            if let Err(message) = result {
                                self.line("")?;
                                self.styled(message, Tone::Warning)?;
                                previous_width = 0;
                            }
                        }
                        _ => {}
                    }
                }
                Event::Paste(pasted) => {
                    let pasted = Zeroizing::new(pasted);
                    if let Err(message) = append_input(&mut input, &pasted, &kind, true) {
                        self.line("")?;
                        self.styled(message, Tone::Warning)?;
                        previous_width = 0;
                    }
                }
                _ => {}
            }
        }
    }

    fn open(&mut self, url: &str) -> Result<(), String> {
        if !url.starts_with("https://") || url.chars().any(char::is_control) {
            return Err("Only an HTTPS provider page can be opened".into());
        }
        #[cfg(target_os = "macos")]
        let program = "open";
        #[cfg(not(target_os = "macos"))]
        let program = "xdg-open";
        let status = std::process::Command::new(program)
            .arg(url)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map_err(|_| "Could not open a browser. Use the printed URL")?;
        if status.success() {
            Ok(())
        } else {
            Err("Could not open a browser. Use the printed URL".into())
        }
    }
}

fn input_display(input: &str, kind: &Prompt, width: usize) -> String {
    match kind {
        Prompt::Secret => "*".repeat(input.chars().count().min(width)),
        Prompt::Choice(_) => input.chars().take(width).collect(),
    }
}

fn append_input(
    input: &mut String,
    text: &str,
    kind: &Prompt,
    paste: bool,
) -> Result<(), &'static str> {
    let limit = match kind {
        Prompt::Secret => crate::envfile::MAX_SIZE as usize,
        Prompt::Choice(_) => 128,
    };
    if input.len().saturating_add(text.len()) > limit || text.contains('\0') {
        return Err("Input is too long or contains a NUL byte; nothing was added.");
    }
    if let Prompt::Choice(allowed) = kind {
        // A credential accidentally pasted at a menu must not enter scrollback.
        // Only complete known menu answers are accepted from the clipboard.
        if paste
            && (!input.is_empty()
                || !allowed
                    .iter()
                    .any(|answer| answer.eq_ignore_ascii_case(text.trim())))
        {
            return Err("Choose an option here. Paste credentials only at the masked key prompt.");
        }
        let text = text.trim_matches(['\r', '\n']);
        if text.chars().any(char::is_control) {
            return Err("Use a single menu choice; nothing was added.");
        }
        input.push_str(text);
    } else {
        input.push_str(text);
    }
    Ok(())
}

fn choices(values: &[&str]) -> Prompt {
    Prompt::Choice(values.iter().map(|value| (*value).to_string()).collect())
}

fn provider_index(registry: &Registry, value: &str) -> Option<usize> {
    let value = value.trim();
    value
        .parse::<usize>()
        .ok()
        .and_then(|n| n.checked_sub(1))
        .filter(|&n| n < registry.provider.len())
        .or_else(|| {
            registry.provider.iter().position(|p| {
                p.id.eq_ignore_ascii_case(value) || p.name.eq_ignore_ascii_case(value)
            })
        })
}

/// Open interactive setup. This function never uses an editor or opens a link automatically.
pub fn run(store: &Store, registry: &Registry, provider: Option<&str>) -> Result<(), String> {
    let requested = provider
        .map(|value| {
            provider_index(registry, value).ok_or_else(|| {
                "Unknown provider. Use `godmode providers` to see the available names.".to_string()
            })
        })
        .transpose()?;
    let mut console = TerminalConsole::start()?;
    run_with(store, registry, requested, &mut console)
}

fn run_with(
    store: &Store,
    registry: &Registry,
    requested: Option<usize>,
    console: &mut impl Console,
) -> Result<(), String> {
    console.styled("Godmode setup", Tone::Title)?;
    console.spans(&[
        ("Credentials: ", Some(Tone::Key)),
        (&store.env_path.display().to_string(), None),
    ])?;
    console.spans(&[
        ("Paste keys at the masked prompts. ", None),
        ("Enter saves", Some(Tone::Success)),
        ("; an empty entry skips. ", None),
        ("Esc or Ctrl-C", Some(Tone::Warning)),
        (" leaves setup.", None),
    ])?;
    let fresh = store.needs_setup()?;
    if fresh || !store.is_initialized() {
        console.line("")?;
        if fresh {
            let (heading, body) = FIRST_RUN_NOTICE
                .split_once('\n')
                .unwrap_or((FIRST_RUN_NOTICE, ""));
            console.styled(heading, Tone::Error)?;
            console.line(body)?;
            console.line("")?;
        }
        let (heading, body) = DISCLAIMER.split_once('\n').unwrap_or((DISCLAIMER, ""));
        console.styled(heading, Tone::Section)?;
        console.line(body)?;
        loop {
            let answer = console.prompt(
                "Type GODMODE to continue, or press Esc to leave:",
                choices(&["GODMODE"]),
            )?;
            if answer.as_str() == "GODMODE" {
                break;
            }
            console.styled(
                "The acknowledgement must be GODMODE. No files have been created.",
                Tone::Warning,
            )?;
        }
        store.acknowledge()?;
        console.styled(
            "Ready. Existing credentials and operating rules were preserved.",
            Tone::Success,
        )?;
    }
    let mut saved = 0;
    if let Some(index) = requested {
        saved += setup_provider(store, registry, &registry.provider[index], console)?;
    } else {
        loop {
            console.line("")?;
            console.styled(
                "Choose a provider. Set up only the accounts you need.",
                Tone::Section,
            )?;
            let file = store.load()?;
            let mut allowed = vec![String::new(), "q".into(), "done".into()];
            for (index, provider) in registry.provider.iter().enumerate() {
                let present = provider
                    .key
                    .iter()
                    .filter(|key| matches!(file.get(&key.name), Lookup::Present(_)))
                    .count();
                console.spans(&[
                    (&format!("  {}. ", index + 1), Some(Tone::Accent)),
                    (&provider.name, Some(Tone::Section)),
                    (
                        &format!(" ({present}/{} keys saved)", provider.key.len()),
                        Some(if present == provider.key.len() {
                            Tone::Success
                        } else {
                            Tone::Warning
                        }),
                    ),
                ])?;
                allowed.extend([
                    (index + 1).to_string(),
                    provider.id.clone(),
                    provider.name.clone(),
                ]);
            }
            drop(file);
            let answer = console.prompt(
                "Provider number or name (Enter finishes):",
                Prompt::Choice(allowed),
            )?;
            if answer.trim().is_empty()
                || matches!(answer.trim().to_ascii_lowercase().as_str(), "q" | "done")
            {
                break;
            }
            if let Some(index) = provider_index(registry, &answer) {
                saved += setup_provider(store, registry, &registry.provider[index], console)?;
            } else {
                console.styled(
                    "Choose one of the provider numbers or names above.",
                    Tone::Warning,
                )?;
            }
        }
    }
    console.line("")?;
    console.styled(
        &format!(
            "Setup finished. Saved {saved} {} this session.",
            if saved == 1 { "key" } else { "keys" }
        ),
        Tone::Success,
    )?;
    console.spans(&[
        ("Credential file: ", Some(Tone::Key)),
        (&store.env_path.display().to_string(), None),
    ])?;
    console.spans(&[
        ("Run ", None),
        ("`godmode setup`", Some(Tone::Accent)),
        (" whenever you want to add more. ", None),
        (
            "Local saves do not verify provider access.",
            Some(Tone::Muted),
        ),
    ])?;
    Ok(())
}

fn setup_provider(
    store: &Store,
    registry: &Registry,
    provider: &Provider,
    console: &mut impl Console,
) -> Result<usize, String> {
    console.line("")?;
    console.styled(&provider.name, Tone::Title)?;
    console.line(&provider.purpose)?;
    console.spans(&[
        ("Sign in:  ", Some(Tone::Key)),
        (provider.login_url(), Some(Tone::Link)),
    ])?;
    console.spans(&[
        ("API keys: ", Some(Tone::Key)),
        (&provider.console, Some(Tone::Link)),
    ])?;
    console.spans(&[
        ("Docs:     ", Some(Tone::Key)),
        (&provider.docs, Some(Tone::Link)),
    ])?;
    loop {
        let answer = console.prompt(
            "Enter to add keys; l sign in / o API keys / d docs / s skip provider:",
            choices(&["", "l", "o", "d", "s"]),
        )?;
        let url = match answer.trim().to_ascii_lowercase().as_str() {
            "" => break,
            "s" => return Ok(0),
            "l" => provider.login_url(),
            "o" => &provider.console,
            "d" => &provider.docs,
            _ => {
                console.styled("Press Enter, l, o, d or s.", Tone::Warning)?;
                continue;
            }
        };
        if let Err(message) = console.open(url) {
            console.styled(&message, Tone::Error)?;
        }
    }
    let mut saved = 0;
    for (index, key) in provider.key.iter().enumerate() {
        console.line("")?;
        console.spans(&[
            (&key.name, Some(Tone::Key)),
            (
                &format!(" ({}/{})", index + 1, provider.key.len()),
                Some(Tone::Muted),
            ),
        ])?;
        console.line(&key.usage)?;
        console.spans(&[("Scope: ", Some(Tone::Key)), (&key.scope, None)])?;
        let file = store.load()?;
        let existing = matches!(file.get(&key.name), Lookup::Present(_));
        let invalid = matches!(
            file.get(&key.name),
            Lookup::Duplicate(_) | Lookup::Malformed(_)
        );
        drop(file);
        if existing || invalid {
            console.styled(
                if existing {
                    "A value is already saved. It will not be shown or copied into this prompt."
                } else {
                    "The current assignment needs attention. Replacing it repairs this key only."
                },
                if existing {
                    Tone::Success
                } else {
                    Tone::Warning
                },
            )?;
            loop {
                let answer =
                    console.prompt("Enter to keep it / r to replace:", choices(&["", "r"]))?;
                match answer.trim().to_ascii_lowercase().as_str() {
                    "" => break,
                    "r" => {
                        saved += enter_key(store, registry, key, console)?;
                        break;
                    }
                    _ => console.styled(
                        "Press Enter to keep the current value, or r to replace it.",
                        Tone::Warning,
                    )?,
                }
            }
        } else {
            saved += enter_key(store, registry, key, console)?;
        }
    }
    Ok(saved)
}

fn enter_key(
    store: &Store,
    registry: &Registry,
    key: &crate::registry::Key,
    console: &mut impl Console,
) -> Result<usize, String> {
    for (index, step) in key.steps.iter().enumerate() {
        console.spans(&[
            (&format!("  {}. ", index + 1), Some(Tone::Accent)),
            (step, None),
        ])?;
    }
    if !key.format.is_empty() {
        console.spans(&[
            ("Format: ", Some(Tone::Key)),
            (&key.format, Some(Tone::Warning)),
        ])?;
    }
    loop {
        let value = console.prompt(
            &format!(
                "Paste {} (masked; Enter saves, empty Enter skips):",
                key.name
            ),
            Prompt::Secret,
        )?;
        // Clipboard text commonly includes its final line ending. Preserve spaces
        // and internal newlines; raw JSON remains the store normalizer's job.
        let literal = if key.json {
            value.as_str()
        } else {
            value.trim_matches(['\r', '\n'])
        };
        if literal.is_empty() {
            console.styled("Skipped. Existing contents were kept.", Tone::Muted)?;
            return Ok(0);
        }
        match store.set(&key.name, literal, registry) {
            Ok(()) => {
                console.styled(&format!("{} saved.", key.name), Tone::Success)?;
                return Ok(1);
            }
            Err(message) => {
                console.styled(&message, Tone::Error)?;
                console.styled(
                    "No value was saved. Paste again, leave empty to skip, or press Esc to leave.",
                    Tone::Warning,
                )?;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    struct Scripted {
        answers: VecDeque<Option<String>>,
        output: String,
        opened: Vec<String>,
    }
    impl Scripted {
        fn new(answers: &[Option<&str>]) -> Self {
            Self {
                answers: answers.iter().map(|s| s.map(str::to_string)).collect(),
                output: String::new(),
                opened: vec![],
            }
        }
    }
    impl Console for Scripted {
        fn line(&mut self, text: &str) -> Result<(), String> {
            self.output.push_str(text);
            self.output.push('\n');
            Ok(())
        }
        fn prompt(&mut self, label: &str, _: Prompt) -> Result<Zeroizing<String>, String> {
            self.line(label)?;
            self.answers
                .pop_front()
                .expect("missing scripted answer")
                .map(Zeroizing::new)
                .ok_or_else(|| CANCELLED.into())
        }
        fn open(&mut self, url: &str) -> Result<(), String> {
            self.opened.push(url.into());
            Ok(())
        }
    }
    fn fixture() -> (tempfile::TempDir, Store, Registry) {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let store = Store::new(root.join("home"), root.join("state")).unwrap();
        let registry = toml::from_str(crate::registry::TEMPLATE).unwrap();
        (temp, store, registry)
    }

    #[test]
    fn fresh_setup_saves_masked_input_after_acknowledgement_and_opens_only_requested_links() {
        let (_temp, store, registry) = fixture();
        let secret = "SYNTHETIC_SECRET_493b";
        let mut console = Scripted::new(&[
            Some("GODMODE"),
            Some("Example"),
            Some("l"),
            Some("o"),
            Some("d"),
            Some(""),
            Some(secret),
            Some(""),
        ]);
        run_with(&store, &registry, None, &mut console).unwrap();
        assert!(
            matches!(store.load().unwrap().get("EXAMPLE_ACCOUNT_ADMIN_TOKEN"), Lookup::Present(v) if v.as_str() == secret)
        );
        assert!(console.output.contains(FIRST_RUN_NOTICE));
        assert!(!console.output.contains(secret));
        assert_eq!(
            console.opened,
            [
                "https://example.com/login",
                "https://example.com/settings/tokens",
                "https://example.com/docs/auth"
            ]
        );
        assert!(console.output.contains("Saved 1 key this session"));
    }

    #[test]
    fn cancellation_before_acknowledgement_creates_nothing() {
        let (_temp, store, registry) = fixture();
        let mut console = Scripted::new(&[None]);
        assert!(run_with(&store, &registry, None, &mut console).is_err());
        assert!(!store.config_dir.exists());
        assert!(!store.state_dir.exists());
    }

    #[test]
    fn existing_keys_are_kept_by_default_and_cancelled_replacement_preserves_bytes() {
        let (_temp, store, registry) = fixture();
        store.acknowledge().unwrap();
        store
            .set(
                "EXAMPLE_ACCOUNT_ADMIN_TOKEN",
                "ORIGINAL_PRIVATE_8fae",
                &registry,
            )
            .unwrap();
        let before = std::fs::read(&store.env_path).unwrap();
        let mut keep = Scripted::new(&[Some(""), Some("")]);
        run_with(&store, &registry, Some(0), &mut keep).unwrap();
        assert_eq!(std::fs::read(&store.env_path).unwrap(), before);
        assert!(!keep.output.contains("ORIGINAL_PRIVATE_8fae"));
        assert!(!keep.output.contains(FIRST_RUN_NOTICE));
        let mut cancel = Scripted::new(&[Some(""), Some("r"), None]);
        assert!(run_with(&store, &registry, Some(0), &mut cancel).is_err());
        assert_eq!(std::fs::read(&store.env_path).unwrap(), before);
        assert!(!cancel.output.contains("ORIGINAL_PRIVATE_8fae"));
    }

    #[test]
    fn invalid_value_retries_without_echo_and_clipboard_line_endings_are_removed() {
        let (_temp, store, registry) = fixture();
        store.acknowledge().unwrap();
        let mut console = Scripted::new(&[
            Some(""),
            Some("PRIVATE\nINVALID_VALUE"),
            Some("\r\nVALID_PRIVATE_239a\r\n"),
        ]);
        run_with(&store, &registry, Some(0), &mut console).unwrap();
        assert!(
            matches!(store.load().unwrap().get("EXAMPLE_ACCOUNT_ADMIN_TOKEN"), Lookup::Present(v) if v.as_str() == "VALID_PRIVATE_239a")
        );
        assert!(!console.output.contains("PRIVATE\nINVALID_VALUE"));
        assert!(!console.output.contains("VALID_PRIVATE_239a"));
        assert!(console.output.contains("Paste again"));
    }

    #[test]
    fn secret_paste_stays_masked_and_cannot_submit_or_echo_at_a_menu() {
        let mut value = String::new();
        let secret = "PRIVATE_PASTE\n{\"multiline\":true}\n";
        append_input(&mut value, secret, &Prompt::Secret, true).unwrap();
        assert_eq!(value, secret);
        assert_eq!(input_display(&value, &Prompt::Secret, 8), "********");
        let menu = choices(&["1", "github"]);
        let mut selection = String::new();
        assert!(append_input(&mut selection, secret, &menu, true).is_err());
        assert!(selection.is_empty());
        append_input(&mut selection, "github\n", &menu, true).unwrap();
        assert_eq!(selection, "github");
    }
}
