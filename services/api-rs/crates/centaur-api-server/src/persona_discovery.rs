use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

use toml::Value as TomlValue;
use tracing::warn;

use crate::types::{ListPersonasResponse, PersonaRecord};

pub(crate) fn discover_personas() -> ListPersonasResponse {
    let roots = match persona_roots() {
        Ok(roots) => roots,
        Err(error) => {
            warn!(%error, "failed to resolve persona roots");
            return BTreeMap::new();
        }
    };
    discover_personas_in_dirs(&roots)
}

fn persona_roots() -> Result<Vec<PathBuf>, String> {
    if let Some(tool_dirs) = clean_env("TOOL_DIRS") {
        return Ok(split_tool_dirs(&tool_dirs));
    }

    let mut sandbox_style_dirs = Vec::new();
    if let Some(path) = clean_env_path("TOOLS_PATH") {
        sandbox_style_dirs.push(path);
    }
    if let Some(path) = clean_env_path("TOOLS_OVERLAY_PATH") {
        sandbox_style_dirs.push(path);
    }
    if !sandbox_style_dirs.is_empty() {
        return Ok(sandbox_style_dirs);
    }

    if let Some(config_path) = clean_env_path("TOOLS_CONFIG").or_else(default_tools_config) {
        let dirs = load_plugins_config(&config_path)?;
        if !dirs.is_empty() {
            return Ok(dirs);
        }
    }

    if let Some(path) = clean_env_path("PLUGINS_DIR") {
        return Ok(vec![path]);
    }

    let root = default_repo_root().unwrap_or_else(|| {
        env::current_dir()
            .ok()
            .unwrap_or_else(|| PathBuf::from("."))
    });
    Ok(vec![root.join("tools")])
}

fn discover_personas_in_dirs(roots: &[PathBuf]) -> ListPersonasResponse {
    let mut personas = BTreeMap::new();
    for root in roots {
        collect_personas(root, &mut personas);
    }
    personas
}

fn collect_personas(root: &Path, personas: &mut ListPersonasResponse) {
    if !root.exists() {
        return;
    }
    let Ok(children) = read_dirs_sorted(root) else {
        warn!(root = %root.display(), "failed to read persona root");
        return;
    };
    for child in children {
        if child.join("pyproject.toml").exists() {
            insert_persona(&child, personas);
            continue;
        }
        let Ok(grandchildren) = read_dirs_sorted(&child) else {
            warn!(path = %child.display(), "failed to read persona category");
            continue;
        };
        for grandchild in grandchildren {
            if grandchild.join("pyproject.toml").exists() {
                insert_persona(&grandchild, personas);
            }
        }
    }
}

fn insert_persona(path: &Path, personas: &mut ListPersonasResponse) {
    let Some((name, persona)) = load_persona(path) else {
        return;
    };
    personas.insert(name, persona);
}

fn load_persona(path: &Path) -> Option<(String, PersonaRecord)> {
    let pyproject_path = path.join("pyproject.toml");
    let pyproject = fs::read_to_string(&pyproject_path).ok()?;
    let pyproject: TomlValue = match toml::from_str(&pyproject) {
        Ok(value) => value,
        Err(error) => {
            warn!(path = %pyproject_path.display(), %error, "failed to parse persona pyproject");
            return None;
        }
    };
    let project = pyproject.get("project");
    let centaur = pyproject.get("tool")?.get("centaur")?;
    if centaur.get("type")?.as_str()? != "persona" {
        return None;
    }
    let name = path.file_name()?.to_str()?.to_owned();
    let description = project
        .and_then(|value| value.get("description"))
        .and_then(TomlValue::as_str)
        .unwrap_or("")
        .to_owned();
    let engine = centaur
        .get("engine")
        .and_then(TomlValue::as_str)
        .unwrap_or("amp")
        .to_owned();
    let default_repo = centaur
        .get("default_repo")
        .and_then(TomlValue::as_str)
        .map(ToOwned::to_owned);

    Some((
        name,
        PersonaRecord {
            description,
            engine,
            default_repo,
            has_custom_executor: path.join("run.py").exists(),
        },
    ))
}

fn load_plugins_config(config_path: &Path) -> Result<Vec<PathBuf>, String> {
    if !config_path.exists() {
        return Ok(Vec::new());
    }
    let contents = fs::read_to_string(config_path)
        .map_err(|error| format!("failed to read {}: {error}", config_path.display()))?;
    let data: TomlValue = toml::from_str(&contents)
        .map_err(|error| format!("failed to parse {}: {error}", config_path.display()))?;
    let base = config_path.parent().unwrap_or_else(|| Path::new("."));
    Ok(data
        .get("plugin_dirs")
        .and_then(TomlValue::as_array)
        .map(|entries| {
            entries
                .iter()
                .filter_map(TomlValue::as_str)
                .map(|entry| {
                    let path = PathBuf::from(entry);
                    if path.is_absolute() {
                        path
                    } else {
                        base.join(path)
                    }
                })
                .collect()
        })
        .unwrap_or_default())
}

fn read_dirs_sorted(path: &Path) -> Result<Vec<PathBuf>, std::io::Error> {
    let mut dirs = fs::read_dir(path)?
        .filter_map(|entry| entry.ok().map(|entry| entry.path()))
        .filter(|path| is_visible_dir(path))
        .collect::<Vec<_>>();
    dirs.sort();
    Ok(dirs)
}

fn is_visible_dir(path: &Path) -> bool {
    path.is_dir()
        && path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| !name.starts_with('.') && !name.starts_with('_'))
}

fn split_tool_dirs(value: &str) -> Vec<PathBuf> {
    value
        .split(':')
        .map(str::trim)
        .filter(|entry| !entry.is_empty())
        .map(PathBuf::from)
        .collect()
}

fn clean_env(name: &str) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn clean_env_path(name: &str) -> Option<PathBuf> {
    clean_env(name).map(PathBuf::from)
}

fn default_tools_config() -> Option<PathBuf> {
    let cwd = env::current_dir().ok()?;
    find_ancestor_file(&cwd, "tools.toml")
}

fn default_repo_root() -> Option<PathBuf> {
    default_tools_config().and_then(|path| path.parent().map(Path::to_path_buf))
}

fn find_ancestor_file(start: &Path, name: &str) -> Option<PathBuf> {
    for dir in start.ancestors() {
        let candidate = dir.join(name);
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::*;

    #[test]
    fn discovers_personas_from_ordered_roots() {
        let temp = temp_dir("api-rs-personas");
        let base = temp.join("base");
        let overlay = temp.join("overlay");
        write_persona(
            &base.join("category").join("eng"),
            r#"
[project]
description = "base engineer"

[tool.centaur]
type = "persona"
engine = "codex"
default_repo = "centaur"
"#,
            false,
        );
        write_persona(
            &overlay.join("eng"),
            r#"
[project]
description = "overlay engineer"

[tool.centaur]
type = "persona"
engine = "amp"
"#,
            true,
        );
        write_persona(
            &overlay.join("research"),
            r#"
[project]
description = "research persona"

[tool.centaur]
type = "persona"
"#,
            false,
        );

        let personas = discover_personas_in_dirs(&[base, overlay]);

        assert_eq!(personas.len(), 2);
        assert_eq!(personas["eng"].description, "overlay engineer");
        assert_eq!(personas["eng"].engine, "amp");
        assert_eq!(personas["eng"].default_repo, None);
        assert!(personas["eng"].has_custom_executor);
        assert_eq!(personas["research"].engine, "amp");
    }

    #[test]
    fn skips_non_persona_tools() {
        let temp = temp_dir("api-rs-non-personas");
        write_persona(
            &temp.join("slack"),
            r#"
[project]
description = "tool"

[tool.centaur]
secrets = []
"#,
            false,
        );

        assert!(discover_personas_in_dirs(&[temp]).is_empty());
    }

    fn write_persona(path: &Path, pyproject: &str, custom_executor: bool) {
        fs::create_dir_all(path).unwrap();
        fs::write(path.join("pyproject.toml"), pyproject).unwrap();
        if custom_executor {
            fs::write(path.join("run.py"), "").unwrap();
        }
    }

    fn temp_dir(prefix: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = env::temp_dir().join(format!("{prefix}-{suffix}"));
        fs::create_dir_all(&path).unwrap();
        path
    }
}
