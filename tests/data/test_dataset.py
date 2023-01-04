# Copyright 2018-2022 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for the :class:`pennylane.data.Dataset` class and its functions.
"""
# pylint:disable=protected-access
from copy import copy
import os
import sys
import pytest
import pennylane as qml

pytestmark = pytest.mark.data

# TODO: Bring pytest skip to relevant tests.
zstd = pytest.importorskip("zstd")
dill = pytest.importorskip("dill")


def test_build_dataset():
    """Test that a dataset builds correctly and returns the correct values."""
    hamiltonian = qml.Hamiltonian(coeffs=[1], observables=[qml.PauliZ(wires=0)])
    test_dataset = qml.data.Dataset(kw1=1, kw2="2", kw3=[3], hamiltonian=hamiltonian)

    assert test_dataset.kw1 == 1
    assert test_dataset.kw2 == "2"
    assert test_dataset.kw3 == [3]
    assert test_dataset.hamiltonian == hamiltonian


def test_write_dataset(tmp_path):
    """Test that datasets are saved correctly."""
    test_dataset = qml.data.Dataset(kw1=1, kw2="2", kw3=[3])
    d = tmp_path / "sub"
    p = d / "test_dataset"
    test_dataset.write(p)


def test_read_dataset(tmp_path):
    """Test that datasets are loaded correctly."""
    test_dataset = qml.data.Dataset(kw1=1, kw2="2", kw3=[3])
    d = tmp_path / "sub"
    p = d / "test_dataset"
    test_dataset.write(p)

    test_dataset = qml.data.Dataset()
    test_dataset.read(p)

    assert test_dataset.kw1 == 1
    assert test_dataset.kw2 == "2"
    assert test_dataset.kw3 == [3]


def test_list_attributes():
    """Test the list_attributes method."""
    test_dataset = qml.data.Dataset(kw1=1)
    assert test_dataset.list_attributes() == ["kw1"]


def test_copy_non_standard():
    """Test that datasets can be built from other datasets."""
    test_dataset = qml.data.Dataset(dtype="test_data", kw1=1, kw2="2", kw3=[3])
    new_dataset = copy(test_dataset)
    assert new_dataset.attrs == test_dataset.attrs
    assert new_dataset._is_standard is False


def test_copy_standard(tmp_path):
    """Test that standard datasets can be built from other standard datasets."""
    filepath = tmp_path / "myset_full.dat"
    qml.data.Dataset._write_file({"molecule": 1, "hf_state": 2}, str(filepath))
    test_dataset = qml.data.Dataset("qchem", str(tmp_path), "myset", "", standard=True)
    new_dataset = copy(test_dataset)

    assert new_dataset._is_standard == test_dataset._is_standard
    assert new_dataset._dtype == test_dataset._dtype
    assert new_dataset._folder == test_dataset._folder
    assert new_dataset._prefix == test_dataset._prefix
    assert new_dataset._prefix_len == test_dataset._prefix_len
    assert new_dataset._fullfile == test_dataset._fullfile
    assert new_dataset.__doc__ == test_dataset.__doc__
    assert new_dataset.attrs == test_dataset.attrs
    assert new_dataset.attrs == {"molecule": None, "hf_state": None}
    assert new_dataset.molecule == 1
    assert new_dataset.hf_state == 2
    assert new_dataset.attrs == {"molecule": 1, "hf_state": 2}


def test_invalid_init():
    """Test that __init__ fails with invalid arguments."""
    with pytest.raises(
        TypeError,
        match=r"Standard datasets expect 4 arguments: \['data_name', 'data_folder', 'attr_prefix', 'docstring'\]",
    ):
        qml.data.Dataset("first", "second", standard=True)

    with pytest.raises(ValueError, match="Expected data_name to be a str, got int"):
        qml.data.Dataset(1, "some_folder", "some_prefix", "some_docstr", standard=True)


def test_getattribute_dunder_non_full(tmp_path):
    """Test the getattribute override."""
    non_standard_dataset = qml.data.Dataset(foo="bar")
    with pytest.raises(AttributeError):
        _ = non_standard_dataset.baz

    folder = tmp_path / "datasets" / "myset"

    # would not usually be done by users, bypassing qml.data.load
    standard_dataset = qml.data.Dataset("qchem", str(folder), "myset", "", standard=True)

    # no hf_state file exists (yet!)
    with pytest.raises(AttributeError):
        _ = standard_dataset.hf_state
    # create an hf_state file
    os.makedirs(folder)
    qml.data.Dataset._write_file(2, str(folder / "myset_hf_state.dat"))
    # this getattribute will read from the above created file
    assert standard_dataset.hf_state == 2
    assert standard_dataset._fullfile is None


def test_getattribute_dunder_full(tmp_path):
    """Test the getattribute behaviour when a fullfile is set."""
    folder = tmp_path / "datasets" / "myset"
    os.makedirs(folder)
    qml.data.Dataset._write_file({"hf_state": 2}, str(folder / "myset_full.dat"))

    # this getattribute will read from the above created file
    dataset = qml.data.Dataset("qchem", str(folder), "myset", "", standard=True)
    assert dataset.hf_state == 2
    with pytest.raises(AttributeError):
        _ = dataset.molecule


def test_none_attribute_value(tmp_path):
    """Test that non-standard datasets return None while standard datasets raise an error."""
    non_standard_dataset = qml.data.Dataset(molecule=None)
    assert non_standard_dataset.molecule is None

    standard_dataset = qml.data.Dataset("qchem", str(tmp_path), "myset", "", standard=True)
    standard_dataset.molecule = None  # wouldn't usually happen
    with pytest.raises(
        AttributeError,
        match="Dataset has a 'molecule' attribute, but it is None and no data file was found",
    ):
        _ = standard_dataset.molecule


def test_lazy_load_until_access_non_full(tmp_path):
    """Test that Datasets do not load values until accessed with non-full files."""
    filename = str(tmp_path / "myset_hf_state.dat")
    qml.data.Dataset._write_file(2, filename)
    dataset = qml.data.Dataset("qchem", str(tmp_path), "myset", "", standard=True)
    assert dataset.attrs == {"hf_state": None}
    assert dataset.hf_state == 2
    assert dataset.attrs == {"hf_state": 2}


def test_lazy_load_until_access_full(tmp_path):
    """Test that Datasets do not load values until accessed with full files."""
    filename = str(tmp_path / "myset_full.dat")
    qml.data.Dataset._write_file({"molecule": 1, "hf_state": 2}, filename)
    dataset = qml.data.Dataset("qchem", str(tmp_path), "myset", "", standard=True)
    assert dataset.attrs == {"molecule": None, "hf_state": None}
    assert dataset.molecule == 1
    assert dataset.attrs == {"molecule": 1, "hf_state": None}
    assert dataset.hf_state == 2
    assert dataset.attrs == {"molecule": 1, "hf_state": 2}


def test_hamiltonian_is_loaded_properly(tmp_path):
    """Test that __getattribute__ correctly loads hamiltonians from dicts."""
    filename = str(tmp_path / "myset_hamiltonian.dat")
    qml.data.Dataset._write_file(
        {"terms": {"IIII": 0.1, "ZIII": 0.2}, "wire_map": {0: 0, 1: 1, 2: 2, 3: 3}}, filename
    )
    dataset = qml.data.Dataset("qchem", str(tmp_path), "myset", "", standard=True)
    ham = dataset.hamiltonian
    assert isinstance(ham, qml.Hamiltonian)
    coeffs, ops = ham.terms()
    assert coeffs == [0.1, 0.2]
    assert qml.equal(qml.Identity(0), ops[0])
    assert qml.equal(qml.PauliZ(0), ops[1])


def test_hamiltonian_write_preserves_wire_map(tmp_path):
    """Test that writing hamiltonians to file converts to the condensed format."""
    filename = str(tmp_path / "myset_full.dat")
    dataset = qml.data.Dataset()
    obs = [qml.PauliX("a") @ qml.PauliY("c"), qml.PauliZ("a") @ qml.PauliZ("b") @ qml.PauliZ("c")]
    dataset.hamiltonian = qml.Hamiltonian([0.1, 0.2], obs)
    dataset.write(filename)

    # ensure that the non-standard dataset wrote the Hamiltonian in condensed format
    terms_and_wiremap = qml.data.Dataset._read_file(filename)["hamiltonian"]
    assert terms_and_wiremap == {
        "terms": {"XIY": 0.1, "ZZZ": 0.2},
        "wire_map": {"a": 0, "b": 1, "c": 2},
    }

    # ensure std dataset reads what was written as expected (conversion happens in getattr dunder)
    std_ham = qml.data.Dataset("qchem", str(tmp_path), "myset", "", standard=True).hamiltonian
    assert qml.equal(std_ham, dataset.hamiltonian)
    assert std_ham.wires.tolist() == ["a", "b", "c"]

    # ensure non-std dataset read works (conversion happens in read() instance method)
    non_std_dataset = qml.data.Dataset()
    non_std_dataset.read(filename)
    assert qml.equal(non_std_dataset.hamiltonian, dataset.hamiltonian)

    # ensure with non-full files as well
    print("entering")
    other_dataset = qml.data.Dataset("qchem", str(tmp_path), "otherset", "", standard=True)
    filename = str(tmp_path / "otherset_hamiltonian.dat")
    dataset._write_file(qml.data.dataset.hamiltonian_to_dict(dataset.hamiltonian), filename)
    assert other_dataset.list_attributes() == []
    other_dataset.read(filename)
    assert qml.equal(other_dataset.hamiltonian, dataset.hamiltonian)


def test_import_zstd_dill(monkeypatch):
    """Test if an ImportError is raised by _import_zstd_dill function."""

    with monkeypatch.context() as m:
        m.setitem(sys.modules, "zstd", None)

        with pytest.raises(ImportError, match="This feature requires zstd and dill"):
            qml.data.dataset._import_zstd_dill()

    with monkeypatch.context() as m:
        m.setitem(sys.modules, "dill", None)

        with pytest.raises(ImportError, match="This feature requires zstd and dill"):
            qml.data.dataset._import_zstd_dill()


def test_repr_standard(tmp_path):
    """Test that __repr__ for standard Datasets look as expected."""
    folder = tmp_path / "qchem" / "H2" / "STO-3G" / "1.02"
    os.makedirs(folder)
    qml.data.Dataset._write_file(
        {"molecule": 1, "hf_state": 2}, str(folder / "H2_STO-3G_1.02_full.dat")
    )

    dataset = qml.data.Dataset("qchem", str(folder), "H2_STO-3G_1.02", "", standard=True)
    assert (
        repr(dataset)
        == "<Dataset = description: qchem/H2/STO-3G/1.02, attributes: ['molecule', 'hf_state']>"
    )

    dataset.vqe_energy = 1.1
    assert (
        repr(dataset)
        == "<Dataset = description: qchem/H2/STO-3G/1.02, attributes: ['molecule', 'hf_state', ...]>"
    )


def test_repr_non_standard():
    """Test that __repr__ for non-standard Datasets look as expected."""
    dataset = qml.data.Dataset(foo=1, bar=2)
    assert repr(dataset) == "<Dataset = attributes: ['foo', 'bar']>"

    dataset.baz = 3
    assert repr(dataset) == "<Dataset = attributes: ['foo', 'bar', ...]>"
