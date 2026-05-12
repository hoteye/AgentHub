from __future__ import annotations

from argparse import Namespace
from unittest.mock import Mock

from cli.scripts import quality_size_guard


def test_quality_size_guard_main_wraps_root_arg_with_path_for_scanning(
    monkeypatch, capsys
) -> None:
    root_arg = "custom/root/for/scan"
    baseline_arg = "custom/baseline.json"
    root_path = Mock()
    root_path.exists.return_value = True
    root_path.rglob.return_value = []

    path_ctor = Mock(side_effect=[root_path, Mock(name="baseline_path")])

    monkeypatch.setattr(
        quality_size_guard,
        "parse_args",
        lambda: Namespace(root=root_arg, soft=3, hard=5, baseline=baseline_arg),
    )
    monkeypatch.setattr(quality_size_guard, "Path", path_ctor)
    monkeypatch.setattr(quality_size_guard, "load_baseline", lambda path: {})

    rc = quality_size_guard.main()
    output = capsys.readouterr().out

    assert rc == 0
    assert path_ctor.call_args_list[0].args == (root_arg,)
    root_path.rglob.assert_called_once_with("*.py")
    assert "[size-guard] scanned=0 soft_limit=3 hard_limit=5" in output
