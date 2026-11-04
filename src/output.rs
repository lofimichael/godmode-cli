//! Semantic color for human-readable output. JSON and redirected text stay plain.
use std::io::{self, IsTerminal};

#[derive(Clone, Copy)]
pub enum Tone {
    Title,
    Section,
    Key,
    Link,
    Success,
    Warning,
    Error,
    Muted,
    Accent,
}

pub(crate) fn permitted() -> bool {
    std::env::var_os("NO_COLOR").is_none()
        && std::env::var("CLICOLOR").as_deref() != Ok("0")
        && std::env::var("TERM").as_deref() != Ok("dumb")
}

pub fn enabled() -> bool {
    io::stdout().is_terminal() && permitted()
}

fn render(text: &str, tone: Tone, color: bool) -> String {
    if !color {
        return text.to_owned();
    }
    // Let the terminal choose readable body colors for its light or dark theme.
    // Only interactive accents and actual status need a color of their own.
    let code = match tone {
        Tone::Title | Tone::Section => "1",
        Tone::Key | Tone::Muted => return text.to_owned(),
        Tone::Link => "4;36",
        Tone::Success => "32",
        Tone::Warning => "33",
        Tone::Error => "1;31",
        Tone::Accent => "36",
    };
    format!("\x1b[{code}m{text}\x1b[0m")
}

pub fn paint(text: &str, tone: Tone) -> String {
    render(text, tone, enabled())
}

pub fn paint_stderr(text: &str, tone: Tone) -> String {
    render(text, tone, io::stderr().is_terminal() && permitted())
}

pub fn clap_styles() -> clap::builder::Styles {
    use clap::builder::styling::{AnsiColor, Style, Styles};
    if !permitted() {
        return Styles::plain();
    }
    Styles::styled()
        .header(Style::new().bold())
        .usage(Style::new().bold())
        .literal(AnsiColor::Cyan.on_default())
        .placeholder(Style::new())
        .error(AnsiColor::Red.on_default().bold())
        .valid(AnsiColor::Green.on_default())
        .invalid(AnsiColor::Red.on_default())
}
