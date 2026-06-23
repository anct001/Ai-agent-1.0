from jarvis.config import Settings
from jarvis.agent import OllamaEngine


def test_select_persists_and_reloads(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.select_llm("ollama", "qwen2.5:7b")
    assert s.llm_provider == "ollama"
    assert s.active_model() == "qwen2.5:7b"

    # A fresh Settings over the same data_dir picks up the saved selection.
    s2 = Settings(data_dir=tmp_path)
    assert s2.llm_provider == "ollama"
    assert s2.ollama_model == "qwen2.5:7b"


def test_select_anthropic_sets_cloud_model(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.select_llm("anthropic", "claude-sonnet-4-6")
    assert s.active_model() == "claude-sonnet-4-6"


def test_select_rejects_bad_provider(tmp_path):
    s = Settings(data_dir=tmp_path)
    try:
        s.select_llm("gpt", "x")
        assert False, "should have raised"
    except ValueError:
        pass


def test_ollama_tool_args_parses_string_and_dict():
    assert OllamaEngine._tool_args(
        {"function": {"arguments": {"symbol": "NVDA"}}}
    ) == {"symbol": "NVDA"}
    assert OllamaEngine._tool_args(
        {"function": {"arguments": '{"symbol": "MSFT"}'}}
    ) == {"symbol": "MSFT"}
    assert OllamaEngine._tool_args({"function": {"arguments": "not-json"}}) == {}
    assert OllamaEngine._tool_args({"function": {}}) == {}
