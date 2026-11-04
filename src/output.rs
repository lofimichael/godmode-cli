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

fn permitted() -> bool {
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
    let code = match tone {
        Tone::Title => "1;96",
        Tone::Section => "1;95",
        Tone::Key => "1;93",
        Tone::Link => "4;96",
        Tone::Success => "1;92",
        Tone::Warning => "1;93",
        Tone::Error => "1;91",
        Tone::Muted => "90",
        Tone::Accent => "1;94",
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
    use clap::builder::styling::{AnsiColor, Styles};
    if !permitted() {
        return Styles::plain();
    }
    Styles::styled()
        .header(AnsiColor::BrightMagenta.on_default().bold())
        .usage(AnsiColor::BrightCyan.on_default().bold())
        .literal(AnsiColor::BrightCyan.on_default().bold())
        .placeholder(AnsiColor::BrightYellow.on_default())
        .error(AnsiColor::BrightRed.on_default().bold())
        .valid(AnsiColor::BrightGreen.on_default())
        .invalid(AnsiColor::BrightRed.on_default())
}
