# Desktop app (macOS)

Bản desktop bọc skill headless hiện có. Skill (`SKILL.md`, `helpers/`) không bị viết lại. App là cửa sổ Tauri gọi các script đó.

Chưa phải sản phẩm dùng được trọn vẹn. Cửa sổ mở được, một số bước chạy được, luồng cắt video chưa được xác nhận hết trên footage thật.

## Đã làm

- App macOS: Tauri 2 + React, nằm ở `apps/desktop/`. Sidecar Python nằm ở `desktop/`.
- Chọn folder footage. Video nhận ở ngay thư mục gốc: `.mp4`, `.mov`, `.mkv`, `.avi`, `.m4v` (cùng rule với `helpers/transcribe_batch.py`).
- Brief viết ở panel **Trao đổi** bên phải. Bấm **Phân tích** thì lưu brief vào `edit/agent/brief.md`.
- ElevenLabs key: dán trong **Cài đặt**. Key được giữ trong process sidecar và thử ghi Keychain macOS (service `vlog-utils`, account `elevenlabs`). Key không đưa vào process agent.
- Transcribe và pack transcript bằng `helpers/transcribe_batch.py` và `helpers/pack_transcripts.py`. File đã có transcript thì không gọi lại.
- Agent local: Claude (`claude -p`), Codex (`codex exec`), Grok (`grok -p`), Cursor (`agent -p` hoặc `cursor-agent`). Trên máy dev, lệnh `agent` trên PATH là Grok, nên mục Cursor hiện là chưa cài.
- Agent được yêu cầu ghi `edit/agent/turn.json`. Nếu nó chỉ trả lời trong stdout, app tự lấy JSON hoặc đoạn văn đó và ghi file. Không còn báo `thiếu turn.json` như lỗi của user.
- Hỏi đáp, duyệt chiến lược, rồi mới nhận EDL.
- Storyboard là màn chính, theo bản thiết kế `apps/desktop/design/mockup.html`. Mỗi thẻ là một range trong `edl.json` và phát clip proxy của cảnh đó (540p H.264, lệnh `clips` của sidecar, lưu ở `edit/storyboard/clip_<hash>.mp4`). Cảnh không đổi thì dùng lại clip cũ. Trong lúc clip đang tạo, thẻ hiện poster. Chữ của cảnh được tô sáng theo lúc phát.
- Không sửa tay trên storyboard. User góp ý từng thẻ, góp ý chưa gửi được giữ lại khi đóng app. Bấm **Gửi N góp ý** thì cả lô đi cho agent trong một lượt. Agent ghi lại EDL, app tạo lại clip rồi so bản cũ với bản mới: thẻ đổi có nhãn kiểu “Bỏ “luôn” · ngắn hơn 0.42s”, cảnh bị bỏ được ghi vào lịch sử trao đổi. Ô nhập trong panel dùng cho yêu cầu chung cả video.
- **Xem liền mạch** phát nối các clip khi chưa render. Sau khi render, nút đổi thành **Xem preview** và phát `preview.mp4`.
- Render vẫn là `helpers/render.py`. Preview rồi final. Phụ đề build bằng `--build-subtitles`. **Xuất final.mp4** chỉ bật sau preview. Xuất xong có nút **Mở trong Finder**.
- Mở lại app thì vào folder gần nhất, đúng bước đang dở (`project_status`). Lịch sử trao đổi và góp ý chưa gửi nằm ở `edit/agent/thread.json`. Nếu lần trước app đóng giữa chừng, app báo theo loại việc: agent bị ngắt thì góp ý quay về chưa gửi, render bị ngắt thì có nút **Render lại**, transcribe bị ngắt thì có nút **Tiếp tục**. Folder đã bị xóa thì về màn chọn folder.
- **Làm lại từ đầu** (menu tên dự án) hỏi trước, rồi cất bản cũ vào `edit/archive/<giờ>/`. Transcript được giữ, không tốn thêm tiền ElevenLabs.
- Không có UI làm animation HyperFrames, Remotion, Manim.

## Chạy

```bash
cd apps/desktop
npm install
npm run tauri dev
```

Cần `ffmpeg`, `ffprobe`, `uv`, và một CLI agent đã đăng nhập. Python deps của repo: `uv sync` ở root.

## Kiểm tra đã chạy

- `uv run --with pytest pytest desktop/tests` — 40 tests. Test của `clips` cần `ffmpeg` trên PATH, thiếu thì bị bỏ qua.
- `npm test` trong `apps/desktop` — 21 tests (so EDL cũ và mới, gộp góp ý thành note, gắn góp ý vào thẻ khi mở lại, đọc trạng thái dự án ở từng bước).
- `npm run build` trong `apps/desktop` — TypeScript và Vite build được.
- `cargo test` và `cargo check` trong `apps/desktop/src-tauri` — 4 tests cho Range của `vlog://`.
- `npm run tauri dev` mở được cửa sổ và spawn sidecar `python -m desktop.server`.
- Giao diện storyboard đã chạy thử trong trình duyệt với Tauri giả lập, dùng clip thật do sidecar tạo từ video `testsrc`: phát clip, góp ý 2 thẻ, gửi lô, thấy nhãn thay đổi, render preview, xuất final.

Chưa có một folder footage thật đi hết từ prompt đến `final.mp4` trong cửa sổ app. Thời gian tạo clip proxy từ nguồn 4K chưa đo.

## Lỗi đã gặp khi dùng thử

- Nút **Phân tích** bị khóa im khi thiếu folder, video, hoặc prompt. Dòng dưới nút ghi lý do.
- Key gõ trong ô không được gửi sang transcribe nếu chỉ lưu Keychain. Phân tích giờ tự lưu key đang dán.
- Agent không ghi `turn.json` thì app báo thiếu file. App giờ tự ghi file từ câu trả lời, và chạy lại một lần nếu chưa có JSON.
- Đóng app khi agent, transcribe hoặc render đang chạy thì tiến trình đó chạy tiếp sau khi app đã tắt. Sidecar giờ kill nó khi stdin đóng.
- ffmpeg do sidecar gọi đọc mất lệnh từ stdin của sidecar. Process con giờ nhận `/dev/null` làm stdin.
- Trình phát xin `bytes=0-` làm handler `vlog://` đọc cả file camera vào RAM. Mỗi lần trả giờ tối đa 4 MiB.

## Ngoài phạm vi

Đóng gói App Store, bundle Python/ffmpeg, cài CLI giúp user, animation slot, Whisper local, nhạc, SFX.
