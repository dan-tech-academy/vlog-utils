mod media;
mod sidecar;

use serde_json::{json, Value};
use sidecar::Sidecar;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::{Manager, State};

pub struct MediaRoot(pub Arc<Mutex<Option<PathBuf>>>);

fn repo_root() -> Result<PathBuf, String> {
    let mut starts = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        starts.push(cwd);
    }
    starts.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));
    for start in starts {
        let mut dir = Some(start.as_path());
        while let Some(current) = dir {
            if current.join("helpers/transcribe_batch.py").is_file()
                && current.join("desktop/server.py").is_file()
            {
                return Ok(current.to_path_buf());
            }
            dir = current.parent();
        }
    }
    Err("không tìm thấy repo vlog-utils".into())
}

fn key_entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new("vlog-utils", "elevenlabs").map_err(|err| err.to_string())
}

fn read_key() -> Result<String, String> {
    key_entry()?.get_password().map_err(|err| err.to_string())
}

fn missing_key(error: &str) -> bool {
    let lowered = error.to_ascii_lowercase();
    lowered.contains("no entry")
        || lowered.contains("not found")
        || lowered.contains("item not found")
        || lowered.contains("could not be found")
        || lowered.contains("no matching")
}

fn with_key(mut req: Value) -> Value {
    let Some(map) = req.as_object_mut() else {
        return req;
    };
    let cmd = map.get("cmd").and_then(|value| value.as_str()).unwrap_or("").to_string();
    if cmd == "set_session_key" {
        return req;
    }
    map.remove("api_key");
    if cmd == "ingest" {
        if let Ok(key) = read_key() {
            if !key.trim().is_empty() {
                map.insert("api_key".into(), Value::String(key));
            }
        }
    }
    req
}

async fn remember_sidecar_key(sidecar: &Sidecar, key: &str) -> Result<bool, String> {
    let client = sidecar.cloned();
    let secret = key.to_string();
    let result = tauri::async_runtime::spawn_blocking(move || {
        client.call(json!({
            "id": "set-session-key",
            "cmd": "set_session_key",
            "api_key": secret,
        }))
    })
    .await
    .map_err(|err| err.to_string())??;
    Ok(result.get("ok").and_then(|value| value.as_bool()).unwrap_or(false))
}

#[tauri::command]
async fn sidecar_call(sidecar: State<'_, Sidecar>, req: Value) -> Result<Value, String> {
    let client = sidecar.cloned();
    let req = with_key(req);
    tauri::async_runtime::spawn_blocking(move || client.call(req))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
fn has_api_key() -> Result<bool, String> {
    match read_key() {
        Ok(key) => Ok(!key.trim().is_empty()),
        Err(error) if missing_key(&error) => Ok(false),
        Err(error) => Err(error),
    }
}

#[tauri::command]
async fn set_api_key(sidecar: State<'_, Sidecar>, key: String) -> Result<(), String> {
    let trimmed = key.trim().to_string();
    if trimmed.is_empty() {
        return Err("Key trống.".into());
    }
    let remembered = remember_sidecar_key(&sidecar, &trimmed).await?;
    let keychain_ok = key_entry()
        .and_then(|entry| entry.set_password(&trimmed).map_err(|err| err.to_string()))
        .is_ok();
    if remembered || keychain_ok {
        return Ok(());
    }
    Err("Không lưu được ElevenLabs API key.".into())
}

#[tauri::command]
async fn clear_api_key(sidecar: State<'_, Sidecar>) -> Result<(), String> {
    if let Ok(entry) = key_entry() {
        match entry.delete_credential() {
            Ok(()) => {}
            Err(error) if missing_key(&error.to_string()) => {}
            Err(error) => return Err(error.to_string()),
        }
    }
    let client = sidecar.cloned();
    let _ = tauri::async_runtime::spawn_blocking(move || {
        client.call(json!({"id": "clear-session-key", "cmd": "clear_session_key"}))
    })
    .await;
    Ok(())
}

#[tauri::command]
fn set_media_root(root: State<MediaRoot>, folder: String) -> Result<(), String> {
    let path = PathBuf::from(&folder);
    if !path.is_dir() {
        return Err("không phải folder".into());
    }
    let canonical = path.canonicalize().map_err(|err| err.to_string())?;
    *root.0.lock().map_err(|err| err.to_string())? = Some(canonical);
    Ok(())
}

#[tauri::command]
fn media_url(root: State<MediaRoot>, path: String) -> Result<String, String> {
    let guard = root.0.lock().map_err(|err| err.to_string())?;
    let folder = guard.clone().ok_or("chưa chọn folder")?;
    let file = PathBuf::from(&path);
    if !media::allow(&folder, &file) {
        return Err("file nằm ngoài folder đang mở".into());
    }
    let canonical = file.canonicalize().map_err(|err| err.to_string())?;
    Ok(media::url_for(&canonical))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let media_root = MediaRoot(Arc::new(Mutex::new(None)));
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(media_root)
        .setup(|app| {
            let handle = app.handle().clone();
            match repo_root().and_then(|repo| sidecar::spawn(handle, repo)) {
                Ok(running) => {
                    app.manage(running);
                }
                Err(error) => {
                    app.manage(Sidecar::dead(error));
                }
            }
            Ok(())
        })
        .register_uri_scheme_protocol("vlog", |ctx, request| {
            let root = ctx.app_handle().state::<MediaRoot>();
            let folder = root.0.lock().ok().and_then(|guard| guard.clone());
            media::handle(folder, request)
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_call,
            has_api_key,
            set_api_key,
            clear_api_key,
            set_media_root,
            media_url
        ])
        .run(tauri::generate_context!())
        .expect("lỗi khi chạy Vlog Utils");
}
