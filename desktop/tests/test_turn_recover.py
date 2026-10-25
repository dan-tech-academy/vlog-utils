from desktop.turn_recover import assistant_text, extract_turn, materialize_turn


def test_extracts_turn_from_claude_result():
    line = (
        '{"type":"result","result":"{\\"kind\\":\\"questions\\",'
        '\\"questions\\":[{\\"id\\":\\"aspect\\",\\"prompt\\":\\"16:9 hay 9:16?\\"}]}"}'
    )
    turn = extract_turn([line])
    assert turn is not None
    assert turn["kind"] == "questions"
    assert turn["questions"][0]["id"] == "aspect"


def test_extracts_turn_from_codex_message():
    line = (
        '{"type":"item.completed","item":{"type":"agent_message","text":'
        '"{\\"kind\\":\\"strategy\\",\\"strategy\\":\\"Keep the second take.\\"}"}}'
    )
    turn = extract_turn([line])
    assert turn == {"kind": "strategy", "strategy": "Keep the second take."}


def test_questions_with_only_strategy_text_become_strategy():
    line = '{"kind":"questions","questions":[],"strategy":"Cut the false start and keep the laugh."}'
    turn = extract_turn([line])
    assert turn["kind"] == "strategy"


def test_prose_reply_is_saved_as_strategy(tmp_path):
    path = tmp_path / "edit" / "agent" / "turn.json"
    lines = [
        "Keep the second take, drop the ums, about one minute, warm grade.",
    ]
    assert materialize_turn(path, lines, strategy_approved=False)
    saved = path.read_text(encoding="utf-8")
    assert "second take" in saved
    assert assistant_text(lines).startswith("Keep the second take")
