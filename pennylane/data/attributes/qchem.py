import json
from typing import Tuple, Type

from pennylane import Hamiltonian
from pennylane.data.base.attribute import AttributeType
from pennylane.data.base.typing_util import HDF5Group
from pennylane.pauli import pauli_word_to_string, string_to_pauli_word


class QChemHamiltonian(AttributeType[HDF5Group, Hamiltonian, Hamiltonian]):
    """Attribute type for QChem dataset hamiltonians, which use only Pauli operators."""

    type_id = "qchem_hamiltonian"

    def __post_init__(self, value: Hamiltonian, info):
        """Save the class name of the operator ``value`` into the
        attribute info."""
        super().__post_init__(value, info)
        self.info["operator_class"] = type(value).__qualname__

    def hdf5_to_value(self, bind: HDF5Group) -> Hamiltonian:
        wire_map = {json.loads(w): i for i, w in enumerate(bind["wires"].asstr())}

        ops = [string_to_pauli_word(pauli_string, wire_map) for pauli_string in bind["ops"].asstr()]
        coeffs = list(bind["coeffs"])

        return Hamiltonian(coeffs, ops)

    def value_to_hdf5(self, bind_parent: HDF5Group, key: str, value: Hamiltonian) -> HDF5Group:
        bind = bind_parent.create_group(key)

        coeffs, ops = value.terms()
        wire_map = {w: i for i, w in enumerate(value.wires)}

        bind["ops"] = [pauli_word_to_string(op, wire_map) for op in ops]
        bind["coeffs"] = coeffs
        bind["wires"] = [json.dumps(w) for w in value.wires]

        return bind