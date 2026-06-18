from pathlib import Path

from typer.testing import CliRunner

from slack.cli import _upload_target_and_files, app


runner = CliRunner()


def test_upload_target_defaults_when_first_arg_is_file(tmp_path: Path) -> None:
    first = tmp_path / "chart.png"
    second = tmp_path / "table.csv"
    first.write_bytes(b"png")
    second.write_text("a,b\n1,2\n")

    channel, files = _upload_target_and_files(str(first), [str(second)])

    assert channel is None
    assert files == [str(first), str(second)]


def test_upload_target_treats_non_file_first_arg_as_channel(tmp_path: Path) -> None:
    upload = tmp_path / "chart.png"
    upload.write_bytes(b"png")

    channel, files = _upload_target_and_files("C123", [str(upload)])

    assert channel == "C123"
    assert files == [str(upload)]


def test_upload_target_single_missing_path_uses_default_context() -> None:
    channel, files = _upload_target_and_files("chart.png", [])

    assert channel is None
    assert files == ["chart.png"]


def test_upload_single_file_with_default_context_does_not_index_missing_files(
    tmp_path: Path, monkeypatch
) -> None:
    upload = tmp_path / "chart.png"
    upload.write_bytes(b"png")
    calls = []

    def fake_upload_file(**kwargs):
        calls.append(kwargs)
        return {"permalink": "https://slack.example/files/chart.png"}

    monkeypatch.setattr("slack.client.upload_file", fake_upload_file)

    result = runner.invoke(app, ["upload", str(upload), "--comment", "chart"])

    assert result.exit_code == 0
    assert calls[0]["channel"] is None
    assert calls[0]["filename"] == "chart.png"
    assert calls[0]["comment"] == "chart"
