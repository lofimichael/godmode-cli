#[allow(dead_code)]
#[path = "../src/envfile.rs"]
mod envfile;

use envfile::*;
use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::PathBuf;

fn fixture() -> (tempfile::TempDir, PathBuf) {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().canonicalize().unwrap().join(".env.godmode");
    (tmp, path)
}

#[test]
fn matches_python_shlex_vectors() {
    let vectors: serde_json::Value =
        serde_json::from_str(include_str!("shlex_vectors.json")).unwrap();
    for vector in vectors.as_array().unwrap() {
        let result = shlex_split(vector["raw"].as_str().unwrap());
        if let Some(error) = vector.get("error") {
            assert_eq!(result.unwrap_err().to_string(), error.as_str().unwrap());
        } else {
            let expected: Vec<String> = serde_json::from_value(vector["tokens"].clone()).unwrap();
            assert_eq!(result.unwrap(), expected);
        }
    }
}

#[test]
fn preserves_untouched_bytes_and_mixed_endings() {
    for original in [
        "",
        "\n",
        "# comment\r\n \nexport TOKEN = 'a b'  # note\r\nOPAQUE TEXT\nLAST=z",
        "K=a\r",
        "K=a\n",
        " K=first#bare\n",
    ] {
        assert_eq!(EnvFile::parse(original).render(), original);
    }
}

#[test]
fn replaces_deduplicates_and_preserves_other_lines() {
    let mut file = EnvFile::parse(
        "# mine\r\n export KEY = old  # scope\nOTHER='untouched'\r\nKEY=duplicate\n",
    );
    assert_eq!(
        file.set("KEY", "new", None).unwrap(),
        SetOutcome::ReplacedAndDeduplicated(1)
    );
    assert_eq!(
        file.render(),
        "# mine\r\n export KEY = 'new'  # scope\nOTHER='untouched'\r\n"
    );
    assert!(matches!(file.get("KEY"), Lookup::Present(v) if *v == "new"));
    assert_eq!(file.unset("KEY"), 1);
    assert_eq!(file.render(), "# mine\r\nOTHER='untouched'\r\n");
}

#[test]
fn appends_without_concatenating_unterminated_lines() {
    let mut file = EnvFile::parse("# owner\r\nA=x");
    file.set("NEW_API_KEY", "new value", Some("Custom"))
        .unwrap();
    assert_eq!(
        file.render(),
        "# owner\r\nA=x\r\n# Custom\r\nNEW_API_KEY='new value'\r\n"
    );
    file.set("EXTRA", "x", Some("Custom")).unwrap();
    assert_eq!(file.render().matches("# Custom").count(), 1);
}

#[test]
fn errors_and_debug_never_render_values() {
    let sentinel = "sensitive-sentinel-very-private";
    let file = EnvFile::parse(&format!("KEY='{sentinel}'\n{sentinel}\n# {sentinel}\n"));
    assert!(!format!("{file:?}").contains(sentinel));
    assert!(!format!("{:?}", file.get("KEY")).contains(sentinel));
    assert!(!format!("{:?}", file.lines()).contains(sentinel));
    assert!(
        !EnvError::InvalidKey(sentinel.into())
            .to_string()
            .contains(sentinel)
    );
    assert!(!format!("{:?}", EnvError::InvalidKey(sentinel.into())).contains(sentinel));
}

#[test]
fn rejects_control_and_invalid_key_without_changing_file() {
    let mut file = EnvFile::parse("KEEP=original\n");
    for value in [
        "a\nb",
        "a\rb",
        "a\0b",
        "a\x1bb",
        "a\tb",
        "a\u{2028}b",
        "a\u{2029}b",
    ] {
        assert!(file.set("KEY", value, None).is_err());
        assert_eq!(file.render(), "KEEP=original\n");
    }
    for name in ["", "1KEY", "A-B", "KEY=value", "A B"] {
        assert!(file.set(name, "anything", None).is_err());
    }
    assert!(file.set("KEY", "anything", Some("bad\nsection")).is_err());
}

#[test]
fn lookup_reports_missing_blank_duplicate_malformed() {
    let file = EnvFile::parse(
        "EMPTY=\nQUOTED=''\nDUPE=first\nDUPE=second\nBROKEN='unclosed\nMULTI=a b\nGOOD='one value'\n",
    );
    assert!(matches!(file.get("ABSENT"), Lookup::Absent));
    assert!(matches!(file.get("EMPTY"), Lookup::Blank));
    assert!(matches!(file.get("QUOTED"), Lookup::Blank));
    assert!(matches!(file.get("DUPE"), Lookup::Duplicate(2)));
    assert!(matches!(file.get("BROKEN"), Lookup::Malformed(_)));
    assert!(matches!(file.get("MULTI"), Lookup::Malformed(_)));
    assert!(matches!(file.get("GOOD"), Lookup::Present(v) if *v == "one value"));
}

#[test]
fn all_quoted_values_round_trip_and_never_expand() {
    for value in [
        "plain",
        "",
        "a'b",
        "a\"b",
        "a b",
        "$HOME",
        "$(touch /tmp/should-never-execute)",
        "`echo surprise`",
        "a#b",
        "a\\b",
        "中文☃",
        "{\"private_key\":\"fake\\nvalue\"}",
    ] {
        let raw = quote_value(value);
        assert_eq!(shlex_split(&raw).unwrap(), vec![value]);
        // The conditional-shlex reader must see the same value too.
        let legacy = if raw.starts_with(['\'', '"']) {
            shlex_split(&raw).unwrap()[0].clone()
        } else {
            raw
        };
        assert_eq!(legacy, value);
    }
}

#[test]
fn private_creation_is_idempotent_and_never_overwrites() {
    let (_tmp, path) = fixture();
    assert!(create_empty(&path).unwrap());
    assert_eq!(fs::read_to_string(&path).unwrap(), NEW_FILE_HEADER);
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
    write_atomic(&path, "KEEP=original\n", None).unwrap();
    assert!(!create_empty(&path).unwrap());
    assert_eq!(fs::read_to_string(&path).unwrap(), "KEEP=original\n");
    assert!(read(&path, None, true).unwrap().facts.strict_ok());
}

#[test]
fn private_atomic_update_cleans_temporary_files() {
    let (tmp, path) = fixture();
    create_empty(&path).unwrap();
    let state = tmp.path().canonicalize().unwrap().join("state");
    fs::create_dir(&state).unwrap();
    fs::set_permissions(&state, fs::Permissions::from_mode(0o700)).unwrap();
    write_atomic(&path, "KEY='new value'\n", Some(&state)).unwrap();
    assert_eq!(fs::read_to_string(&path).unwrap(), "KEY='new value'\n");
    assert_eq!(fs::read_dir(&state).unwrap().count(), 0);
    assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 2);
}

#[test]
fn refuses_insecure_mode_symlinks_directories_and_oversize() {
    let (_tmp, path) = fixture();
    create_empty(&path).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
    assert!(matches!(
        read(&path, None, true),
        Err(EnvError::BadMode(_, _))
    ));
    assert!(read(&path, None, false).is_ok());
    assert!(write_atomic(&path, "X=y\n", None).is_err());
    assert!(create_empty(&path).is_err());
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    let link = path.with_file_name("link");
    symlink(&path, &link).unwrap();
    assert!(matches!(read(&link, None, true), Err(EnvError::Symlink(_))));
    assert!(write_atomic(&link, "X=y\n", None).is_err());
    let dir = path.with_file_name("dir");
    fs::create_dir(&dir).unwrap();
    assert!(matches!(
        read(&dir, None, true),
        Err(EnvError::NotRegular(_))
    ));
    assert!(write_atomic(&dir, "X=y\n", None).is_err());
    let original = fs::read(&path).unwrap();
    assert!(write_atomic(&path, &"x".repeat(MAX_SIZE as usize + 1), None).is_err());
    assert_eq!(fs::read(&path).unwrap(), original);
    fs::write(&path, vec![b'x'; MAX_SIZE as usize + 1]).unwrap();
    assert!(matches!(
        read(&path, None, true),
        Err(EnvError::TooLarge(_, _))
    ));
}

#[test]
fn refuses_symlinked_parents_and_parent_traversal() {
    let (_tmp, path) = fixture();
    create_empty(&path).unwrap();
    let parent_dir = path.parent().unwrap();
    let link = parent_dir.join("alias");
    symlink(parent_dir, &link).unwrap();
    let redirected = link.join(".env.godmode");
    assert!(read(&redirected, None, true).is_err());
    assert!(write_atomic(&redirected, "BAD=x\n", None).is_err());
    assert!(create_empty(&link.join("new")).is_err());
    assert!(read(&link.join("..").join(".env.godmode"), None, true).is_err());
    assert_eq!(fs::read_to_string(&path).unwrap(), NEW_FILE_HEADER);
}

#[test]
fn invalid_utf8_never_becomes_lossy_credential() {
    let (_tmp, path) = fixture();
    create_empty(&path).unwrap();
    fs::write(&path, [0xff, 0xfe]).unwrap();
    assert!(matches!(read(&path, None, true), Err(EnvError::NotUtf8(_))));
}

#[test]
fn differential_against_python_shlex_with_5000_inputs() {
    let script = r#"
import json, random, shlex
r = random.Random(538)
chars = "ab \t\n\r'\"\\#$;é☃\0"
out = []
for _ in range(5000):
    raw = ''.join(r.choice(chars) for _ in range(r.randrange(0, 45)))
    try: out.append({'raw':raw, 'tokens':shlex.split(raw, comments=True, posix=True)})
    except ValueError as e: out.append({'raw':raw, 'error':str(e)})
print(json.dumps(out))
"#;
    let output = std::process::Command::new("python3")
        .args(["-c", script])
        .output()
        .expect("Python 3 is required for differential compatibility tests");
    assert!(output.status.success());
    let vectors: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    for (i, vector) in vectors.as_array().unwrap().iter().enumerate() {
        let result = shlex_split(vector["raw"].as_str().unwrap());
        if let Some(error) = vector.get("error") {
            assert_eq!(
                result.unwrap_err().to_string(),
                error.as_str().unwrap(),
                "vector {i}"
            );
        } else {
            let expected: Vec<String> = serde_json::from_value(vector["tokens"].clone()).unwrap();
            assert_eq!(result.unwrap(), expected, "vector {i}");
        }
    }
}

#[test]
fn escaped_space_before_comment_remains_part_of_value() {
    let mut file = EnvFile::parse("KEY=a\\ #comment\n");
    assert!(matches!(file.get("KEY"), Lookup::Present(v) if *v == "a "));
    file.set("KEY", "new", None).unwrap();
    assert!(matches!(file.get("KEY"), Lookup::Present(v) if *v == "new"));
    let mut adjacent = EnvFile::parse("KEY=a#comment\n");
    adjacent.set("KEY", "new", None).unwrap();
    assert_eq!(adjacent.render(), "KEY='new' #comment\n");
}

#[test]
fn destination_directory_lock_blocks_independent_writers_and_releases() {
    let (_tmp, path) = fixture();
    let config = path.parent().unwrap();
    let first = lock_directory(config).unwrap();
    assert!(lock_directory(config).is_err());
    drop(first);
    assert!(lock_directory(config).is_ok());
    fs::set_permissions(config, fs::Permissions::from_mode(0o777)).unwrap();
    assert!(lock_directory(config).is_err());
    fs::set_permissions(config, fs::Permissions::from_mode(0o700)).unwrap();
}
