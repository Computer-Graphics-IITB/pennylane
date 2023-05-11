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
"""Contains a class for mapping Zarr groups to Dataset Attributes, and a mixin
class that provides the mapper class."""


import typing
from collections.abc import MutableMapping
from types import MappingProxyType
from typing import Any, Dict, Iterator, Optional

from pennylane.data.base.attribute import (
    AttributeInfo,
    AttributeType,
    get_attribute_type,
    match_obj_type,
)
from pennylane.data.base.typing_util import ZarrGroup


class AttributeTypeMapper(MutableMapping):
    """
    This class performs the mapping between the objects contained
    in a Zarr group and Dataset attributes.
    """

    bind: ZarrGroup
    _cache: Dict[str, AttributeType]

    def __init__(self, bind: ZarrGroup) -> None:
        self._cache = {}
        self.bind = bind

    def __getitem__(self, key: str) -> AttributeType:
        if key in self._cache:
            return self._cache[key]

        zobj = self.bind[key]

        attr_type = get_attribute_type(zobj)
        attr = attr_type(bind=zobj)
        self._cache[key] = attr

        return attr

    @property
    def info(self) -> AttributeInfo:
        """Return ``AttributeInfo`` for ``self.bind``."""
        return AttributeInfo(self.bind.attrs)

    def set_item(self, key: str, value: Any, info: Optional[AttributeInfo]):
        """Creates or replaces attribute ``key`` with ``value``, optionally
        including ``info``."""
        if isinstance(value, AttributeType):
            value._set_parent(self.bind, key)  # pylint: disable=protected-access
            if info:
                value.info.load(info)
        else:
            attr_type = match_obj_type(value)
            attr_type(value, info, parent_and_key=(self.bind, key))

        self._cache.pop(key, None)

    def __setitem__(self, key: str, value: Any):
        self.set_item(key, value, None)

    def move(self, src: str, dest: str) -> None:
        """Moves the attribute stored at ``src`` in ``bind`` to ``dest``."""
        self.bind.move(src, dest)
        self._cache.pop(src, None)

    def view(self) -> typing.Mapping[str, AttributeType]:
        """Returns a read-only mapping of the attributes in ``bind``."""
        return MappingProxyType(self)

    def __len__(self) -> int:
        return len(self.bind)

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self.bind)

    def __contains__(self, key: str) -> bool:
        return key in self._cache or key in self.bind

    def __delitem__(self, key: str):
        self._cache.pop(key, None)
        del self.bind[key]


class MapperMixin:  # pylint: disable=too-few-public-methods
    """Mixin class for Dataset types that provide an interface
    to a Zarr group, e.g `DatasetList`, `DatasetDict`. Provides
    a `_mapper` property over the type's ``bind`` attribute."""

    bind: ZarrGroup

    __mapper: AttributeTypeMapper = None

    @property
    def _mapper(self) -> AttributeTypeMapper:
        if self.__mapper is None:
            self.__mapper = AttributeTypeMapper(self.bind)

        return self.__mapper
