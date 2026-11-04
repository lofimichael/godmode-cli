//! Locate a Godmode home without moving or creating anything.

use std::{
    fs,
    io::ErrorKind,
    path::{Path, PathBuf},
};

pub struct Paths {
    pub config_dir: PathBuf,
    pub state_dir: PathBuf,
}

/// A bin-only installation is not a configured home. Metadata checks include
/// dangling symlinks so discovery does not silently bypass an existing home.
/// Each file is validated by the component that actually opens it.
pub(crate) fn has_configuration(path: &Path) -> Result<bool, String> {
    for name in [".env.godmode", "AGENTS.md", "providers.toml"] {
        match fs::symlink_metadata(path.join(name)) {
            Ok(_) => return Ok(true),
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Err(_) => return Err("Cannot inspect the Godmode configuration directory".into()),
        }
    }
    Ok(false)
}

/// An explicit home always wins. Automatic discovery adopts the new home only
/// once it contains configuration; otherwise it preserves an existing legacy
/// location and its existing acknowledgement state. No files are migrated.
pub fn resolve(
    user_home: &Path,
    requested_home: Option<PathBuf>,
    requested_state: Option<PathBuf>,
) -> Result<Paths, String> {
    let (config_dir, default_state) = if let Some(home) = requested_home {
        let state = home.join("state");
        (home, state)
    } else {
        let home = user_home.join(".godmode");
        let legacy = user_home.join(".config/godmode");
        if has_configuration(&home)? {
            let state = home.join("state");
            (home, state)
        } else {
            match fs::symlink_metadata(&legacy) {
                // Preserve discovery even for an unsafe existing type. Store
                // validation, not fallback discovery, reports that problem.
                Ok(_) => (legacy, user_home.join(".local/state/godmode/cli")),
                Err(error) if error.kind() == ErrorKind::NotFound => {
                    let state = home.join("state");
                    (home, state)
                }
                Err(_) => return Err("Cannot inspect the existing Godmode directory".into()),
            }
        }
    };
    Ok(Paths {
        config_dir,
        state_dir: requested_state.unwrap_or(default_state),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fresh_machine_uses_one_home_without_creating_it() {
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path().join("user");
        let paths = resolve(&home, None, None).unwrap();
        assert_eq!(paths.config_dir, home.join(".godmode"));
        assert_eq!(paths.state_dir, home.join(".godmode/state"));
        assert!(!home.exists());
    }

    #[test]
    fn bin_only_new_home_preserves_legacy_config_and_state() {
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path();
        let legacy = home.join(".config/godmode");
        fs::create_dir_all(&legacy).unwrap();
        fs::write(legacy.join(".env.godmode"), "SYNTHETIC=unchanged\n").unwrap();
        fs::create_dir_all(home.join(".godmode/bin")).unwrap();
        fs::write(home.join(".godmode/bin/godmode"), "synthetic binary").unwrap();
        let paths = resolve(home, None, None).unwrap();
        assert_eq!(paths.config_dir, legacy);
        assert_eq!(paths.state_dir, home.join(".local/state/godmode/cli"));
        assert_eq!(
            fs::read_to_string(legacy.join(".env.godmode")).unwrap(),
            "SYNTHETIC=unchanged\n"
        );
    }

    #[test]
    fn each_new_home_marker_takes_precedence_over_legacy() {
        for marker in [".env.godmode", "AGENTS.md", "providers.toml"] {
            let temp = tempfile::tempdir().unwrap();
            let home = temp.path();
            fs::create_dir_all(home.join(".config/godmode")).unwrap();
            fs::create_dir_all(home.join(".godmode")).unwrap();
            fs::write(home.join(".godmode").join(marker), "synthetic").unwrap();
            let paths = resolve(home, None, None).unwrap();
            assert_eq!(paths.config_dir, home.join(".godmode"));
            assert_eq!(paths.state_dir, home.join(".godmode/state"));
        }
    }

    #[test]
    fn explicit_home_and_state_override_discovery() {
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path();
        fs::create_dir_all(home.join(".config/godmode")).unwrap();
        let explicit = home.join("elsewhere");
        let paths = resolve(home, Some(explicit.clone()), None).unwrap();
        assert_eq!(paths.config_dir, explicit);
        assert_eq!(paths.state_dir, explicit.join("state"));
        let state = home.join("separate-state");
        let paths = resolve(home, Some(explicit.clone()), Some(state.clone())).unwrap();
        assert_eq!(paths.config_dir, explicit);
        assert_eq!(paths.state_dir, state);
        assert!(!explicit.exists());
    }

    #[test]
    fn symlink_markers_and_existing_unsafe_legacy_are_not_hidden() {
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path();
        fs::create_dir_all(home.join(".godmode")).unwrap();
        std::os::unix::fs::symlink(home.join("absent"), home.join(".godmode/AGENTS.md")).unwrap();
        assert!(has_configuration(&home.join(".godmode")).unwrap());
        assert_eq!(
            resolve(home, None, None).unwrap().config_dir,
            home.join(".godmode")
        );
        fs::remove_file(home.join(".godmode/AGENTS.md")).unwrap();
        fs::create_dir_all(home.join(".config")).unwrap();
        fs::write(home.join(".config/godmode"), "not a directory").unwrap();
        assert_eq!(
            resolve(home, None, None).unwrap().config_dir,
            home.join(".config/godmode")
        );
        assert!(has_configuration(&home.join(".config/godmode")).is_err());
    }
}
