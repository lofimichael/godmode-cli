//! Human-facing onboarding. Credential bytes never become widget text.
use std::io::{self, IsTerminal};
use std::time::{Duration, Instant};

use ratatui::{
    Frame,
    crossterm::{
        event::{
            self, DisableBracketedPaste, EnableBracketedPaste, Event, KeyCode, KeyEvent,
            KeyEventKind, KeyModifiers,
        },
        execute,
    },
    layout::{Constraint, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Clear, List, ListItem, ListState, Padding, Paragraph, Wrap},
};
use zeroize::{Zeroize, Zeroizing};

use crate::{
    Store,
    envfile::{EnvFile, Lookup},
    registry::{Key, Registry},
};

use crate::store::{DISCLAIMER, FIRST_RUN_NOTICE};

const MAX_INPUT: usize = crate::envfile::MAX_SIZE as usize;

#[derive(Clone, Copy)]
struct Theme {
    bg: Color,
    panel: Color,
    text: Color,
    dim: Color,
    accent: Color,
    amber: Color,
    green: Color,
    red: Color,
    mono: bool,
}
impl Theme {
    fn new() -> Self {
        Self::from_mono(!crate::output::permitted())
    }
    fn from_mono(mono: bool) -> Self {
        // Native terminal colors keep light and dark themes readable. Do not
        // paint a fixed background or dim instructions that the user must read.
        Self {
            bg: Color::Reset,
            panel: Color::Reset,
            text: Color::Reset,
            dim: Color::Reset,
            accent: if mono { Color::Reset } else { Color::Cyan },
            amber: if mono { Color::Reset } else { Color::Yellow },
            green: if mono { Color::Reset } else { Color::Green },
            red: if mono { Color::Reset } else { Color::Red },
            mono,
        }
    }
    fn base(self) -> Style {
        Style::default().fg(self.text).bg(self.bg)
    }
    fn block(self, title: impl Into<String>, active: bool) -> Block<'static> {
        Block::default()
            .title(format!(" [ {} ] ", title.into()))
            .borders(Borders::ALL)
            .border_set(ratatui::symbols::border::Set {
                top_left: "+",
                top_right: "+",
                bottom_left: "+",
                bottom_right: "+",
                vertical_left: "|",
                vertical_right: "|",
                horizontal_top: "-",
                horizontal_bottom: "-",
            })
            .border_style(Style::default().fg(if active { self.accent } else { self.dim }))
            .style(Style::default().fg(self.text).bg(self.panel))
            .padding(Padding::horizontal(1))
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum KeyState {
    Missing,
    Set,
    Invalid,
}
impl KeyState {
    fn label(self) -> &'static str {
        match self {
            Self::Missing => "missing",
            Self::Set => "set",
            Self::Invalid => "invalid",
        }
    }
    fn color(self, t: Theme) -> Color {
        match self {
            Self::Missing => t.dim,
            Self::Set => t.green,
            Self::Invalid => t.red,
        }
    }
}
fn key_state(file: &EnvFile, key: &str) -> KeyState {
    match file.get(key) {
        Lookup::Present(_) => KeyState::Set,
        Lookup::Absent | Lookup::Blank => KeyState::Missing,
        Lookup::Duplicate(_) | Lookup::Malformed(_) => KeyState::Invalid,
    }
}
fn snapshot(store: &Store, registry: &Registry) -> Result<Vec<Vec<KeyState>>, String> {
    let file = store.load()?;
    Ok(registry
        .provider
        .iter()
        .map(|p| p.key.iter().map(|k| key_state(&file, &k.name)).collect())
        .collect())
}

/// Only this type holds unsaved secret input. Its renderer emits fixed masking.
struct SecretInput {
    value: Zeroizing<String>,
}
impl SecretInput {
    fn new() -> Self {
        Self {
            value: Zeroizing::new(String::new()),
        }
    }
    fn push(&mut self, text: &str) -> Result<(), String> {
        if self.value.len().saturating_add(text.len()) > MAX_INPUT {
            return Err("Input exceeds the 1 MiB limit; nothing was added.".into());
        }
        if text.contains('\0') {
            return Err("NUL bytes are not accepted; nothing was added.".into());
        }
        self.value.push_str(text);
        Ok(())
    }
    fn key(&mut self, key: KeyEvent) -> Result<(), String> {
        match key.code {
            KeyCode::Backspace => {
                self.value.pop();
            }
            KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.value.zeroize();
            }
            KeyCode::Char(c)
                if !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
            {
                let mut buf = [0; 4];
                self.push(c.encode_utf8(&mut buf))?;
                buf.zeroize();
            }
            _ => {}
        }
        Ok(())
    }
    fn mask(&self, width: usize) -> String {
        "*".repeat(self.value.chars().count().min(width))
    }
}

struct TerminalGuard;
impl Drop for TerminalGuard {
    fn drop(&mut self) {
        let _ = execute!(io::stdout(), DisableBracketedPaste);
        ratatui::restore();
    }
}
fn start_terminal() -> Result<(ratatui::DefaultTerminal, TerminalGuard), String> {
    if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
        return Err(
            "Interactive setup needs a terminal. Use `godmode status` or `godmode set --stdin`."
                .into(),
        );
    }
    if std::env::var("TERM").is_ok_and(|t| t == "dumb") {
        return Err("This terminal cannot display the board. Use the plain CLI commands (`godmode --help`).".into());
    }
    let terminal =
        ratatui::try_init().map_err(|_| "Could not initialize the terminal.".to_owned())?;
    let guard = TerminalGuard;
    execute!(io::stdout(), EnableBracketedPaste)
        .map_err(|_| "Could not enable bracketed paste.".to_owned())?;
    Ok((terminal, guard))
}

struct Ui {
    accepted: bool,
    first_run: bool,
    ack: String,
    selected: usize,
    selected_key: usize,
    scroll: u16,
    ack_scroll: u16,
    states: Vec<Vec<KeyState>>,
    editing: Option<SecretInput>,
    notice: String,
    help: bool,
    picard_active: bool,
    visual: Option<crate::picard_visual::Visual>,
    show_visual: bool,
    visual_tiled: bool,
    started: Instant,
}
impl Ui {
    fn new(accepted: bool, registry: &Registry) -> Self {
        Self {
            accepted,
            first_run: false,
            ack: String::new(),
            selected: 0,
            selected_key: 0,
            scroll: 0,
            ack_scroll: 0,
            states: registry
                .provider
                .iter()
                .map(|p| vec![KeyState::Missing; p.key.len()])
                .collect(),
            editing: None,
            notice: String::new(),
            help: false,
            picard_active: false,
            visual: None,
            show_visual: false,
            visual_tiled: false,
            started: Instant::now(),
        }
    }
    fn selected_key<'a>(&self, registry: &'a Registry) -> Option<&'a Key> {
        registry
            .provider
            .get(self.selected)?
            .key
            .get(self.selected_key)
    }
    fn next_setup(&mut self, registry: &Registry, skip_provider: bool) {
        if let Some(provider) = registry.provider.get(self.selected) {
            if !skip_provider && self.selected_key + 1 < provider.key.len() {
                self.selected_key += 1;
                self.notice = "Next key selected. Enter adds it; n skips it.".into();
            } else if self.selected + 1 < registry.provider.len() {
                self.selected += 1;
                self.selected_key = 0;
                self.notice = "Next provider selected. Set up only the accounts you need.".into();
            } else {
                self.notice =
                    "End of the provider list. Saved keys are already on disk; q exits.".into();
            }
            self.scroll = 0;
        }
    }
    fn refresh(&mut self, store: &Store, registry: &Registry) {
        match snapshot(store, registry) {
            Ok(states) => self.states = states,
            Err(e) => self.notice = e,
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
enum LoadingAction {
    Continue,
    Cancel,
    Exit,
}

fn loading_action(event: Event) -> LoadingAction {
    match event {
        Event::Key(key) if key.kind != KeyEventKind::Release => {
            if key.code == KeyCode::Char('q')
                || (key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL))
            {
                LoadingAction::Exit
            } else if matches!(
                key.code,
                KeyCode::Char('p') | KeyCode::Char('i') | KeyCode::Esc
            ) {
                LoadingAction::Cancel
            } else {
                LoadingAction::Continue
            }
        }
        Event::Paste(value) => {
            // A paste while loading is not credential input. Clear it and cancel playback.
            let _discarded = Zeroizing::new(value);
            LoadingAction::Cancel
        }
        _ => LoadingAction::Continue,
    }
}

// Downloads run synchronously, but poll terminal input before each short wait.
// Keeping exit separate from cancellation prevents q from merely closing a load notice.
fn load_with_input<T>(
    operation: impl FnOnce(&mut dyn FnMut() -> bool) -> Result<T, String>,
) -> (Result<T, String>, bool) {
    let mut exit = false;
    let mut input_failed = false;
    let result = operation(&mut || loop {
        match event::poll(Duration::ZERO) {
            Ok(false) => return false,
            Ok(true) => match event::read() {
                Ok(event) => match loading_action(event) {
                    LoadingAction::Continue => {}
                    LoadingAction::Cancel => return true,
                    LoadingAction::Exit => {
                        exit = true;
                        return true;
                    }
                },
                Err(_) => {
                    input_failed = true;
                    return true;
                }
            },
            Err(_) => {
                input_failed = true;
                return true;
            }
        }
    });
    if input_failed {
        (Err("Could not read terminal input.".into()), false)
    } else {
        (result, exit)
    }
}

fn poll_audio(player: &mut Option<crate::picard::Player>, error: &mut Option<String>) {
    if let Some(active) = player {
        match active.tick() {
            Ok(true) => {}
            Ok(false) => *player = None,
            Err(message) => {
                *error = Some(message);
                *player = None;
            }
        }
    }
}

fn draw_picard(
    frame: &mut Frame,
    visual: Option<&crate::picard_visual::Visual>,
    notice: &str,
    playing: bool,
    board: bool,
    tiled: bool,
    theme: Theme,
) {
    let area = frame.area();
    frame.render_widget(Block::default().style(theme.base()), area);
    let rows = Layout::vertical([
        Constraint::Length(1),
        Constraint::Min(1),
        Constraint::Length(2),
        Constraint::Length(1),
    ])
    .split(area);
    frame.render_widget(
        Paragraph::new(format!(
            "picard.ytmnd.com   audio: {}",
            if playing { "playing" } else { "stopped" }
        ))
        .style(Style::default().fg(theme.dim)),
        rows[0],
    );
    if let Some(image) = visual {
        image.render(frame, rows[1], theme.mono, tiled);
    }
    frame.render_widget(
        Paragraph::new(notice)
            .wrap(Wrap { trim: false })
            .style(Style::default().fg(theme.amber)),
        rows[2],
    );
    let controls = if board {
        "i/Esc back   t tile/fit   p audio   v source   q quit"
    } else {
        "t tile/fit   p audio   v source   q/Esc quit"
    };
    frame.render_widget(
        Paragraph::new(controls).style(Style::default().fg(theme.dim)),
        rows[3],
    );
}

/// Standalone media view: does not initialize or load a credential store.
pub fn show_picard(state_dir: &std::path::Path) -> Result<(), String> {
    let theme = Theme::new();
    let (mut terminal, _guard) = start_terminal()?;
    terminal
        .draw(|frame| {
            draw_picard(
                frame,
                None,
                "Loading Picard image; Esc cancels, q/Ctrl-C quits.",
                false,
                false,
                false,
                theme,
            )
        })
        .map_err(|_| "Could not draw the terminal.")?;
    let (loaded, exit) =
        load_with_input(|cancel| crate::picard_visual::Visual::load_cancellable(state_dir, cancel));
    if exit {
        return Ok(());
    }
    let visual = loaded?;
    let mut player = None;
    let mut notice = String::new();
    let mut tiled = false;
    loop {
        let mut audio_error = None;
        poll_audio(&mut player, &mut audio_error);
        if let Some(error) = audio_error {
            notice = error;
        }
        terminal
            .draw(|frame| {
                draw_picard(
                    frame,
                    Some(&visual),
                    &notice,
                    player.is_some(),
                    false,
                    tiled,
                    theme,
                )
            })
            .map_err(|_| "Could not draw the terminal.")?;
        if !event::poll(Duration::from_millis(100)).map_err(|_| "Could not read terminal input.")? {
            continue;
        }
        match event::read().map_err(|_| "Could not read terminal input.")? {
            Event::Key(key) if key.kind == KeyEventKind::Press => {
                if matches!(key.code, KeyCode::Char('q') | KeyCode::Esc)
                    || (key.code == KeyCode::Char('c')
                        && key.modifiers.contains(KeyModifiers::CONTROL))
                {
                    return Ok(());
                }
                match key.code {
                    KeyCode::Char('t') => tiled = !tiled,
                    KeyCode::Char('p') => {
                        if let Some(mut active) = player.take() {
                            notice = match active.stop() {
                                Ok(()) => "Picard stopped.".into(),
                                Err(error) => error,
                            };
                        } else {
                            terminal
                                .draw(|frame| {
                                    draw_picard(
                                        frame,
                                        Some(&visual),
                                        "Loading Picard audio; p/Esc cancels, q/Ctrl-C quits.",
                                        false,
                                        false,
                                        tiled,
                                        theme,
                                    )
                                })
                                .map_err(|_| "Could not draw the terminal.")?;
                            let (started, exit) = load_with_input(|cancel| {
                                crate::picard::Player::start_cancellable(state_dir, cancel)
                            });
                            if exit {
                                return Ok(());
                            }
                            match started {
                                Ok(active) => {
                                    player = Some(active);
                                    notice.clear();
                                }
                                Err(error) => notice = error,
                            }
                        }
                    }
                    KeyCode::Char('v') => {
                        notice = match crate::picard::open_source() {
                            Ok(()) => "Opened picard.ytmnd.com in your browser.".into(),
                            Err(error) => error,
                        }
                    }
                    _ => {}
                }
            }
            Event::Paste(value) => {
                let _discarded = Zeroizing::new(value);
            }
            _ => {}
        }
    }
}

/// Open the provider board. Persistence is delegated to Store; UI never reads values for display.
pub fn run(store: &Store, registry: &Registry, no_motion: bool) -> Result<(), String> {
    let first_run = store.needs_setup()?;
    let mut ui = Ui::new(!first_run && store.is_initialized(), registry);
    ui.first_run = first_run;
    if ui.accepted {
        ui.refresh(store, registry);
    }
    let theme = Theme::new();
    let no_motion = no_motion || theme.mono || std::env::var_os("GODMODE_REDUCE_MOTION").is_some();
    let (mut terminal, _guard) = start_terminal()?;
    let mut picard: Option<crate::picard::Player> = None;
    loop {
        if let Some(player) = &mut picard {
            match player.tick() {
                Ok(true) => {}
                Ok(false) => {
                    picard = None;
                    ui.notice = "Picard stopped.".into();
                }
                Err(error) => {
                    picard = None;
                    ui.notice = error;
                }
            }
        }
        ui.picard_active = picard.is_some();
        terminal
            .draw(|frame| draw(frame, store, registry, &mut ui, theme, no_motion))
            .map_err(|_| "Could not draw the terminal.".to_owned())?;
        if !event::poll(Duration::from_millis(if no_motion { 250 } else { 80 }))
            .map_err(|_| "Could not read terminal input.".to_owned())?
        {
            continue;
        }
        match event::read().map_err(|_| "Could not read terminal input.".to_owned())? {
            Event::Key(key) if key.kind == KeyEventKind::Press => {
                if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
                    return Ok(());
                }
                if ui.help {
                    ui.help = false;
                    continue;
                }
                if let Some(input) = &mut ui.editing {
                    match key.code {
                        KeyCode::Esc => {
                            ui.editing = None;
                            ui.notice = "Cancelled. Existing value kept.".into();
                        }
                        KeyCode::Enter => {
                            if input.value.is_empty() {
                                ui.notice = "Enter a value, or Esc to keep the current key.".into();
                                continue;
                            }
                            if let Some(k) = registry
                                .provider
                                .get(ui.selected)
                                .and_then(|p| p.key.get(ui.selected_key))
                            {
                                match store.set(&k.name, &input.value, registry) {
                                    Ok(()) => {
                                        ui.editing = None;
                                        ui.notice = format!(
                                            "{} saved. Press n to continue, or s to skip this provider.",
                                            k.name
                                        );
                                        ui.refresh(store, registry);
                                    }
                                    Err(e) => ui.notice = e,
                                }
                            }
                        }
                        _ => {
                            if let Err(e) = input.key(key) {
                                ui.notice = e;
                            }
                        }
                    }
                    continue;
                }
                if !ui.accepted {
                    match key.code {
                        KeyCode::Esc => return Ok(()),
                        KeyCode::Enter if ui.ack == "GODMODE" => match store.acknowledge() {
                            Ok(()) => {
                                ui.accepted = true;
                                ui.ack.clear();
                                ui.notice =
                                    "Choose a provider; l signs in, o opens API keys, d opens documentation.".into();
                                ui.refresh(store, registry);
                            }
                            Err(e) => ui.notice = e,
                        },
                        KeyCode::Enter => {
                            ui.notice = "Type GODMODE exactly to continue, or Esc to leave.".into()
                        }
                        KeyCode::Backspace => {
                            ui.ack.pop();
                        }
                        KeyCode::Char(c)
                            if !key
                                .modifiers
                                .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT)
                                && ui.ack.len() < 12 =>
                        {
                            ui.ack.push(c)
                        }
                        KeyCode::PageDown | KeyCode::Down => {
                            ui.ack_scroll = ui.ack_scroll.saturating_add(3)
                        }
                        KeyCode::PageUp | KeyCode::Up => {
                            ui.ack_scroll = ui.ack_scroll.saturating_sub(3)
                        }
                        _ => {}
                    }
                    continue;
                }
                if ui.show_visual {
                    match key.code {
                        KeyCode::Char('i') | KeyCode::Esc => {
                            ui.show_visual = false;
                            ui.notice.clear();
                            continue;
                        }
                        KeyCode::Char('q') => return Ok(()),
                        KeyCode::Char('t') => {
                            ui.visual_tiled = !ui.visual_tiled;
                            continue;
                        }
                        KeyCode::Char('p') | KeyCode::Char('v') => {}
                        _ => continue,
                    }
                }
                let count = registry.provider.len();
                match key.code {
                    KeyCode::Char('q') | KeyCode::Esc => return Ok(()),
                    KeyCode::Char('?') => ui.help = true,
                    KeyCode::Down | KeyCode::Char('j') if count > 0 => {
                        ui.selected = (ui.selected + 1) % count;
                        ui.selected_key = 0;
                        ui.scroll = 0;
                    }
                    KeyCode::Up | KeyCode::Char('k') if count > 0 => {
                        ui.selected = (ui.selected + count - 1) % count;
                        ui.selected_key = 0;
                        ui.scroll = 0;
                    }
                    KeyCode::Right | KeyCode::Tab => {
                        if let Some(p) = registry.provider.get(ui.selected)
                            && !p.key.is_empty()
                        {
                            ui.selected_key = (ui.selected_key + 1) % p.key.len();
                            ui.scroll = 0;
                        }
                    }
                    KeyCode::Left | KeyCode::BackTab => {
                        if let Some(p) = registry.provider.get(ui.selected)
                            && !p.key.is_empty()
                        {
                            ui.selected_key = (ui.selected_key + p.key.len() - 1) % p.key.len();
                            ui.scroll = 0;
                        }
                    }
                    KeyCode::Char('n') => ui.next_setup(registry, false),
                    KeyCode::Char('s') => ui.next_setup(registry, true),
                    KeyCode::Char('l') => {
                        if let Some(p) = registry.provider.get(ui.selected) {
                            ui.notice = match open_url(p.login_url()) {
                                Ok(()) => "Opened sign-in in your browser. Return here after creating your key.".into(),
                                Err(e) => e,
                            };
                        }
                    }
                    KeyCode::PageDown => ui.scroll = ui.scroll.saturating_add(5),
                    KeyCode::PageUp => ui.scroll = ui.scroll.saturating_sub(5),
                    KeyCode::Home => ui.scroll = 0,
                    KeyCode::Enter if ui.selected_key(registry).is_some() => {
                        ui.editing = Some(SecretInput::new());
                        ui.notice.clear();
                    }
                    KeyCode::Char('p') => {
                        if let Some(mut player) = picard.take() {
                            ui.notice = match player.stop() {
                                Ok(()) => "Picard stopped.".into(),
                                Err(error) => error,
                            };
                        } else {
                            ui.notice = "Picard loading... [p]/Esc cancel; q/Ctrl-C exit.".into();
                            terminal
                                .draw(|frame| {
                                    draw(frame, store, registry, &mut ui, theme, no_motion)
                                })
                                .map_err(|_| "Could not draw the terminal.")?;
                            let (started, exit_after_cancel) = load_with_input(|cancel| {
                                crate::picard::Player::start_cancellable(&store.state_dir, cancel)
                            });
                            if exit_after_cancel {
                                drop(started);
                                return Ok(());
                            }
                            match started {
                                Ok(player) => {
                                    picard = Some(player);
                                    ui.notice =
                                        "Picard is playing. [p] stop / [v] original source.".into();
                                }
                                Err(error) => ui.notice = error,
                            }
                        }
                    }
                    KeyCode::Char('i') => {
                        if ui.visual.is_none() {
                            ui.notice = "Loading Picard image; i/Esc cancel, q/Ctrl-C quit.".into();
                            terminal
                                .draw(|frame| {
                                    draw(frame, store, registry, &mut ui, theme, no_motion)
                                })
                                .map_err(|_| "Could not draw the terminal.")?;
                            let mut audio_error = None;
                            let (loaded, exit) = load_with_input(|cancel| {
                                crate::picard_visual::Visual::load_cancellable(
                                    &store.state_dir,
                                    || {
                                        poll_audio(&mut picard, &mut audio_error);
                                        cancel()
                                    },
                                )
                            });
                            if exit {
                                return Ok(());
                            }
                            match loaded {
                                Ok(visual) => {
                                    ui.visual = Some(visual);
                                    ui.notice.clear();
                                }
                                Err(error) => ui.notice = error,
                            }
                            if let Some(error) = audio_error {
                                ui.notice = error;
                            }
                        }
                        ui.show_visual = ui.visual.is_some();
                    }
                    KeyCode::Char('v') => {
                        ui.notice = match crate::picard::open_source() {
                            Ok(()) => "Original YTMND source opened in your browser.".into(),
                            Err(error) => error,
                        };
                    }
                    KeyCode::Char('r') => {
                        ui.notice = "Local file refreshed. Set means stored, not verified.".into();
                        ui.refresh(store, registry);
                    }
                    KeyCode::Char('o') => {
                        if let Some(p) = registry.provider.get(ui.selected) {
                            ui.notice = match open_url(&p.console) {
                                Ok(()) => "Provider console opened in your browser.".into(),
                                Err(e) => e,
                            };
                        }
                    }
                    KeyCode::Char('d') => {
                        if let Some(p) = registry.provider.get(ui.selected) {
                            ui.notice = match open_url(&p.docs) {
                                Ok(()) => "Provider documentation opened in your browser.".into(),
                                Err(e) => e,
                            };
                        }
                    }
                    _ => {}
                }
            }
            Event::Paste(value) => {
                let value = Zeroizing::new(value);
                if let Some(input) = &mut ui.editing {
                    if let Err(e) = input.push(&value) {
                        ui.notice = e;
                    }
                } else if !ui.accepted && value.as_str() == "GODMODE" {
                    ui.ack = "GODMODE".into();
                }
            }
            _ => {}
        }
    }
}

fn open_url(url: &str) -> Result<(), String> {
    if !url.starts_with("https://") || url.chars().any(char::is_control) {
        return Err("Only an HTTPS provider URL can be opened.".into());
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
        .map_err(|_| {
            "Could not open a browser. The provider URL is shown in its guide.".to_owned()
        })?;
    if status.success() {
        Ok(())
    } else {
        Err("Browser did not open. The provider URL is shown in its guide.".into())
    }
}

fn draw(
    frame: &mut Frame,
    store: &Store,
    registry: &Registry,
    ui: &mut Ui,
    theme: Theme,
    no_motion: bool,
) {
    let area = frame.area();
    frame.render_widget(Block::default().style(theme.base()), area);
    if ui.show_visual
        && let Some(visual) = &ui.visual
    {
        draw_picard(
            frame,
            Some(visual),
            &ui.notice,
            ui.picard_active,
            true,
            ui.visual_tiled,
            theme,
        );
        return;
    }
    if area.width < 48 || area.height < 16 {
        frame.render_widget(Paragraph::new("GODMODE\n\nResize to at least 48 × 16.\nCtrl-C exits without saving input.\n\nPlain commands: godmode --help").style(theme.base()).wrap(Wrap {trim: false}), area);
        return;
    }
    let rows = Layout::vertical([
        Constraint::Length(if area.width > 80 && area.height > 24 {
            7
        } else {
            3
        }),
        Constraint::Length(2),
        Constraint::Min(5),
        Constraint::Length(2),
        Constraint::Length(1),
    ])
    .margin(1)
    .split(area);
    draw_banner(frame, rows[0], theme, ui.started.elapsed(), no_motion);
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(format!(
                "BUILD .. v{}   LOCAL .. plaintext   PICARD .. {}",
                env!("CARGO_PKG_VERSION"),
                if !ui.accepted {
                    "OFF / controls after setup"
                } else if ui.picard_active {
                    "ON [p] / source [v]"
                } else {
                    "OFF [p] / source [v]"
                }
            ))
            .style(Style::default().fg(theme.dim)),
            Line::from(format!("FILE ... {}", store.env_path.display()))
                .style(Style::default().fg(theme.text)),
        ]),
        rows[1],
    );
    if ui.accepted {
        draw_board(frame, rows[2], registry, ui, theme);
    } else {
        draw_ack(frame, rows[2], ui, theme);
    }
    frame.render_widget(
        Paragraph::new(ui.notice.as_str())
            .style(Style::default().fg(theme.amber))
            .wrap(Wrap { trim: false }),
        rows[3],
    );
    let controls = if ui.editing.is_some() {
        "Enter save   Esc cancel   Ctrl-U clear   paste supported"
    } else if !ui.accepted {
        "GODMODE + Enter accept   PgUp/PgDn read   Esc leave"
    } else if area.width >= 100 {
        "j/k provider  Tab key  Enter add  n next  s skip provider  PgDn read  ? help  q quit"
    } else if area.width >= 72 {
        "j/k provider Tab key Enter add n next s skip PgDn read ? help q quit"
    } else {
        "j/k Tab Enter | l login o keys d docs | n next ? q"
    };
    frame.render_widget(
        Paragraph::new(controls).style(Style::default().fg(theme.dim)),
        rows[4],
    );
    if let Some(input) = &ui.editing
        && let Some(key) = ui.selected_key(registry)
    {
        draw_input(frame, key, input, &ui.notice, theme);
    }
    if ui.help {
        draw_help(frame, theme);
    }
}

// Original masthead drawn for this project, rather than a copied scene logo.
const MASTHEAD: [&str; 6] = [
    r"   _____  ___  ____  __  __  ___  ____  _____ ",
    r"  / ____|/ _ \|  _ \|  \/  |/ _ \|  _ \| ____|",
    r" | |  __| | | | | | | |\/| | | | | | | |  _|  ",
    r" | | |_ | |_| | |_| | |  | | |_| | |_| | |___ ",
    r"  \_____|\___/|____/|_|  |_|\___/|____/|_____|",
    r"",
];

fn draw_banner(frame: &mut Frame, area: Rect, theme: Theme, elapsed: Duration, no_motion: bool) {
    if area.height >= 7 {
        let lines: Vec<_> = MASTHEAD.iter().map(|line| Line::from(*line)).collect();
        frame.render_widget(
            Paragraph::new(lines).style(Style::default().fg(theme.text)),
            Rect::new(area.x, area.y, area.width.min(51), 6),
        );
        if area.width >= 84 {
            frame.render_widget(
                Paragraph::new(vec![
                    Line::from(format!("godmode {}", env!("CARGO_PKG_VERSION"))),
                    Line::default(),
                    Line::from("provider credentials"),
                    Line::from("and setup notes"),
                ])
                .style(Style::default().fg(theme.dim)),
                Rect::new(area.x + 55, area.y + 1, area.width - 55, 5),
            );
        }
    } else {
        frame.render_widget(
            Paragraph::new(format!("godmode {}", env!("CARGO_PKG_VERSION")))
                .style(Style::default().fg(theme.text).bold()),
            area,
        );
    }
    let rule_y = area.y + area.height.saturating_sub(1);
    frame.render_widget(
        Paragraph::new("-".repeat(area.width as usize)).style(Style::default().fg(theme.dim)),
        Rect::new(area.x, rule_y, area.width, 1),
    );
    if !no_motion && area.width > 0 {
        let offset = ((elapsed.as_millis() / 150) % area.width as u128) as u16;
        frame.buffer_mut()[(area.x + offset, rule_y)].set_fg(theme.amber);
    }
}

fn draw_ack(frame: &mut Frame, area: Rect, ui: &mut Ui, theme: Theme) {
    let rows = Layout::vertical([Constraint::Min(3), Constraint::Length(3)]).split(area);
    let block = theme.block("READTHIS.NFO", true);
    let inner = block.inner(rows[0]);
    let text = if ui.first_run {
        format!("{FIRST_RUN_NOTICE}\n\n{DISCLAIMER}")
    } else {
        DISCLAIMER.to_owned()
    };
    let paragraph = Paragraph::new(text).wrap(Wrap { trim: false });
    let total = paragraph.line_count(inner.width).min(u16::MAX as usize) as u16;
    ui.ack_scroll = ui.ack_scroll.min(total.saturating_sub(inner.height));
    frame.render_widget(paragraph.scroll((ui.ack_scroll, 0)).block(block), rows[0]);
    frame.render_widget(
        Paragraph::new(format!("> {}", ui.ack))
            .style(Style::default().fg(theme.text))
            .block(theme.block("TYPE GODMODE", true)),
        rows[1],
    );
}

fn fit_name(name: &str, width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    let truncated = Span::raw(name).width() > width;
    let content_width = width.saturating_sub(usize::from(truncated));
    let mut output = String::new();
    let mut used = 0;
    for c in name.chars() {
        let char_width = Span::raw(c.to_string()).width();
        if used + char_width > content_width {
            break;
        }
        output.push(c);
        used += char_width;
    }
    if truncated {
        output.push('…');
        used += 1;
    }
    output.push_str(&" ".repeat(width.saturating_sub(used)));
    output
}

fn draw_board(frame: &mut Frame, area: Rect, registry: &Registry, ui: &mut Ui, theme: Theme) {
    if registry.provider.is_empty() {
        frame.render_widget(
            Paragraph::new(
                "No providers. Add an entry to providers.toml, or use `godmode set KEY`.",
            )
            .wrap(Wrap { trim: false })
            .block(theme.block("PROVIDERS", true)),
            area,
        );
        return;
    }
    let cols = if area.width >= 72 {
        Layout::horizontal([Constraint::Length(25), Constraint::Min(20)])
            .spacing(1)
            .split(area)
    } else {
        Layout::vertical([Constraint::Length(5), Constraint::Min(3)]).split(area)
    };
    let left = Layout::vertical([Constraint::Min(3), Constraint::Length(2)]).split(cols[0]);
    let items: Vec<_> = registry
        .provider
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let states = &ui.states[i];
            let set = states.iter().filter(|&&s| s == KeyState::Set).count();
            let bad = states.contains(&KeyState::Invalid);
            let (glyph, color) = if bad {
                ("!", theme.red)
            } else if set == p.key.len() {
                ("+", theme.green)
            } else if set > 0 {
                ("~", theme.amber)
            } else {
                ("-", theme.dim)
            };
            let count = format!("  {set}/{}", p.key.len());
            // Reserve room for borders, padding, selection, state glyph, and count.
            let name_width = (left[0].width as usize).saturating_sub(8 + count.len());
            ListItem::new(Line::from(vec![
                Span::styled(format!("{glyph} "), Style::default().fg(color)),
                Span::raw(fit_name(&p.name, name_width)),
                Span::styled(count, Style::default().fg(theme.dim)),
            ]))
        })
        .collect();
    let mut list_state = ListState::default().with_selected(Some(ui.selected));
    frame.render_stateful_widget(
        List::new(items)
            .block(theme.block("PROVIDERS", true))
            .highlight_style(
                Style::default()
                    .fg(theme.accent)
                    .add_modifier(Modifier::BOLD),
            )
            .highlight_symbol("> "),
        left[0],
        &mut list_state,
    );
    let total: usize = ui.states.iter().map(Vec::len).sum();
    let set = ui
        .states
        .iter()
        .flatten()
        .filter(|&&s| s == KeyState::Set)
        .count();
    let meter_width = (left[1].width as usize).saturating_sub(2);
    let filled = (set * meter_width).checked_div(total).unwrap_or(0);
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(format!("{set}/{total} keys stored")).style(Style::default().fg(theme.text)),
            Line::from(format!(
                "[{}{}]",
                "#".repeat(filled),
                ".".repeat(meter_width - filled)
            ))
            .style(Style::default().fg(theme.accent)),
        ]),
        left[1],
    );
    let p = &registry.provider[ui.selected];
    let mut lines = vec![
        Line::from(p.purpose.clone()).style(Style::default().fg(theme.text)),
        Line::default(),
    ];
    for (i, key) in p.key.iter().enumerate() {
        let state = ui.states[ui.selected][i];
        lines.push(Line::from(vec![
            Span::styled(
                if i == ui.selected_key { "> " } else { "  " },
                Style::default().fg(theme.accent),
            ),
            Span::styled(
                key.name.as_str(),
                Style::default()
                    .fg(if i == ui.selected_key {
                        theme.accent
                    } else {
                        theme.text
                    })
                    .add_modifier(if i == ui.selected_key {
                        Modifier::BOLD
                    } else {
                        Modifier::empty()
                    }),
            ),
            Span::styled(
                format!(
                    "  {}{}",
                    state.label(),
                    if key.required { "" } else { " · optional" }
                ),
                Style::default().fg(state.color(theme)),
            ),
        ]));
    }
    if let Some(key) = p.key.get(ui.selected_key) {
        lines.extend([
            Line::default(),
            Line::from("[ SETUP ]").style(Style::default().fg(theme.text).bold()),
        ]);
        for (i, step) in key.steps.iter().enumerate() {
            lines.push(Line::from(format!("{}. {step}", i + 1)));
        }
        lines.extend([
            Line::default(),
            Line::from("[ USAGE ]").style(Style::default().fg(theme.text).bold()),
            Line::from(key.usage.clone()),
            Line::default(),
            Line::from("[ SCOPE ]").style(Style::default().fg(theme.text).bold()),
            Line::from(key.scope.clone()),
        ]);
        if !key.format.is_empty() {
            lines.extend([
                Line::default(),
                Line::from("[ EXPECTED FORMAT ]").style(Style::default().fg(theme.text).bold()),
                Line::from(key.format.clone()),
            ]);
        }
    }
    lines.extend([
        Line::default(),
        Line::from("SIGN IN  [l]").style(Style::default().fg(theme.text).bold()),
        Line::from(p.login_url().to_owned()).style(Style::default().fg(theme.accent).underlined()),
        Line::default(),
        Line::from("API KEYS  [o]").style(Style::default().fg(theme.text).bold()),
        Line::from(p.console.clone()).style(Style::default().fg(theme.accent).underlined()),
        Line::default(),
        Line::from("DOCUMENTATION  [d]").style(Style::default().fg(theme.text).bold()),
        Line::from(p.docs.clone()).style(Style::default().fg(theme.accent).underlined()),
    ]);
    for note in &p.notes {
        lines.extend([
            Line::default(),
            Line::from(note.clone()).style(Style::default().fg(theme.dim)),
        ]);
    }
    lines.extend([
        Line::default(),
        Line::from("Set means stored locally. Account access and permissions are not verified.")
            .style(Style::default().fg(theme.amber)),
    ]);
    let block = theme.block(p.name.clone(), false);
    let inner = block.inner(cols[1]);
    frame.render_widget(block, cols[1]);
    let areas = Layout::vertical([Constraint::Length(4), Constraint::Min(1)]).split(inner);
    let link_line = |key: &str, name: &str, url: &str| {
        let label = format!("[{key}] {name:<8} ");
        let display = url
            .strip_prefix("https://")
            .unwrap_or(url)
            .split('?')
            .next()
            .unwrap_or(url);
        Line::from(vec![
            Span::styled(label.clone(), Style::default().fg(theme.text)),
            Span::styled(
                fit_name(
                    display,
                    (areas[0].width as usize).saturating_sub(label.len()),
                ),
                Style::default().fg(theme.accent).underlined(),
            ),
        ])
    };
    frame.render_widget(
        Paragraph::new(vec![
            link_line("l", "Sign in", p.login_url()),
            link_line("o", "API keys", &p.console),
            link_line("d", "Docs", &p.docs),
        ]),
        areas[0],
    );
    let paragraph = Paragraph::new(Text::from(lines)).wrap(Wrap { trim: false });
    let total = paragraph.line_count(areas[1].width).min(u16::MAX as usize) as u16;
    ui.scroll = ui.scroll.min(total.saturating_sub(areas[1].height));
    frame.render_widget(paragraph.scroll((ui.scroll, 0)), areas[1]);
}

fn popup(area: Rect, width: u16, height: u16) -> Rect {
    let width = width.min(area.width.saturating_sub(4));
    let height = height.min(area.height.saturating_sub(2));
    Rect::new(
        area.x + (area.width - width) / 2,
        area.y + (area.height - height) / 2,
        width,
        height,
    )
}
fn draw_input(frame: &mut Frame, key: &Key, input: &SecretInput, notice: &str, theme: Theme) {
    let area = popup(frame.area(), 84, 14);
    frame.render_widget(Clear, area);
    let block = theme.block(format!("ADD / REPLACE  {}", key.name), true);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let mask_width = inner.width.saturating_sub(4) as usize;
    let shape = if input.value.is_empty() {
        "Paste or type a value. Existing values stay hidden.".to_owned()
    } else if key
        .forbid_prefixes
        .iter()
        .any(|p| input.value.starts_with(p))
    {
        "This value has a forbidden prefix for this key.".into()
    } else if key.json {
        "JSON input · compacted and validated on save".into()
    } else if !key.prefixes.is_empty() && !key.prefixes.iter().any(|p| input.value.starts_with(p)) {
        "Prefix differs from the guide. Check the key type before saving.".into()
    } else {
        "Press Enter to save, or Esc to discard this input.".into()
    };
    let text = vec![
        Line::from("Stored as plaintext, mode 0600. Programs running as you can read it.")
            .style(Style::default().fg(theme.dim)),
        Line::default(),
        Line::from(format!("> {}", input.mask(mask_width))).style(Style::default().fg(theme.text)),
        Line::from(format!("{} bytes entered", input.value.len()))
            .style(Style::default().fg(theme.dim)),
        Line::default(),
        Line::from(shape).style(Style::default().fg(theme.accent)),
        Line::default(),
        Line::from(notice).style(Style::default().fg(theme.amber)),
        Line::default(),
        Line::from("Enter save / Esc keep existing / Ctrl-U clear")
            .style(Style::default().fg(theme.dim)),
    ];
    frame.render_widget(Paragraph::new(text).wrap(Wrap { trim: false }), inner);
    if inner.height > 2 {
        frame.set_cursor_position((
            inner.x + 2 + input.value.chars().count().min(mask_width) as u16,
            inner.y + 2,
        ));
    }
}
fn draw_help(frame: &mut Frame, theme: Theme) {
    let area = popup(frame.area(), 86, 25);
    frame.render_widget(Clear, area);
    frame.render_widget(Paragraph::new("j/k, Up/Down   Choose a provider\nTab, Left/Right Choose one of its keys\nEnter          Add or replace selected key\nPgUp/PgDn      Read the provider notes\nHome           Top of notes\nl / o / d      Provider sign-in / API keys / documentation\nn              Next key, then next provider\ns              Skip remaining keys for this provider\ni              Show the Picard image (downloads on first view)\np              Picard loop: play / stop (downloads on first play)\nv              Open the original YTMND source\nr              Reload local key status\nq, Esc, Ctrl-C Leave; stop playback\n\nKey entry: type or paste, Backspace, Ctrl-U clear,\nEnter save, Esc cancel. No reveal switch.\n\nKey status is local; provider access has not been checked.\nPress any key to return.").wrap(Wrap{trim:false}).block(theme.block("KEYS",true)),area);
}

/// Read a secret from an actual raw-mode TTY, including large bracketed pastes.
pub fn prompt_secret(label: &str) -> Result<Zeroizing<String>, String> {
    let (mut terminal, _guard) = start_terminal()?;
    let mut input = SecretInput::new();
    let theme = Theme::new();
    let mut notice = String::new();
    loop {
        terminal
            .draw(|frame| {
                let area = frame.area();
                frame.render_widget(Block::default().style(theme.base()), area);
                let popup = popup(area, 80, 9);
                frame.render_widget(
                    Paragraph::new(vec![
                        Line::from(label).style(Style::default().fg(theme.text).bold()),
                        Line::default(),
                        Line::from(format!(
                            "> {}",
                            input.mask(popup.width.saturating_sub(7) as usize)
                        )),
                        Line::from(format!("{} bytes / hidden", input.value.len()))
                            .style(Style::default().fg(theme.dim)),
                        Line::from(notice.as_str()).style(Style::default().fg(theme.amber)),
                        Line::from("Enter save / Esc cancel / Ctrl-U clear")
                            .style(Style::default().fg(theme.dim)),
                    ])
                    .wrap(Wrap { trim: false })
                    .block(theme.block("GODMODE / KEY ENTRY", true)),
                    popup,
                );
            })
            .map_err(|_| "Could not draw the terminal.".to_owned())?;
        match event::read().map_err(|_| "Could not read terminal input.".to_owned())? {
            Event::Key(key) if key.kind == KeyEventKind::Press => {
                if key.code == KeyCode::Esc
                    || (key.modifiers.contains(KeyModifiers::CONTROL)
                        && key.code == KeyCode::Char('c'))
                {
                    return Err("Cancelled. No value saved.".into());
                }
                if key.code == KeyCode::Enter {
                    return Ok(input.value);
                }
                if let Err(e) = input.key(key) {
                    notice = e;
                }
            }
            Event::Paste(value) => {
                let value = Zeroizing::new(value);
                if let Err(e) = input.push(&value) {
                    notice = e;
                }
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{Terminal, backend::TestBackend};
    fn key() -> Key {
        Key {
            name: "SAMPLE_API_TOKEN".into(),
            kind: "secret".into(),
            usage: "Build useful things".into(),
            scope: "Selected account".into(),
            format: "token".into(),
            verify: String::new(),
            required: true,
            steps: vec!["Open the provider console".into()],
            prefixes: vec![],
            forbid_prefixes: vec![],
            json: false,
        }
    }
    fn buffer_text(terminal: &Terminal<TestBackend>) -> String {
        terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|c| c.symbol())
            .collect()
    }
    #[test]
    fn every_secret_input_frame_is_masked() {
        let mut terminal = Terminal::new(TestBackend::new(100, 30)).unwrap();
        let mut input = SecretInput::new();
        let sentinel = "SENTINEL_PRIVATE_7f08_TOKEN";
        for c in sentinel.chars() {
            input
                .key(KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE))
                .unwrap();
            terminal
                .draw(|f| draw_input(f, &key(), &input, "", Theme::new()))
                .unwrap();
            let text = buffer_text(&terminal);
            assert!(!text.contains(sentinel));
            assert!(!text.contains("SENTINEL"));
        }
        input
            .push("\n{\"private_key\":\"SENTINEL_MULTI_KB_JSON\"}\n")
            .unwrap();
        terminal
            .draw(|f| draw_input(f, &key(), &input, "", Theme::new()))
            .unwrap();
        assert!(!buffer_text(&terminal).contains("SENTINEL"));
        input
            .key(KeyEvent::new(KeyCode::Char('u'), KeyModifiers::CONTROL))
            .unwrap();
        assert!(input.value.is_empty());
    }
    #[test]
    fn secret_input_handles_large_paste_and_cancel_by_drop() {
        let mut input = SecretInput::new();
        input.push(&"x".repeat(20000)).unwrap();
        assert_eq!(input.value.len(), 20000);
        assert_eq!(input.mask(25).chars().count(), 25);
        assert!(input.push(&"x".repeat(MAX_INPUT)).is_err());
        assert_eq!(input.value.len(), 20000);
        assert!(input.push("\0").is_err());
    }
    #[test]
    fn loading_cancellation_preserves_exit_intent_and_ignores_key_release() {
        for key in [KeyCode::Char('p'), KeyCode::Esc] {
            assert_eq!(
                loading_action(Event::Key(KeyEvent::new(key, KeyModifiers::NONE))),
                LoadingAction::Cancel
            );
        }
        assert_eq!(
            loading_action(Event::Key(KeyEvent::new(
                KeyCode::Char('q'),
                KeyModifiers::NONE
            ))),
            LoadingAction::Exit
        );
        assert_eq!(
            loading_action(Event::Key(KeyEvent::new(
                KeyCode::Char('c'),
                KeyModifiers::CONTROL
            ))),
            LoadingAction::Exit
        );
        let mut released = KeyEvent::new(KeyCode::Char('p'), KeyModifiers::NONE);
        released.kind = KeyEventKind::Release;
        assert_eq!(
            loading_action(Event::Key(released)),
            LoadingAction::Continue
        );
        assert_eq!(
            loading_action(Event::Resize(80, 24)),
            LoadingAction::Continue
        );
        assert_eq!(
            loading_action(Event::Paste("DISCARDED_SYNTHETIC_INPUT".into())),
            LoadingAction::Cancel
        );
    }

    #[test]
    fn masthead_is_original_plain_ascii_and_fits_its_area() {
        assert!(
            MASTHEAD
                .iter()
                .all(|line| line.is_ascii() && line.len() <= 51)
        );
    }

    #[test]
    fn board_and_disclaimer_render_across_sizes_without_values() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let store = Store::new(root.join("config"), root.join("state")).unwrap();
        let registry = Registry {
            schema: 1,
            provider: vec![crate::registry::Provider {
                id: "sample".into(),
                name: "Sample provider".into(),
                purpose: "Deploy and manage the selected account".into(),
                login: "https://example.invalid/login".into(),
                console: "https://example.invalid/keys".into(),
                docs: "https://example.invalid/docs".into(),
                notes: vec![],
                key: vec![key()],
            }],
        };
        for (width, height) in [(1, 1), (47, 15), (48, 16), (80, 24), (120, 40)] {
            let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
            let mut ui = Ui::new(false, &registry);
            terminal
                .draw(|f| draw(f, &store, &registry, &mut ui, Theme::new(), true))
                .unwrap();
            ui.accepted = true;
            ui.states[0][0] = KeyState::Set;
            terminal
                .draw(|f| draw(f, &store, &registry, &mut ui, Theme::new(), true))
                .unwrap();
            if width >= 80 && height >= 24 {
                let text = buffer_text(&terminal);
                assert!(text.contains("SAMPLE_API_TOKEN"));
                assert!(text.contains("1/1 keys stored"));
                assert!(text.contains("Sign in"));
                assert!(text.contains("Docs"));
                assert!(text.contains("PICARD .. OFF"));
                if width == 80 {
                    assert!(text.contains("godmode "));
                }
            }
            let mut input = SecretInput::new();
            input.push("BOARD_FRAME_PRIVATE_SENTINEL").unwrap();
            ui.editing = Some(input);
            terminal
                .draw(|f| draw(f, &store, &registry, &mut ui, Theme::new(), true))
                .unwrap();
            assert!(!buffer_text(&terminal).contains("BOARD_FRAME_PRIVATE_SENTINEL"));
        }
    }

    /// Renders the real widgets using synthetic states; never opens the credential file.
    /// GODMODE_RENDER_PATH must name an explicit output SVG file.
    #[test]
    #[ignore = "writes an explicitly requested synthetic UI preview"]
    fn render_preview() {
        use std::fmt::Write;
        let path = std::env::var_os("GODMODE_RENDER_PATH")
            .map(std::path::PathBuf::from)
            .expect("set GODMODE_RENDER_PATH to an explicit SVG destination");
        assert!(path.is_absolute(), "preview destination must be absolute");
        let registry: Registry =
            toml::from_str(include_str!("../registry/providers.toml")).unwrap();
        let store = Store::new("/demo/.godmode".into(), "/demo/.godmode/state".into()).unwrap();
        let mut ui = Ui::new(true, &registry);
        ui.states[0][0] = KeyState::Set;
        ui.states[1][0] = KeyState::Set;
        ui.notice = "Choose a provider and press Enter to add a key.".into();
        let theme = Theme::from_mono(false);
        let width = std::env::var("GODMODE_RENDER_WIDTH")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(112_u16);
        let height = std::env::var("GODMODE_RENDER_HEIGHT")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(36_u16);
        let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
        let stem = path.file_stem().unwrap().to_string_lossy();
        let extension = |kind: &str| path.with_file_name(format!("{stem}-{kind}.svg"));
        let mut previews = vec![
            ("board", path.clone()),
            ("disclaimer", extension("disclaimer")),
            ("masked", extension("masked")),
        ];
        if let Some(state) = std::env::var_os("GODMODE_RENDER_PICARD_STATE") {
            ui.visual = Some(
                crate::picard_visual::Visual::load_cancellable(
                    &std::path::PathBuf::from(state),
                    || false,
                )
                .expect("explicit Picard preview needs its verified cache"),
            );
            previews.push(("picard", extension("picard")));
            previews.push(("picard-tiled", extension("picard-tiled")));
        }
        for (kind, output) in previews {
            ui.show_visual = kind.starts_with("picard");
            ui.visual_tiled = kind == "picard-tiled";
            ui.accepted = kind != "disclaimer";
            ui.first_run = kind == "disclaimer";
            ui.editing = if kind == "masked" {
                let mut input = SecretInput::new();
                input
                    .push("SYNTHETIC_PREVIEW_CREDENTIAL_NEVER_RENDERED")
                    .unwrap();
                Some(input)
            } else {
                None
            };
            if ui.show_visual {
                ui.notice.clear();
            }
            terminal
                .draw(|frame| draw(frame, &store, &registry, &mut ui, theme, true))
                .unwrap();
            let mut svg = format!(
                r##"<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}"><title>Godmode {} — rendered terminal UI preview with synthetic state</title><rect width="100%" height="100%" fill="#1e1e1e"/><g font-family="Menlo,DejaVu Sans Mono,monospace" font-size="14">"##,
                width * 9,
                height * 18,
                width * 9,
                height * 18,
                kind
            );
            for y in 0..height {
                for x in 0..width {
                    let cell = &terminal.backend().buffer()[(x, y)];
                    let rgb = |color: Color, fallback: &str| -> String {
                        match color {
                            Color::Rgb(r, g, b) => format!("#{r:02x}{g:02x}{b:02x}"),
                            Color::Cyan => "#56b6c2".into(),
                            Color::Green => "#8bbf76".into(),
                            Color::Yellow => "#c8ac67".into(),
                            Color::Red => "#d47777".into(),
                            _ => fallback.to_string(),
                        }
                    };
                    let mut fg = rgb(cell.fg, "#d4d4d4");
                    let mut bg = rgb(cell.bg, "#1e1e1e");
                    if cell.modifier.contains(Modifier::REVERSED) {
                        std::mem::swap(&mut fg, &mut bg);
                    }
                    write!(
                        svg,
                        r#"<rect x="{}" y="{}" width="9" height="18" fill="{}"/>"#,
                        x * 9,
                        y * 18,
                        bg
                    )
                    .unwrap();
                    if cell.symbol() != " " {
                        let text = cell
                            .symbol()
                            .replace('&', "&amp;")
                            .replace('<', "&lt;")
                            .replace('>', "&gt;");
                        write!(
                            svg,
                            r#"<text x="{}" y="{}" fill="{}"{}>{}</text>"#,
                            x * 9,
                            y * 18 + 14,
                            fg,
                            if cell.modifier.contains(Modifier::BOLD) {
                                " font-weight=\"bold\""
                            } else {
                                ""
                            },
                            text
                        )
                        .unwrap();
                    }
                }
            }
            svg.push_str("</g></svg>");
            assert!(!svg.contains("SYNTHETIC_PREVIEW_CREDENTIAL_NEVER_RENDERED"));
            std::fs::write(output, svg).unwrap();
        }
    }

    #[test]
    fn input_resize_and_help_never_panic() {
        for (width, height) in [(1, 1), (20, 5), (48, 16), (80, 24), (120, 40)] {
            let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
            let mut input = SecretInput::new();
            input.push("private-sentinel").unwrap();
            terminal
                .draw(|f| {
                    draw_input(f, &key(), &input, "", Theme::new());
                    draw_help(f, Theme::new());
                })
                .unwrap();
            assert!(!buffer_text(&terminal).contains("private-sentinel"));
        }
    }
}
