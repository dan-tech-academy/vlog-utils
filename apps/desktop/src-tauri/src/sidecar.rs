use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

extern "C" {
    fn kill(pid: i32, sig: i32) -> i32;
}

struct Inner {
    stdin: Mutex<Option<ChildStdin>>,
    pending: Arc<Mutex<HashMap<String, Sender<Value>>>>,
    child: Mutex<Option<Child>>,
    boot_error: Mutex<Option<String>>,
}

pub struct Sidecar {
    inner: Arc<Inner>,
}

impl Sidecar {
    pub fn cloned(&self) -> Self {
        Self { inner: Arc::clone(&self.inner) }
    }

    pub fn dead(error: String) -> Self {
        Self {
            inner: Arc::new(Inner {
                stdin: Mutex::new(None),
                pending: Arc::new(Mutex::new(HashMap::new())),
                child: Mutex::new(None),
                boot_error: Mutex::new(Some(error)),
            }),
        }
    }

    pub fn call(&self, req: Value) -> Result<Value, String> {
        if let Some(error) = self.inner.boot_error.lock().map_err(|err| err.to_string())?.clone() {
            return Err(error);
        }
        let id = req
            .get("id")
            .and_then(|value| value.as_str())
            .ok_or("missing id")?
            .to_string();
        let (tx, rx) = mpsc::channel();
        self.inner
            .pending
            .lock()
            .map_err(|err| err.to_string())?
            .insert(id.clone(), tx);
        {
            let mut guard = self.inner.stdin.lock().map_err(|err| err.to_string())?;
            let stdin = guard.as_mut().ok_or("sidecar stopped")?;
            let line = serde_json::to_string(&req).map_err(|err| err.to_string())?;
            writeln!(stdin, "{line}").map_err(|err| err.to_string())?;
            stdin.flush().map_err(|err| err.to_string())?;
        }
        let message = self.wait_result(&id, rx);
        self.inner.pending.lock().map_err(|err| err.to_string())?.remove(&id);
        message
    }

    fn wait_result(&self, id: &str, rx: std::sync::mpsc::Receiver<Value>) -> Result<Value, String> {
        loop {
            let message = rx.recv().map_err(|_| "sidecar closed".to_string())?;
            if message.get("type").and_then(|value| value.as_str()) != Some("result") {
                continue;
            }
            let message_id = message.get("id").and_then(|value| value.as_str());
            if message_id.is_none() || message_id == Some(id) {
                return Ok(message);
            }
        }
    }
}

impl Drop for Inner {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(child) = guard.as_mut() {
                let pid = child.id() as i32;
                unsafe { kill(pid, 15); }
            }
        }
    }
}

pub fn spawn(app: AppHandle, repo: PathBuf) -> Result<Sidecar, String> {
    let mut command = python_command(&repo);
    command
        .current_dir(&repo)
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|err| format!("không chạy được Python sidecar: {err}"))?;
    let stdin = child.stdin.take().ok_or("sidecar stdin")?;
    let stdout = child.stdout.take().ok_or("sidecar stdout")?;
    let stderr = child.stderr.take().ok_or("sidecar stderr")?;
    let pending = Arc::new(Mutex::new(HashMap::new()));
    spawn_reader(app.clone(), stdout, Arc::clone(&pending));
    spawn_stderr(app, stderr);
    Ok(Sidecar {
        inner: Arc::new(Inner {
            stdin: Mutex::new(Some(stdin)),
            pending,
            child: Mutex::new(Some(child)),
            boot_error: Mutex::new(None),
        }),
    })
}

fn spawn_reader(app: AppHandle, stdout: impl std::io::Read + Send + 'static, pending: Arc<Mutex<HashMap<String, Sender<Value>>>>) {
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            let Ok(line) = line else { break };
            let message: Value = match serde_json::from_str(&line) {
                Ok(value) => value,
                Err(_) => {
                    let _ = app.emit("sidecar-event", json!({"type": "stderr", "data": {"line": line}}));
                    continue;
                }
            };
            let _ = app.emit("sidecar-event", &message);
            let id = message.get("id").and_then(|value| value.as_str()).unwrap_or("");
            if let Ok(waiters) = pending.lock() {
                if let Some(sender) = waiters.get(id) {
                    let _ = sender.send(message);
                }
            }
        }
        if let Ok(waiters) = pending.lock() {
            for sender in waiters.values() {
                let _ = sender.send(json!({"type": "result", "ok": false, "error": "sidecar closed"}));
            }
        }
    });
}

fn spawn_stderr(app: AppHandle, stderr: impl std::io::Read + Send + 'static) {
    std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            let Ok(line) = line else { break };
            let _ = app.emit("sidecar-event", json!({"type": "stderr", "data": {"line": line}}));
        }
    });
}

fn python_command(repo: &std::path::Path) -> Command {
    let venv = repo.join(".venv/bin/python");
    if venv.exists() {
        let mut command = Command::new(venv);
        command.args(["-u", "-m", "desktop.server"]);
        return command;
    }
    if let Some(uv) = which("uv") {
        let mut command = Command::new(uv);
        command
            .arg("run")
            .arg("--project")
            .arg(repo)
            .args(["python", "-u", "-m", "desktop.server"]);
        return command;
    }
    let mut command = Command::new("python3");
    command.args(["-u", "-m", "desktop.server"]);
    command
}

fn which(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}
