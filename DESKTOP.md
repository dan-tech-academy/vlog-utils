# Desktop app (macOS)

Bản desktop bọc skill headless hiện có. Skill (`SKILL.md`, `helpers/`) không bị viết lại. App là cửa sổ Tauri gọi các script đó.

Chưa phải sản phẩm dùng được trọn vẹn. Cửa sổ mở được, một số bước chạy được, luồng cắt video chưa được xác nhận hết trên footage thật.

## Đã làm

- App macOS: Tauri 2 + React, nằm ở `apps/desktop/`. Sidecar Python nằm ở `desktop/`.
- Chọn folder footage. Video nhận ở ngay thư mục gốc: `.mp4`, `.mov`, `.mkv`, `.avi`, `.m4v` (cùng rule với `helpers/transcribe_batch.py`).
- Ô prompt. Bấm **Phân tích** thì lưu brief vào `edit/agent/brief.md`.
- ElevenLabs key: dán vào ô bên trái rồi bấm **Phân tích** là được. Key được giữ trong process sidecar và thử ghi Keychain macOS (service `vlog-utils`, account `elevenlabs`). Key không đưa vào process agent.
- Transcribe và pack transcript bằng `helpers/transcribe_batch.py` và `helpers/pack_transcripts.py`. File đã có transcript thì không gọi lại.
- Agent local: Claude (`claude -p`), Codex (`codex exec`), Grok (`grok -p`), Cursor (`agent -p` hoặc `cursor-agent`). Trên máy dev, lệnh `agent` trên PATH là Grok, nên mục Cursor hiện là chưa cài.
- Agent được yêu cầu ghi `edit/agent/turn.json`. Nếu nó chỉ trả lời trong stdout, app tự lấy JSON hoặc đoạn văn đó và ghi file. Không còn báo `thiếu turn.json` như lỗi của user.
- Hỏi đáp, duyệt chiến lược, rồi mới nhận EDL. Storyboard: xóa, sắp xếp, trim bám word (đệm 30–200ms). **Xuất final.mp4** chỉ bật sau preview.
- Render vẫn là `helpers/render.py`. Preview rồi final. Phụ đề build bằng `--build-subtitles`.
- Sidecar có sẵn lệnh để mở lại folder đúng bước đang dở: `project_status`, `save_thread` (ghi `edit/agent/thread.json`), `reset_project` (cất bản cũ vào `edit/archive/<giờ>/`, giữ transcript). UI chưa gọi các lệnh này; mở lại app vẫn bắt đầu từ chọn folder.
- Giao diện mới dạng storyboard có góp ý từng cảnh mới ở dạng mockup: `apps/desktop/design/mockup.html`.
- Không có UI làm animation HyperFrames, Remotion, Manim.

## Chạy

```bash
cd apps/desktop
npm install
npm run tauri dev
```

Cần `ffmpeg`, `ffprobe`, `uv`, và một CLI agent đã đăng nhập. Python deps của repo: `uv sync` ở root.

## Kiểm tra đã chạy

- `uv run --with pytest pytest desktop/tests` — 36 tests.
- `npm test` trong `apps/desktop` — 11 tests.
- `npm run build` trong `apps/desktop` — TypeScript và Vite build được.
- `cargo check` trong `apps/desktop/src-tauri` — compile được.
- `npm run tauri dev` mở được cửa sổ và spawn sidecar `python -m desktop.server`.

Chưa có một folder footage thật đi hết từ prompt đến `final.mp4` trong cửa sổ app.

## Lỗi đã gặp khi dùng thử

- Nút **Phân tích** bị khóa im khi thiếu folder, video, hoặc prompt. Dòng dưới nút ghi lý do.
- Key gõ trong ô không được gửi sang transcribe nếu chỉ lưu Keychain. Phân tích giờ tự lưu key đang dán.
- Agent không ghi `turn.json` thì app báo thiếu file. App giờ tự ghi file từ câu trả lời, và chạy lại một lần nếu chưa có JSON.
- Đóng app khi agent, transcribe hoặc render đang chạy thì tiến trình đó chạy tiếp sau khi app đã tắt. Sidecar giờ kill nó khi stdin đóng.

## Ngoài phạm vi

Đóng gói App Store, bundle Python/ffmpeg, cài CLI giúp user, animation slot, Whisper local, nhạc, SFX.
