from __future__ import annotations

from cli.agent_cli.providers.config_catalog_types import read_json_file, read_toml_file


def test_read_json_file_accepts_utf8_bom(tmp_path) -> None:
    path = tmp_path / "auth.json"
    path.write_text('{"OPENAI_API_KEY":"sk-test"}', encoding="utf-8-sig")

    assert read_json_file(path) == {"OPENAI_API_KEY": "sk-test"}


def test_read_toml_file_accepts_utf8_bom(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model_provider = "openai"\n', encoding="utf-8-sig")

    assert read_toml_file(path) == {"model_provider": "openai"}
