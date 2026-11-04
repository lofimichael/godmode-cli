mod envfile;
mod picard;
mod registry;
mod store;
mod tui;

use clap::{Parser, Subcommand};
use envfile::Lookup;
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
    about = "Hand your agents the keys. Try not to fucking pwn yourself.",
    disable_help_subcommand = true
)]
struct Cli {
    /// Credential directory (default: ~/.config/godmode). Does not install or replace rules.
    #[arg(long, global = true)]
    config_dir: Option<PathBuf>,
    /// Local acknowledgement and writer-lock directory
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
    /// Open the interactive provider board
    Onboard,
    /// Acknowledge the disclaimer; create the credential file only if absent
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
    /// Play the original ~8-second YTMND loop until stopped (foreground)
    Play,
    /// Stop Godmode's active player for this state directory
    Stop,
}

fn main() {
    // Panic payloads can contain values from third-party parsers; never display them.
    std::panic::set_hook(Box::new(|_| {
        ratatui::restore();
        eprintln!("godmode: unexpected error; credential details suppressed");
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
                "godmode: invalid arguments; use --help. Pass secrets through masked input, --stdin, or --from-file."
            );
            std::process::exit(2);
        }
    };
    match execute(cli) {
        Ok(code) => std::process::exit(code),
        Err(message) => {
            eprintln!("godmode: {message}");
            std::process::exit(2);
        }
    }
}
fn execute(cli: Cli) -> Result<i32, String> {
    if let Some(Commands::Picard { action }) = &cli.command {
        match action {
            None | Some(PicardCommand::Link) => {
                println!("{}", picard::SOURCE_URL);
                if action.is_none() {
                    println!(
                        "Picard mode: `godmode picard play` / `godmode picard stop`. No autoplay. You're welcome."
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
    let config = cli
        .config_dir
        .or_else(|| std::env::var_os("GODMODE_CONFIG_DIR").map(PathBuf::from))
        .unwrap_or_else(|| home.join(".config/godmode"));
    let state = cli
        .state_dir
        .or_else(|| std::env::var_os("GODMODE_STATE_DIR").map(PathBuf::from))
        .unwrap_or_else(|| home.join(".local/state/godmode/cli"));
    let store = Store::new(config, state)?;
    if let Some(Commands::Picard { action }) = &cli.command {
        match action {
            Some(PicardCommand::Play) => {
                println!(
                    "PICARD MODE / original YTMND loop. Ctrl-C or `godmode picard stop` to stop."
                );
                picard::play_foreground(&store.state_dir)?;
            }
            Some(PicardCommand::Stop) => {
                println!(
                    "{}",
                    if picard::stop(&store.state_dir)? {
                        "Picard stopped. Back to your regularly scheduled shit."
                    } else {
                        "Picard is already quiet."
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
        None if !io::stdin().is_terminal()
            || !io::stdout().is_terminal()
            || std::env::var("TERM").as_deref() == Ok("dumb") =>
        {
            status(&store, &registry, false)
        }
        None | Some(Commands::Onboard) => {
            if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
                return Err("Onboarding needs a terminal; use init --accept-disclaimer and set --stdin for scripts".into());
            }
            if std::env::var("TERM").as_deref() == Ok("dumb") {
                return Err("Use init, providers, guide and set in a plain terminal".into());
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
                    return Err("Read the disclaimer with interactive init, or explicitly pass --accept-disclaimer".into());
                }
                tui::run(&store, &registry, cli.no_motion)?;
                return Ok(if store.is_initialized() { 0 } else { 1 });
            }
            store.acknowledge()?;
            println!(
                "Ready: {} (existing contents preserved)",
                store.env_path.display()
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
            println!("Saved {key}; value hidden");
            Ok(0)
        }
        Some(Commands::Unset { key }) => {
            let removed = store.unset(&key)?;
            println!("{key}: {}", if removed { "removed" } else { "absent" });
            Ok(0)
        }
        Some(Commands::Has { keys }) => {
            let file = store.load()?;
            let mut ok = true;
            for key in keys {
                store::valid_key(&key)?;
                let state = label(file.get(&key));
                println!("{key}: {state}");
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
                    println!("{:<14} {} — {}", p.id, p.name, p.purpose);
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
            println!(
                "{}\n{}\n\nConsole: {}\nDocs: {}",
                p.name, p.purpose, p.console, p.docs
            );
            for key in &p.key {
                println!(
                    "\n{}{}\nUsage: {}\nScope: {}",
                    key.name,
                    if key.required { "" } else { " (optional)" },
                    key.usage,
                    key.scope
                );
                for (i, step) in key.steps.iter().enumerate() {
                    println!("  {}. {}", i + 1, step);
                }
                if !key.format.is_empty() {
                    println!("Format hint: {}", key.format);
                }
                if !key.verify.is_empty() {
                    println!("Manual verification hint (not executed): {}", key.verify);
                }
            }
            for note in &p.notes {
                println!("\n{note}");
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
            "{}\nLocal presence only — provider access not checked.",
            store.env_path.display()
        );
        for e in entries {
            println!(
                "{:<44} {}",
                e["key"].as_str().unwrap_or_default(),
                e["status"].as_str().unwrap_or_default()
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
            if ok { "PASS" } else { "NEEDS ATTENTION" }
        );
        for issue in issues {
            println!("  {issue}");
        }
    }
    Ok(if ok { 0 } else { 1 })
}
