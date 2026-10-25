use percent_encoding::{percent_decode_str, utf8_percent_encode, NON_ALPHANUMERIC};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use tauri::http::{header, Request, Response, StatusCode};

pub fn allow(root: &Path, candidate: &Path) -> bool {
    let Ok(root) = root.canonicalize() else {
        return false;
    };
    let Ok(path) = candidate.canonicalize() else {
        return false;
    };
    path.starts_with(&root)
}

pub fn url_for(path: &Path) -> String {
    let text = path.to_string_lossy();
    let encoded = utf8_percent_encode(text.as_ref(), NON_ALPHANUMERIC);
    format!("vlog://localhost/?path={encoded}")
}

pub fn path_from_uri(uri: &str) -> Option<PathBuf> {
    let query = uri.split_once('?')?.1.split('#').next().unwrap_or("");
    for pair in query.split('&') {
        let mut parts = pair.splitn(2, '=');
        let key = parts.next().unwrap_or("");
        let value = parts.next().unwrap_or("");
        if key == "path" {
            let decoded = percent_decode_str(value).decode_utf8_lossy().to_string();
            if decoded.is_empty() {
                return None;
            }
            return Some(PathBuf::from(decoded));
        }
    }
    None
}

fn content_type(path: &Path) -> &'static str {
    match path.extension().and_then(|ext| ext.to_str()).unwrap_or("").to_ascii_lowercase().as_str() {
        "jpg" | "jpeg" => "image/jpeg",
        "png" => "image/png",
        "webp" => "image/webp",
        "mov" => "video/quicktime",
        "mkv" => "video/x-matroska",
        "webm" => "video/webm",
        "m4v" | "mp4" => "video/mp4",
        _ => "application/octet-stream",
    }
}

fn parse_range(header_value: &str, len: u64) -> Option<(u64, u64)> {
    let spec = header_value.trim().strip_prefix("bytes=")?;
    let (start_text, end_text) = spec.split_once('-')?;
    if len == 0 {
        return None;
    }
    let start: u64 = if start_text.is_empty() { 0 } else { start_text.parse().ok()? };
    let end: u64 = if end_text.is_empty() { len - 1 } else { end_text.parse().ok()? };
    if start > end || start >= len {
        return None;
    }
    Some((start, end.min(len - 1)))
}

fn reply(status: StatusCode, content_type: &str, extra: Vec<(&str, String)>, body: Vec<u8>) -> Response<Vec<u8>> {
    let mut builder = Response::builder().status(status);
    builder = builder
        .header(header::CONTENT_TYPE, content_type)
        .header(header::ACCEPT_RANGES, "bytes")
        .header(header::CACHE_CONTROL, "no-store")
        .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, "*");
    for (key, value) in extra {
        builder = builder.header(key, value);
    }
    builder.body(body).unwrap_or_else(|_| Response::new(Vec::new()))
}

pub fn handle(root: Option<PathBuf>, request: Request<Vec<u8>>) -> Response<Vec<u8>> {
    let Some(root) = root else {
        return reply(StatusCode::FORBIDDEN, "text/plain", vec![], b"no folder".to_vec());
    };
    let uri = request.uri().to_string();
    let Some(path) = path_from_uri(&uri) else {
        return reply(StatusCode::BAD_REQUEST, "text/plain", vec![], b"missing path".to_vec());
    };
    if !allow(&root, &path) {
        return reply(StatusCode::FORBIDDEN, "text/plain", vec![], b"outside folder".to_vec());
    }
    let file = match File::open(&path) {
        Ok(file) => file,
        Err(_) => return reply(StatusCode::NOT_FOUND, "text/plain", vec![], b"missing".to_vec()),
    };
    let len = match file.metadata() {
        Ok(meta) => meta.len(),
        Err(_) => return reply(StatusCode::NOT_FOUND, "text/plain", vec![], b"missing".to_vec()),
    };
    let mut file = file;
    let range = request
        .headers()
        .get(header::RANGE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| parse_range(value, len));
    let (start, end, status) = match range {
        Some((start, end)) => (start, end, StatusCode::PARTIAL_CONTENT),
        None => (0, len.saturating_sub(1), StatusCode::OK),
    };
    if len == 0 {
        return reply(status, content_type(&path), vec![], Vec::new());
    }
    let size = (end - start + 1) as usize;
    if file.seek(SeekFrom::Start(start)).is_err() {
        return reply(StatusCode::INTERNAL_SERVER_ERROR, "text/plain", vec![], b"seek".to_vec());
    }
    let mut body = vec![0; size];
    if file.read_exact(&mut body).is_err() {
        return reply(StatusCode::INTERNAL_SERVER_ERROR, "text/plain", vec![], b"read".to_vec());
    }
    let mut extra = vec![(header::CONTENT_LENGTH.as_str(), body.len().to_string())];
    if status == StatusCode::PARTIAL_CONTENT {
        extra.push((header::CONTENT_RANGE.as_str(), format!("bytes {start}-{end}/{len}")));
    }
    reply(status, content_type(&path), extra, body)
}
