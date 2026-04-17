#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{AppHandle, Manager};

struct BackendChild(Mutex<Option<Child>>);

fn python_candidates(app: &AppHandle) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(current_dir) = std::env::current_dir() {
        candidates.push(current_dir.join(".venv/bin/python"));
        candidates.push(current_dir.join(".venv/Scripts/python.exe"));
    }

    if let Some(resource_dir) = app.path().resource_dir().ok() {
        candidates.push(resource_dir.join(".venv/bin/python"));
        candidates.push(resource_dir.join(".venv/Scripts/python.exe"));
    }

    candidates
}

fn start_backend(app: &AppHandle) -> Result<Child, String> {
    let mut command = None;

    for candidate in python_candidates(app) {
        if candidate.exists() {
            let mut cmd = Command::new(candidate);
            cmd.arg("solar_api_server.py");
            command = Some(cmd);
            break;
        }
    }

    let mut command = command.unwrap_or_else(|| {
        let mut cmd = Command::new("python3");
        cmd.arg("solar_api_server.py");
        cmd
    });

    let cwd = std::env::current_dir().map_err(|err| err.to_string())?;
    command
        .current_dir(cwd)
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    command.spawn().map_err(|err| format!("Failed to start Python backend: {err}"))
}

fn main() {
    tauri::Builder::default()
        .manage(BackendChild(Mutex::new(None)))
        .setup(|app| {
            let child = start_backend(app.handle())?;
            let backend = app.state::<BackendChild>();
            *backend.0.lock().expect("backend mutex poisoned") = Some(child);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let backend = window.app_handle().state::<BackendChild>();
                if let Some(mut child) = backend.0.lock().expect("backend mutex poisoned").take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
