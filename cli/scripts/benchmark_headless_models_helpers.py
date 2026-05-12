#!/usr/bin/env python3
from __future__ import annotations

import sys

from benchmark_headless_models_helpers_part1 import SOURCE_PART as _PART_1
from benchmark_headless_models_helpers_part2 import SOURCE_PART as _PART_2
from benchmark_headless_models_helpers_part3 import SOURCE_PART as _PART_3
from benchmark_headless_models_helpers_part4 import SOURCE_PART as _PART_4
from benchmark_headless_models_helpers_part5 import SOURCE_PART as _PART_5
from benchmark_headless_models_helpers_part6 import SOURCE_PART as _PART_6
from benchmark_headless_models_helpers_part7 import SOURCE_PART as _PART_7
from benchmark_headless_models_helpers_part8 import SOURCE_PART as _PART_8
from script_runtime_helpers import ensure_script_import_paths, resolve_script_provider_home_dir

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
if str(_SCRIPT_PATHS.cli_root) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_PATHS.cli_root))
if str(_SCRIPT_PATHS.repo_root) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_PATHS.repo_root))

_SOURCE = ''.join([_PART_1, _PART_2, _PART_3, _PART_4, _PART_5, _PART_6, _PART_7, _PART_8])
exec(compile(_SOURCE, __file__, 'exec'), globals(), globals())

DEFAULT_PROVIDER_HOME = resolve_script_provider_home_dir(cwd=REPO_ROOT)
