# Copyright 2018-2023 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Contains a lazy-loaded interface to the Zarr module. For internal use only."""

import importlib
from types import ModuleType
from typing import Any, Literal, Union
from pathlib import Path
from .typing_util import ZarrGroup, ZarrArray, ZarrAny
from random import randint


class _zarr_lazy:  # pylint: disable=too-few-public-methods
    """Provides a lazy-loaded interface to the Zarr module."""

    convenience: ModuleType

    def __init__(self):
        self.__h5 = None

    def _do_import(self):
        try:
            self.__h5 = importlib.import_module("h5py")
        except ImportError as Error:
            raise ImportError(
                "This feature requires the 'h5py' and 'zstd' packages. "
                "They can be installed with:\n\n pip install zarr zstd."
            ) from Error

    def __getattr__(self, resource: str) -> Any:
        if self.__h5 is None:
            self._do_import()

        return getattr(self.__h5, resource)

    def group(self) -> ZarrGroup:
        f = self.File(str(randint(0, 32768)), mode="w-", driver="core", backing_store=False)
        return f

    def copy(
        self,
        source: ZarrAny,
        dest: ZarrGroup,
        key: str,
        if_exists: Literal["raise", "overwrite"] = "raise",
    ):
        if if_exists == "raise" and key in dest:
            raise ValueError(f"Key {key} already exists in in {source.name}")

        dest.copy(source, dest, name=key)

    def copy_all(
        self, source: ZarrGroup, dest: ZarrGroup, if_exists: Literal["raise", "overwrite"] = "raise"
    ):
        for key, elem in source.items():
            self.copy(elem, dest, key=key, if_exists=if_exists)

    def open_group(
        self, path: Union[Path, str], mode: Literal["r", "w", "w-", "a"] = "r"
    ) -> ZarrGroup:
        return self.__h5.File(path, mode)


zarr = _zarr_lazy()
