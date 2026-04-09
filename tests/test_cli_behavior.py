import pytest

import steam_artwork_schizopost as app


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(app.time, "sleep", lambda _seconds: None)


def test_positive_float_accepts_fractional_values():
    assert app.positive_float("0.5") == 0.5


def test_load_or_prompt_cookies_reprompts_on_wrong_json_shape(monkeypatch, tmp_path):
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text("[]")
    monkeypatch.setattr(app, "COOKIES_FILE", cookies_file)
    monkeypatch.setattr(app, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app.Prompt, "ask", lambda prompt: "new-value" if "sessionid" in prompt else "secure-value")

    session_id, login_secure = app.load_or_prompt_cookies()

    assert session_id == "new-value"
    assert login_secure == "secure-value"


def test_main_exits_nonzero_when_all_uploads_fail(monkeypatch):
    monkeypatch.setattr(app, "collect_images", lambda _path: [app.Path("photo.png")])
    monkeypatch.setattr(app, "load_or_prompt_cookies", lambda: ("sid", "secure"))
    monkeypatch.setattr(app, "upload_image", lambda **_kwargs: False)
    monkeypatch.setattr(
        app.argparse.ArgumentParser,
        "parse_args",
        lambda self: app.argparse.Namespace(
            path="photo.png",
            quantity=1,
            delay=0.0,
            timeout=1.0,
            reset_cookies=False,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app.main()

    assert exc_info.value.code == 1


def test_main_exits_nonzero_when_some_uploads_fail(monkeypatch):
    outcomes = iter([True, False])

    monkeypatch.setattr(app, "collect_images", lambda _path: [app.Path("photo.png")])
    monkeypatch.setattr(app, "load_or_prompt_cookies", lambda: ("sid", "secure"))
    monkeypatch.setattr(app, "upload_image", lambda **_kwargs: next(outcomes))
    monkeypatch.setattr(
        app.argparse.ArgumentParser,
        "parse_args",
        lambda self: app.argparse.Namespace(
            path="photo.png",
            quantity=2,
            delay=0.0,
            timeout=1.0,
            reset_cookies=False,
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app.main()

    assert exc_info.value.code == 1


def test_main_returns_success_when_all_uploads_succeed(monkeypatch):
    monkeypatch.setattr(app, "collect_images", lambda _path: [app.Path("photo.png")])
    monkeypatch.setattr(app, "load_or_prompt_cookies", lambda: ("sid", "secure"))
    monkeypatch.setattr(app, "upload_image", lambda **_kwargs: True)
    monkeypatch.setattr(
        app.argparse.ArgumentParser,
        "parse_args",
        lambda self: app.argparse.Namespace(
            path="photo.png",
            quantity=2,
            delay=0.0,
            timeout=1.0,
            reset_cookies=False,
        ),
    )

    assert app.main() == 0
