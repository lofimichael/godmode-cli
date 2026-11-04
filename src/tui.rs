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
    widgets::{
        Block, BorderType, Borders, Clear, Gauge, List, ListItem, ListState, Padding, Paragraph,
        Wrap,
    },
};
use tui_big_text::{BigText, PixelSize};
use zeroize::{Zeroize, Zeroizing};

use crate::{
    Store,
    envfile::{EnvFile, Lookup},
    registry::{Key, Registry},
};

use crate::store::DISCLAIMER;

const MAX_INPUT: usize = crate::envfile::MAX_SIZE as usize;

#[derive(Clone, Copy)]
struct Theme {
    bg: Color,
    panel: Color,
    text: Color,
    dim: Color,
    purple: Color,
    amber: Color,
    green: Color,
    red: Color,
    mono: bool,
}
impl Theme {
    fn new() -> Self {
        let mono = std::env::var_os("NO_COLOR").is_some();
        if mono {
            return Self {
                bg: Color::Reset,
                panel: Color::Reset,
                text: Color::Reset,
                dim: Color::Reset,
                purple: Color::Reset,
                amber: Color::Reset,
                green: Color::Reset,
                red: Color::Reset,
                mono,
            };
        }
        let rgb = std::env::var("COLORTERM").is_ok_and(|v| v == "truecolor" || v == "24bit");
        if rgb {
            Self {
                bg: Color::Rgb(12, 12, 20),
                panel: Color::Rgb(19, 19, 30),
                text: Color::Rgb(231, 230, 243),
                dim: Color::Rgb(139, 137, 163),
                purple: Color::Rgb(173, 136, 255),
                amber: Color::Rgb(255, 200, 109),
                green: Color::Rgb(118, 218, 181),
                red: Color::Rgb(255, 120, 135),
                mono,
            }
        } else {
            Self {
                bg: Color::Indexed(233),
                panel: Color::Indexed(235),
                text: Color::Indexed(255),
                dim: Color::Indexed(245),
                purple: Color::Indexed(141),
                amber: Color::Indexed(222),
                green: Color::Indexed(115),
                red: Color::Indexed(210),
                mono,
            }
        }
    }
    fn base(self) -> Style {
        Style::default().fg(self.text).bg(self.bg)
    }
    fn block(self, title: impl Into<String>, active: bool) -> Block<'static> {
        Block::default()
            .title(format!(" {} ", title.into()))
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(if active { self.purple } else { self.dim }))
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
        "•".repeat(self.value.chars().count().min(width))
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
    ack: String,
    selected: usize,
    selected_key: usize,
    scroll: u16,
    ack_scroll: u16,
    states: Vec<Vec<KeyState>>,
    editing: Option<SecretInput>,
    notice: String,
    help: bool,
    started: Instant,
}
impl Ui {
    fn new(accepted: bool, registry: &Registry) -> Self {
        Self {
            accepted,
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
    fn refresh(&mut self, store: &Store, registry: &Registry) {
        match snapshot(store, registry) {
            Ok(states) => self.states = states,
            Err(e) => self.notice = e,
        }
    }
}

/// Open the provider board. Persistence is delegated to Store; UI never reads values for display.
pub fn run(store: &Store, registry: &Registry, no_motion: bool) -> Result<(), String> {
    let mut ui = Ui::new(store.is_initialized(), registry);
    if ui.accepted {
        ui.refresh(store, registry);
    }
    let theme = Theme::new();
    let no_motion = no_motion || theme.mono || std::env::var_os("GODMODE_REDUCE_MOTION").is_some();
    let (mut terminal, _guard) = start_terminal()?;
    loop {
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
                                        ui.notice = format!("{} saved · mode 0600", k.name);
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
                                    "Ready. Choose a provider, then press Enter to add a key."
                                        .into();
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
                    KeyCode::PageDown => ui.scroll = ui.scroll.saturating_add(5),
                    KeyCode::PageUp => ui.scroll = ui.scroll.saturating_sub(5),
                    KeyCode::Home => ui.scroll = 0,
                    KeyCode::Enter if ui.selected_key(registry).is_some() => {
                        ui.editing = Some(SecretInput::new());
                        ui.notice.clear();
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
    if area.width < 48 || area.height < 16 {
        frame.render_widget(Paragraph::new("GODMODE\n\nResize to at least 48 × 16.\nCtrl-C exits without saving input.\n\nPlain commands: godmode --help").style(theme.base()).wrap(Wrap {trim: false}), area);
        return;
    }
    let rows = Layout::vertical([
        Constraint::Length(5),
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
            Line::from(vec![
                Span::styled(
                    "ONE FILE. EVERY CAPABILITY.",
                    Style::default().fg(theme.amber).bold(),
                ),
                Span::styled(
                    "  /  YOUR AGENTS, UNLEASHED",
                    Style::default().fg(theme.dim),
                ),
            ]),
            Line::from(store.env_path.display().to_string()).style(Style::default().fg(theme.dim)),
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
    } else {
        "↑↓ provider  ←→ key  Enter add  PgDn read  o console  ? help  q quit"
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

fn draw_banner(frame: &mut Frame, area: Rect, theme: Theme, elapsed: Duration, no_motion: bool) {
    let banner = BigText::builder()
        .pixel_size(PixelSize::Quadrant)
        .style(Style::default().fg(theme.purple))
        .lines(vec!["GODMODE".into()])
        .build();
    frame.render_widget(
        banner,
        Rect::new(area.x, area.y, area.width.min(30), area.height.min(4)),
    );
    if area.width >= 70 {
        let right = Rect::new(area.x + 37, area.y + 1, area.width.saturating_sub(37), 3);
        frame.render_widget(
            Paragraph::new(vec![
                Line::from("LOBOTOMIZED AGENTS").style(Style::default().fg(theme.text).bold()),
                Line::from("HELP NOBODY.").style(Style::default().fg(theme.amber).bold()),
                Line::from(format!(
                    "v{}  ·  LOCAL CREDENTIAL ONBOARDING",
                    env!("CARGO_PKG_VERSION")
                ))
                .style(Style::default().fg(theme.dim)),
            ]),
            right,
        );
    }
    if !no_motion {
        let sweep = (elapsed.as_millis() / 100) as u16 % 50;
        for y in area.y..area.y + area.height.min(4) {
            for x in area.x..area.x + area.width.min(28) {
                let relative = x - area.x;
                let color = if relative.abs_diff(sweep) < 2 {
                    theme.amber
                } else {
                    theme.purple
                };
                frame.buffer_mut()[(x, y)].set_fg(color);
            }
        }
    }
    if area.height >= 5 {
        frame.render_widget(
            Paragraph::new("─".repeat(area.width as usize)).style(Style::default().fg(theme.dim)),
            Rect::new(area.x, area.y + 4, area.width, 1),
        );
    }
}

fn draw_ack(frame: &mut Frame, area: Rect, ui: &mut Ui, theme: Theme) {
    let rows = Layout::vertical([Constraint::Min(3), Constraint::Length(3)]).split(area);
    let block = theme.block("THE DEAL", true);
    let inner = block.inner(rows[0]);
    let paragraph = Paragraph::new(DISCLAIMER).wrap(Wrap { trim: false });
    let total = paragraph.line_count(inner.width).min(u16::MAX as usize) as u16;
    ui.ack_scroll = ui.ack_scroll.min(total.saturating_sub(inner.height));
    frame.render_widget(paragraph.scroll((ui.ack_scroll, 0)).block(block), rows[0]);
    frame.render_widget(
        Paragraph::new(format!("> {}", ui.ack))
            .style(Style::default().fg(theme.amber))
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
                ("●", theme.green)
            } else if set > 0 {
                ("◐", theme.amber)
            } else {
                ("○", theme.dim)
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
            .block(theme.block("CAPABILITIES", true))
            .highlight_style(
                Style::default()
                    .fg(theme.text)
                    .bg(if theme.mono { Color::Reset } else { theme.bg })
                    .add_modifier(Modifier::BOLD),
            )
            .highlight_symbol("▸ "),
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
    frame.render_widget(
        Gauge::default()
            .gauge_style(Style::default().fg(theme.purple).bg(theme.bg))
            .ratio(if total == 0 {
                0.0
            } else {
                set as f64 / total as f64
            })
            .label(format!("{set}/{total} keys stored")),
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
                if i == ui.selected_key { "▸ " } else { "  " },
                Style::default().fg(theme.amber),
            ),
            Span::styled(
                key.name.as_str(),
                Style::default()
                    .fg(if i == ui.selected_key {
                        theme.amber
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
            Line::from("GET THE KEY").style(Style::default().fg(theme.purple).bold()),
        ]);
        for (i, step) in key.steps.iter().enumerate() {
            lines.push(Line::from(format!("{}. {step}", i + 1)));
        }
        lines.extend([
            Line::default(),
            Line::from("UNLOCKS").style(Style::default().fg(theme.purple).bold()),
            Line::from(key.usage.clone()),
            Line::default(),
            Line::from("PERMISSIONS").style(Style::default().fg(theme.purple).bold()),
            Line::from(key.scope.clone()),
        ]);
        if !key.format.is_empty() {
            lines.extend([
                Line::default(),
                Line::from("EXPECTED FORMAT").style(Style::default().fg(theme.purple).bold()),
                Line::from(key.format.clone()),
            ]);
        }
    }
    lines.extend([
        Line::default(),
        Line::from("CONSOLE  [o]").style(Style::default().fg(theme.purple).bold()),
        Line::from(p.console.clone()).style(Style::default().fg(theme.dim)),
        Line::default(),
        Line::from("DOCUMENTATION  [d]").style(Style::default().fg(theme.purple).bold()),
        Line::from(p.docs.clone()).style(Style::default().fg(theme.dim)),
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
    let paragraph = Paragraph::new(Text::from(lines)).wrap(Wrap { trim: false });
    let total = paragraph.line_count(inner.width).min(u16::MAX as usize) as u16;
    ui.scroll = ui.scroll.min(total.saturating_sub(inner.height));
    frame.render_widget(paragraph.scroll((ui.scroll, 0)).block(block), cols[1]);
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
        "Input captured. No value is shown or copied.".into()
    };
    let text = vec![
        Line::from("One reusable key. Stored locally with mode 0600.")
            .style(Style::default().fg(theme.dim)),
        Line::default(),
        Line::from(format!("> {}", input.mask(mask_width))).style(Style::default().fg(theme.amber)),
        Line::from(format!("{} bytes entered", input.value.len()))
            .style(Style::default().fg(theme.dim)),
        Line::default(),
        Line::from(shape).style(Style::default().fg(theme.purple)),
        Line::default(),
        Line::from(notice).style(Style::default().fg(theme.amber)),
        Line::default(),
        Line::from("Enter save  ·  Esc keep existing  ·  Ctrl-U clear")
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
    let area = popup(frame.area(), 70, 18);
    frame.render_widget(Clear, area);
    frame.render_widget(Paragraph::new("↑ / ↓, j / k     Choose a provider\n← / →, Tab       Choose one of its keys\nEnter           Add or replace the selected key\nPgUp / PgDn     Read the provider guide\nHome            Return to the top of the guide\no / d           Open console / documentation\nr               Reload local key status\nq, Esc, Ctrl-C  Leave\n\nWhile entering a key: paste, type, Backspace,\nCtrl-U to clear, Enter to save, Esc to cancel.\n\nKeys are masked. Stored does not mean verified.\nAny key closes this panel.").wrap(Wrap{trim:false}).block(theme.block("CONTROLS",true)),area);
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
                        Line::from(label).style(Style::default().fg(theme.amber).bold()),
                        Line::default(),
                        Line::from(format!(
                            "> {}",
                            input.mask(popup.width.saturating_sub(7) as usize)
                        )),
                        Line::from(format!("{} bytes · hidden", input.value.len()))
                            .style(Style::default().fg(theme.dim)),
                        Line::from(notice.as_str()).style(Style::default().fg(theme.amber)),
                        Line::from("Enter save · Esc cancel · Ctrl-U clear")
                            .style(Style::default().fg(theme.dim)),
                    ])
                    .wrap(Wrap { trim: false })
                    .block(theme.block("GODMODE / CREDENTIAL", true)),
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
        let store = Store::new(
            "/demo/.config/godmode".into(),
            "/demo/.local/state/godmode/cli".into(),
        )
        .unwrap();
        let mut ui = Ui::new(true, &registry);
        ui.states[0][0] = KeyState::Set;
        ui.states[1][0] = KeyState::Set;
        ui.notice = "Ready. Choose a capability, add its key, and put your agents to work.".into();
        let theme = Theme {
            bg: Color::Rgb(12, 12, 20),
            panel: Color::Rgb(19, 19, 30),
            text: Color::Rgb(231, 230, 243),
            dim: Color::Rgb(139, 137, 163),
            purple: Color::Rgb(173, 136, 255),
            amber: Color::Rgb(255, 200, 109),
            green: Color::Rgb(118, 218, 181),
            red: Color::Rgb(255, 120, 135),
            mono: false,
        };
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
        for (kind, output) in [
            ("board", path.clone()),
            ("disclaimer", extension("disclaimer")),
            ("masked", extension("masked")),
        ] {
            ui.accepted = kind != "disclaimer";
            ui.editing = if kind == "masked" {
                let mut input = SecretInput::new();
                input
                    .push("SYNTHETIC_PREVIEW_CREDENTIAL_NEVER_RENDERED")
                    .unwrap();
                Some(input)
            } else {
                None
            };
            terminal
                .draw(|frame| draw(frame, &store, &registry, &mut ui, theme, true))
                .unwrap();
            let mut svg = format!(
                r##"<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}"><title>Godmode {} — rendered terminal UI preview with synthetic state</title><rect width="100%" height="100%" fill="#0c0c14"/><g font-family="Menlo,DejaVu Sans Mono,monospace" font-size="14">"##,
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
                            _ => fallback.to_string(),
                        }
                    };
                    let mut fg = rgb(cell.fg, "#e7e6f3");
                    let mut bg = rgb(cell.bg, "#0c0c14");
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
