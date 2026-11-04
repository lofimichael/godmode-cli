mod envfile;
mod output;
mod paths;
mod picard;
mod picard_visual;
mod registry;
mod setup;
mod store;
mod tui;

use clap::{Parser, Subcommand};
use envfile::Lookup;
use output::{Tone, paint};
use registry::Registry;
use std::{
    collections::BTreeSet,
    io::{self, IsTerminal, Read},
    path::PathBuf,
};
pub use store::Store;
use zeroize::Zeroizing;

#[derive(Parser)]
#[command(
    name = "godmode",
    version,
    about = "Set up provider credentials for local agents.",
    disable_help_subcommand = true,
    styles = output::clap_styles()
)]
struct Cli {
    /// Godmode home (default: ~/.godmode; existing ~/.config/godmode is detected)
    #[arg(long = "home", visible_alias = "config-dir", global = true)]
    config_dir: Option<PathBuf>,
    /// Local acknowledgements, writer locks and optional Picard cache
    #[arg(long, global = true)]
    state_dir: Option<PathBuf>,
    /// Disable terminal animation
    #[arg(long, global = true)]
    no_motion: bool,
    #[command(subcommand)]
    command: Option<Commands>,
}
#[derive(Subcommand)]
enum Commands {
    /// Optional YTMND Picard loop. Explicit play/stop; no autoplay
    Picard {
        #[command(subcommand)]
        action: Option<PicardCommand>,
    },
    /// Choose a provider and paste credentials into masked prompts
    Setup { provider: Option<String> },
    /// Open the full-screen provider board
    Onboard,
    /// Start interactive setup; --accept-disclaimer initializes without prompts
    Init {
        #[arg(long)]
        accept_disclaimer: bool,
    },
    /// Show key names and local presence, never values
    Status {
        #[arg(long)]
        json: bool,
    },
    /// Check local file safety and syntax; makes no provider requests
    Doctor {
        #[arg(long)]
        json: bool,
    },
    /// Save one literal key. Value comes from masked input, stdin, or a file, never argv
    Set {
        key: String,
        #[arg(long, conflicts_with = "from_file")]
        stdin: bool,
        #[arg(long)]
        from_file: Option<PathBuf>,
    },
    /// Remove a key while preserving all unrelated content
    Unset { key: String },
    /// Exit 0 only if every named key contains a usable value
    Has {
        #[arg(required=true,num_args=1..)]
        keys: Vec<String>,
    },
    /// Show setup instructions and scope for one provider
    Guide { provider: String },
    /// List the built-in and local-overlay provider catalog
    Providers {
        #[arg(long)]
        json: bool,
    },
    /// Print a TOML overlay template (no values)
    ProvidersTemplate,
    /// Run a child with only selected credentials and basic process environment
    Run {
        #[arg(long="with",required=true,action=clap::ArgAction::Append)]
        with: Vec<String>,
        #[arg(last=true,required=true,num_args=1..)]
        command: Vec<String>,
    },
}

#[derive(Subcommand)]
enum PicardCommand {
    /// Print the original Picard YTMND URL without opening a browser
    Link,
    /// Open the original Picard YTMND in your browser
    Open,
    /// Show the original Picard image in the terminal; audio starts only with p
    Show,
    /// Play the original ~8-second YTMND loop until stopped (foreground)
    Play,
    /// Stop Godmode's active player for this state directory
    Stop,
}

fn main() {
    // Panic payloads can contain values from third-party parsers; never display them.
    std::panic::set_hook(Box::new(|_| {
        ratatui::restore();
        eprintln!(
            "{}",
            output::paint_stderr(
                "godmode: unexpected error; credential details suppressed",
                Tone::Error
            )
        );
    }));
    let cli = match Cli::try_parse() {
        Ok(v) => v,
        Err(e) => {
            if matches!(
                e.kind(),
                clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion
            ) {
                let _ = e.print();
                std::process::exit(0);
            }
            eprintln!(
                "{}",
                output::paint_stderr(
                    "godmode: invalid arguments; use --help. Pass secrets through masked input, --stdin, or --from-file.",
                    Tone::Error
                )
            );
            std::process::exit(2);
        }
    };
    match execute(cli) {
        Ok(code) => std::process::exit(code),
        Err(message) => {
            eprintln!(
                "{}",
                output::paint_stderr(&format!("godmode: {message}"), Tone::Error)
            );
            std::process::exit(2);
        }
    }
}
fn execute(cli: Cli) -> Result<i32, String> {
    if let Some(Commands::Picard { action }) = &cli.command {
        match action {
            None | Some(PicardCommand::Link) => {
                println!("{}", paint(picard::SOURCE_URL, Tone::Link));
                if action.is_none() {
                    println!(
                        "Use `godmode picard show` for the picture, `play` for audio, or `stop` to stop audio."
                    );
                }
                return Ok(0);
            }
            Some(PicardCommand::Open) => {
                picard::open_source()?;
                println!("Opened {}", picard::SOURCE_URL);
                return Ok(0);
            }
            _ => {}
        }
    }
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .ok_or("HOME is not set; cannot resolve local directories")?;
    let requested_home = cli
        .config_dir
        .or_else(|| std::env::var_os("GODMODE_HOME").map(PathBuf::from))
        .or_else(|| std::env::var_os("GODMODE_CONFIG_DIR").map(PathBuf::from));
    let requested_state = cli
        .state_dir
        .or_else(|| std::env::var_os("GODMODE_STATE_DIR").map(PathBuf::from));
    let resolved = paths::resolve(&home, requested_home, requested_state)?;
    let store = Store::new(resolved.config_dir, resolved.state_dir)?;
    if let Some(Commands::Picard { action }) = &cli.command {
        match action {
            Some(PicardCommand::Show) => tui::show_picard(&store.state_dir)?,
            Some(PicardCommand::Play) => picard::play_foreground(&store.state_dir)?,
            Some(PicardCommand::Stop) => {
                println!(
                    "{}",
                    if picard::stop(&store.state_dir)? {
                        "Picard stopped."
                    } else {
                        "No Picard player is running."
                    }
                );
            }
            _ => unreachable!(),
        }
        return Ok(0);
    }
    let registry = Registry::load(&store.config_dir)?;
    match cli.command {
        Some(Commands::Picard { .. }) => unreachable!(),
        None if !io::stdin().is_terminal() || !io::stdout().is_terminal() => {
            if store.needs_setup()? {
                eprintln!(
                    "{}\n\nRun `godmode setup` in a terminal to begin.\n",
                    output::paint_stderr(store::FIRST_RUN_NOTICE, Tone::Warning)
                );
            }
            status(&store, &registry, false)
        }
        None | Some(Commands::Setup { provider: None }) => {
            setup::run(&store, &registry, None)?;
            Ok(0)
        }
        Some(Commands::Setup {
            provider: Some(provider),
        }) => {
            setup::run(&store, &registry, Some(&provider))?;
            Ok(0)
        }
        Some(Commands::Onboard) => {
            if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
                return Err("Onboarding needs a terminal; use init --accept-disclaimer and set --stdin for scripts".into());
            }
            if std::env::var("TERM").as_deref() == Ok("dumb") {
                return Err("Use `godmode setup` for prompts in a plain terminal".into());
            }
            tui::run(
                &store,
                &registry,
                cli.no_motion || std::env::var_os("GODMODE_NO_MOTION").is_some(),
            )?;
            Ok(0)
        }
        Some(Commands::Init { accept_disclaimer }) => {
            if !accept_disclaimer {
                if !io::stdin().is_terminal() {
                    if store.needs_setup()? {
                        eprintln!(
                            "{}\n",
                            output::paint_stderr(store::FIRST_RUN_NOTICE, Tone::Warning)
                        );
                    }
                    return Err("Read the disclaimer with interactive init, or explicitly pass --accept-disclaimer".into());
                }
                setup::run(&store, &registry, None)?;
                return Ok(if store.is_initialized() { 0 } else { 1 });
            }
            if store.needs_setup()? {
                eprintln!(
                    "{}\n",
                    output::paint_stderr(store::FIRST_RUN_NOTICE, Tone::Warning)
                );
            }
            store.acknowledge()?;
            println!(
                "Ready: {} (existing contents preserved)",
                paint(&store.env_path.display().to_string(), Tone::Success)
            );
            Ok(0)
        }
        Some(Commands::Status { json }) => status(&store, &registry, json),
        Some(Commands::Doctor { json }) => doctor(&store, json),
        Some(Commands::Set {
            key,
            stdin,
            from_file,
        }) => {
            store::valid_key(&key)?;
            if !store.is_initialized() {
                return Err("Run init before entering a credential".into());
            }
            let value = if let Some(path) = from_file {
                use std::os::unix::fs::OpenOptionsExt;
                let f = std::fs::OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_NONBLOCK)
                    .open(path)
                    .map_err(|_| "Cannot open credential input file")?;
                if !f
                    .metadata()
                    .map_err(|_| "Cannot inspect credential input file")?
                    .is_file()
                {
                    return Err("--from-file requires a regular file".into());
                }
                read_input(f)?
            } else if stdin {
                if io::stdin().is_terminal() {
                    return Err(
                        "--stdin requires a pipe or redirected file; omit it for masked entry"
                            .into(),
                    );
                }
                read_input(io::stdin())?
            } else {
                tui::prompt_secret(&key)?
            };
            store.set(&key, &value, &registry)?;
            println!(
                "{} {}; value hidden",
                paint("Saved", Tone::Success),
                paint(&key, Tone::Key)
            );
            Ok(0)
        }
        Some(Commands::Unset { key }) => {
            let removed = store.unset(&key)?;
            println!(
                "{}: {}",
                paint(&key, Tone::Key),
                paint(
                    if removed { "removed" } else { "absent" },
                    if removed { Tone::Success } else { Tone::Muted }
                )
            );
            Ok(0)
        }
        Some(Commands::Has { keys }) => {
            let file = store.load()?;
            let mut ok = true;
            for key in keys {
                store::valid_key(&key)?;
                let state = label(file.get(&key));
                println!(
                    "{}: {}",
                    paint(&key, Tone::Key),
                    paint(state, status_tone(state))
                );
                ok &= state == "set";
            }
            Ok(if ok { 0 } else { 1 })
        }
        Some(Commands::Providers { json }) => {
            if json {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&registry)
                        .map_err(|_| "Cannot serialize catalog")?
                );
            } else {
                for p in &registry.provider {
                    println!(
                        "{} {} — {}",
                        paint(&format!("{:<14}", p.id), Tone::Key),
                        paint(&p.name, Tone::Section),
                        p.purpose
                    );
                }
            }
            Ok(0)
        }
        Some(Commands::ProvidersTemplate) => {
            print!("{}", registry::TEMPLATE);
            Ok(0)
        }
        Some(Commands::Guide { provider }) => {
            let p = registry
                .provider
                .iter()
                .find(|p| p.id == provider)
                .ok_or("Unknown provider; use providers to list IDs")?;
            println!("{}\n{}\n", paint(&p.name, Tone::Title), p.purpose);
            for (label, url) in [
                ("Sign in:", p.login_url()),
                ("API keys:", p.console.as_str()),
                ("Docs:", p.docs.as_str()),
            ] {
                println!("{} {}", paint(label, Tone::Section), paint(url, Tone::Link));
            }
            for key in &p.key {
                println!(
                    "\n{}{}\n{} {}\n{} {}",
                    paint(&key.name, Tone::Key),
                    paint(if key.required { "" } else { " (optional)" }, Tone::Muted),
                    paint("Usage:", Tone::Section),
                    key.usage,
                    paint("Scope:", Tone::Section),
                    key.scope
                );
                for (i, step) in key.steps.iter().enumerate() {
                    println!("  {} {}", paint(&format!("{}.", i + 1), Tone::Accent), step);
                }
                if !key.format.is_empty() {
                    println!("{} {}", paint("Format hint:", Tone::Section), key.format);
                }
                if !key.verify.is_empty() {
                    println!(
                        "{} {}",
                        paint("Manual verification hint (not executed):", Tone::Section),
                        key.verify
                    );
                }
            }
            for note in &p.notes {
                println!("\n{} {note}", paint("Note:", Tone::Warning));
            }
            Ok(0)
        }
        Some(Commands::Run { with, command }) => store::run_selected(&store, &with, &command),
    }
}
fn read_input(input: impl Read) -> Result<Zeroizing<String>, String> {
    let mut bytes = Zeroizing::new(Vec::new());
    input
        .take(envfile::MAX_SIZE + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read credential input")?;
    if bytes.len() > envfile::MAX_SIZE as usize {
        return Err("Credential input exceeds size limit".into());
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| "Credential input is not UTF-8")?;
    let text = text
        .strip_suffix("\r\n")
        .or_else(|| text.strip_suffix('\n'))
        .unwrap_or(text);
    Ok(Zeroizing::new(text.to_owned()))
}
fn label(value: Lookup) -> &'static str {
    match value {
        Lookup::Present(_) => "set",
        Lookup::Blank => "blank",
        Lookup::Absent => "missing",
        Lookup::Duplicate(_) => "duplicate",
        Lookup::Malformed(_) => "malformed",
    }
}
fn status_tone(state: &str) -> Tone {
    match state {
        "set" => Tone::Success,
        "duplicate" | "malformed" => Tone::Error,
        _ => Tone::Warning,
    }
}
fn status(store: &Store, registry: &Registry, json: bool) -> Result<i32, String> {
    let file = store.load()?;
    let mut keys: BTreeSet<&str> = registry
        .provider
        .iter()
        .flat_map(|p| p.key.iter().map(|k| k.name.as_str()))
        .collect();
    keys.extend(file.keys());
    let entries: Vec<_> = keys
        .into_iter()
        .map(|k| serde_json::json!({"key":k,"status":label(file.get(k))}))
        .collect();
    if json {
        println!(
            "{}",
            serde_json::json!({"path":store.env_path,"initialized":store.is_initialized(),"verification":"local presence only; provider access not checked","keys":entries})
        );
    } else {
        println!(
            "{}\n{}",
            paint(&store.env_path.display().to_string(), Tone::Title),
            paint(
                "Local presence only — provider access not checked.",
                Tone::Muted
            )
        );
        for e in entries {
            println!(
                "{} {}",
                paint(
                    &format!("{:<44}", e["key"].as_str().unwrap_or_default()),
                    Tone::Key
                ),
                paint(
                    e["status"].as_str().unwrap_or_default(),
                    status_tone(e["status"].as_str().unwrap_or_default())
                )
            );
        }
    }
    Ok(0)
}
fn doctor(store: &Store, json: bool) -> Result<i32, String> {
    let mut issues = Vec::<String>::new();
    match envfile::inspect(&store.env_path, None) {
        Err(e) => issues.push(e.to_string()),
        Ok(facts) => {
            if !facts.exists {
                issues.push("Credential file does not exist; run init".into());
            } else if !facts.strict_ok() {
                issues.push("File must be an owned regular file, mode 0600, at most 1 MiB, with no symlink components".into());
            } else {
                match store.load() {
                    Err(e) => issues.push(e),
                    Ok(file) => {
                        let keys: BTreeSet<_> = file.keys().into_iter().collect();
                        for key in keys {
                            match file.get(key) {
                                Lookup::Duplicate(_) => {
                                    issues.push(format!("{key}: duplicate assignment"))
                                }
                                Lookup::Malformed(_) => {
                                    issues.push(format!("{key}: malformed assignment"))
                                }
                                _ => {}
                            }
                        }
                        if file
                            .lines()
                            .iter()
                            .any(|l| matches!(l, envfile::Line::Opaque(_)))
                        {
                            issues.push("Unrecognized lines found; inspect the file locally without sharing its contents".into());
                        }
                    }
                }
            }
        }
    }
    let ok = issues.is_empty();
    if json {
        println!(
            "{}",
            serde_json::json!({"ok":ok,"checks":"offline file safety and syntax only","issues":issues})
        );
    } else {
        println!(
            "{} — offline file safety and syntax; no provider requests",
            paint(
                if ok { "PASS" } else { "NEEDS ATTENTION" },
                if ok { Tone::Success } else { Tone::Error }
            )
        );
        for issue in issues {
            println!("  {} {issue}", paint("!", Tone::Error));
        }
    }
    Ok(if ok { 0 } else { 1 })
}
