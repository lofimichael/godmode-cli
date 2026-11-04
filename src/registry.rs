use serde::{Deserialize, Serialize};
use std::{collections::HashSet, path::Path};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Registry {
    pub schema: u32,
    #[serde(default)]
    pub provider: Vec<Provider>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Provider {
    pub id: String,
    pub name: String,
    pub purpose: String,
    pub console: String,
    pub docs: String,
    #[serde(default)]
    pub notes: Vec<String>,
    pub key: Vec<Key>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Key {
    pub name: String,
    #[serde(default = "secret_kind")]
    pub kind: String,
    #[serde(default)]
    pub required: bool,
    pub usage: String,
    pub scope: String,
    #[serde(default)]
    pub steps: Vec<String>,
    #[serde(default)]
    pub format: String,
    #[serde(default)]
    pub verify: String,
    #[serde(default)]
    pub prefixes: Vec<String>,
    #[serde(default)]
    pub forbid_prefixes: Vec<String>,
    #[serde(default)]
    pub json: bool,
}

fn secret_kind() -> String {
    "secret".into()
}

impl Registry {
    pub fn load(config: &Path) -> Result<Self, String> {
        let mut registry: Self = toml::from_str(include_str!("../registry/providers.toml"))
            .map_err(|_| "Bundled provider catalog is invalid".to_string())?;
        let explicit = std::env::var_os("GODMODE_REGISTRY");
        let overlay = explicit
            .as_ref()
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| config.join("providers.toml"));
        if explicit.is_some() || overlay.exists() {
            let metadata =
                std::fs::metadata(&overlay).map_err(|_| "Cannot read provider overlay")?;
            if metadata.len() > 1_048_576 || !metadata.is_file() {
                return Err("Invalid provider overlay size or type".into());
            }
            let source =
                std::fs::read_to_string(&overlay).map_err(|_| "Cannot read provider overlay")?;
            let extra: Self = toml::from_str(&source).map_err(|_| "Invalid provider TOML (details suppressed; never put credentials in the catalog)")?;
            extra.validate()?;
            for p in extra.provider {
                if let Some(i) = registry.provider.iter().position(|v| v.id == p.id) {
                    registry.provider[i] = p;
                } else {
                    registry.provider.push(p);
                }
            }
        }
        registry.validate()?;
        Ok(registry)
    }

    pub fn find_key(&self, name: &str) -> Option<&Key> {
        self.provider
            .iter()
            .flat_map(|p| &p.key)
            .find(|k| k.name == name)
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema != 1 {
            return Err("Unsupported provider schema; expected schema = 1".into());
        }
        let mut ids = HashSet::new();
        let mut keys = HashSet::new();
        for p in &self.provider {
            if p.id.is_empty()
                || !p
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                || !ids.insert(&p.id)
            {
                return Err("Provider IDs must be unique lowercase slugs".into());
            }
            for url in [&p.console, &p.docs] {
                if !url.starts_with("https://")
                    || url.chars().any(char::is_whitespace)
                    || url.chars().any(char::is_control)
                {
                    return Err("Provider links must be HTTPS without whitespace".into());
                }
            }
            let safe = |s: &str| !s.chars().any(|c| c.is_control() && c != '\n' && c != '\t');
            if ![&p.name, &p.purpose].into_iter().all(|s| safe(s))
                || !p.notes.iter().all(|s| safe(s))
            {
                return Err("Control codes in provider catalog".into());
            }
            if p.key.is_empty() {
                return Err("Each provider needs at least one key".into());
            }
            for k in &p.key {
                if !crate::envfile::is_valid_key(&k.name) || !keys.insert(&k.name) {
                    return Err("Catalog keys must be valid and unique".into());
                }
                if ![&k.kind, &k.usage, &k.scope, &k.format, &k.verify]
                    .into_iter()
                    .all(|s| safe(s))
                    || !k
                        .steps
                        .iter()
                        .chain(&k.prefixes)
                        .chain(&k.forbid_prefixes)
                        .all(|s| safe(s))
                {
                    return Err("Control codes in key metadata".into());
                }
            }
        }
        Ok(())
    }
}

pub const TEMPLATE: &str = r#"schema = 1

[[provider]]
id = "example"
name = "Example"
purpose = "Describe what your agents can do with this provider"
console = "https://example.com/settings/tokens"
docs = "https://example.com/docs/auth"

[[provider.key]]
name = "EXAMPLE_ACCOUNT_ADMIN_TOKEN"
kind = "secret"
required = true
usage = "Administer the operator's projects"
scope = "Account scope; choose the permissions your tasks require"
steps = ["Open the token page", "Create a token", "Paste it into Godmode"]
"#;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bundled_and_template_are_valid() {
        let r: Registry = toml::from_str(include_str!("../registry/providers.toml")).unwrap();
        r.validate().unwrap();
        let r: Registry = toml::from_str(TEMPLATE).unwrap();
        r.validate().unwrap();
    }
}
