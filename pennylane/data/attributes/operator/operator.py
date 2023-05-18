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
"""Contains AttributeType definition for pennylane operators, and lists
of operators."""

import json
import typing
from functools import lru_cache
from typing import FrozenSet, Generic, List, Sequence, Type, TypeVar

import numpy as np

import pennylane as qml
from pennylane.data.base._hdf5 import h5py
from pennylane.data.base.attribute import AttributeType
from pennylane.data.base.typing_util import HDF5Group
from pennylane.operation import Operator, Tensor

from ._wires import wires_to_json

Op = TypeVar("Op", bound=Operator)


class _DatasetOperatorMixin:
    """Generic attribute type for ``pennylane.operation.Operator`` classes."""

    @classmethod
    @lru_cache(1)
    def supported_ops(cls) -> FrozenSet[Type[Operator]]:
        return frozenset(
            (
                # pennylane/operation/Tensor
                Tensor,
                # pennylane/ops/qubit/arithmetic_qml.py
                qml.QubitCarry,
                qml.QubitSum,
                # pennylane/ops/qubit/matrix_qml.py
                qml.QubitUnitary,
                qml.DiagonalQubitUnitary,
                # pennylane/ops/qubit/non_parametric_qml.py
                qml.Hadamard,
                qml.PauliX,
                qml.PauliY,
                qml.PauliZ,
                qml.T,
                qml.S,
                qml.SX,
                qml.CNOT,
                qml.CZ,
                qml.CY,
                qml.CH,
                qml.SWAP,
                qml.ECR,
                qml.SISWAP,
                qml.CSWAP,
                qml.CCZ,
                qml.Toffoli,
                qml.WireCut,
                # pennylane/ops/qubit/observables.py
                qml.Hermitian,
                qml.Projector,
                # pennylane/ops/qubit/parametric_ops_controlled.py
                qml.ControlledPhaseShift,
                qml.CPhaseShift00,
                qml.CPhaseShift01,
                qml.CPhaseShift10,
                qml.CRX,
                qml.CRY,
                qml.CRZ,
                qml.CRot,
                # pennylane/ops/qubit/parametric_ops_multi_qubit.py
                qml.MultiRZ,
                qml.IsingXX,
                qml.IsingYY,
                qml.IsingZZ,
                qml.IsingXY,
                qml.PSWAP,
                # pennylane/ops/qubit/parametric_ops_single_qubit.py
                qml.RX,
                qml.RY,
                qml.RZ,
                qml.PhaseShift,
                qml.Rot,
                qml.U1,
                qml.U2,
                qml.U3,
                # pennylane/ops/qubit/qchem_qml.py
                qml.SingleExcitation,
                qml.SingleExcitationMinus,
                qml.SingleExcitationPlus,
                qml.DoubleExcitation,
                qml.DoubleExcitationMinus,
                qml.DoubleExcitationPlus,
                qml.OrbitalRotation,
                # pennylane/ops/special_unitary.py
                qml.SpecialUnitary,
                # pennylane/ops/state_preparation.py
                qml.BasisState,
                qml.QubitStateVector,
                qml.QubitDensityMatrix,
                # pennylane/ops/qutrit/matrix_qml.py
                qml.QutritUnitary,
                # pennylane/ops/qutrit/non_parametric_qml.py
                qml.TShift,
                qml.TClock,
                qml.TAdd,
                qml.TSWAP,
                # pennylane/ops/qutrit/observables.py
                qml.THermitian,
                # pennylane/ops/channel.py
                qml.AmplitudeDamping,
                qml.GeneralizedAmplitudeDamping,
                qml.PhaseDamping,
                qml.DepolarizingChannel,
                qml.BitFlip,
                qml.ResetError,
                qml.PauliError,
                qml.PhaseFlip,
                qml.ThermalRelaxationError,
                # pennylane/ops/cv.py
                qml.Rotation,
                qml.Squeezing,
                qml.Displacement,
                qml.Beamsplitter,
                qml.TwoModeSqueezing,
                qml.QuadraticPhase,
                qml.ControlledAddition,
                qml.ControlledPhase,
                qml.Kerr,
                qml.CrossKerr,
                qml.InterferometerUnitary,
                qml.CoherentState,
                qml.SqueezedState,
                qml.DisplacedSqueezedState,
                qml.ThermalState,
                qml.GaussianState,
                qml.FockState,
                qml.FockStateVector,
                qml.FockDensityMatrix,
                qml.CatState,
                qml.NumberOperator,
                qml.TensorN,
                qml.X,
                qml.P,
                qml.QuadOperator,
                qml.PolyXP,
                qml.FockStateProjector,
                # pennylane/ops/identity.py
                qml.Identity,
            )
        )

    def _hdf5_to_ops(self, bind: HDF5Group) -> List[Operator]:
        ops = []

        op_class_names = bind["op_class_names"].asstr()
        op_wire_labels = bind["op_wire_labels"].asstr()

        for i in range(len(op_class_names)):
            op_key = f"op_{i}"

            op_cls = self._supported_ops_dict()[op_class_names[i]]
            if op_cls is Tensor:
                ops.append(Tensor(*self._hdf5_to_ops(bind[op_key])))
            else:
                wire_labels = json.loads(op_wire_labels[i])
                op_data = bind[op_key]
                if op_data.shape is not None:
                    params = np.zeros(shape=op_data.shape, dtype=op_data.dtype)
                    op_data.read_direct(params)
                    ops.append(op_cls(*params, wires=wire_labels))
                else:
                    ops.append(op_cls(wires=wire_labels))

        return ops

    def _ops_to_hdf5(
        self, bind_parent: HDF5Group, key: str, value: typing.Sequence[Operator]
    ) -> HDF5Group:
        bind = bind_parent.create_group(key)

        op_wire_labels = []
        op_class_names = []
        for i, op in enumerate(value):
            op_key = f"op_{i}"
            if type(op) not in self.supported_ops():
                raise TypeError(
                    f"Serialization of operator type {type(op).__name__} is not supported."
                )

            if isinstance(op, Tensor):
                self._ops_to_hdf5(bind, op_key, op.obs)
                op_wire_labels.append("null")
            else:
                bind[op_key] = op.data if len(op.data) else h5py.Empty("f")
                op_wire_labels.append(wires_to_json(op.wires))

            op_class_names.append(type(op).__name__)

        bind["op_wire_labels"] = op_wire_labels
        bind["op_class_names"] = op_class_names

        return bind

    @classmethod
    @lru_cache(1)
    def _supported_ops_dict(cls) -> dict[str, Type[Operator]]:
        """Returns a dict mapping ``Operator`` subclass names to the class."""
        return {op.__name__: op for op in cls.supported_ops()}


class DatasetOperator(Generic[Op], AttributeType[HDF5Group, Op, Op], _DatasetOperatorMixin):
    type_id = "operator"

    @classmethod
    def consumes_types(cls) -> FrozenSet[Type[Operator]]:
        return cls.supported_ops()

    def value_to_hdf5(self, bind_parent: HDF5Group, key: str, value: Op) -> HDF5Group:
        return self._ops_to_hdf5(bind_parent, key, [value])

    def hdf5_to_value(self, bind: HDF5Group) -> Op:
        return self._hdf5_to_ops(bind)[0]


class DatasetOperatorList(
    AttributeType[HDF5Group, List[Operator], typing.Sequence[Operator]], _DatasetOperatorMixin
):
    type_id = "operator_list"

    def value_to_hdf5(
        self, bind_parent: HDF5Group, key: str, value: Sequence[Operator]
    ) -> HDF5Group:
        return self._ops_to_hdf5(bind_parent, key, value)

    def hdf5_to_value(self, bind: HDF5Group) -> List[Operator]:
        return self._hdf5_to_ops(bind)