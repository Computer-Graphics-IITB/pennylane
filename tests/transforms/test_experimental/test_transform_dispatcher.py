# Copyright 2023 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
import pennylane as qml
from pennylane.transforms.core import transform, TransformError
from typing import Sequence, Callable

# TODO: Replace with default qubit 2
dev = qml.device("default.qubit", wires=2)

with qml.tape.QuantumTape() as tape_circuit:
    qml.Hadamard(wires=0)
    qml.CNOT(wires=[0, 1])
    qml.PauliX(wires=0)
    qml.RZ(0.42, wires=1)
    qml.expval(qml.PauliZ(wires=0))


def qfunc_circuit(a):
    qml.Hadamard(wires=0)
    qml.CNOT(wires=[0, 1])
    qml.PauliX(wires=0)
    qml.RZ(a, wires=1)
    return qml.expval(qml.PauliZ(wires=0))


@qml.qnode(device=dev)
def qnode_circuit(a):
    qml.Hadamard(wires=0)
    qml.CNOT(wires=[0, 1])
    qml.PauliX(wires=0)
    qml.RZ(a, wires=1)
    return qml.expval(qml.PauliZ(wires=0))


##########################################
# Non-valid transforms

non_callable = tape_circuit


def no_tape_transform(
    circuit: qml.tape.QuantumTape, index: int
) -> (Sequence[qml.tape.QuantumTape], Callable):
    circuit.circuit.pop(index)
    return [circuit], lambda x: x


def no_quantum_tape_transform(
    tape: qml.operation.Operator, index: int
) -> (Sequence[qml.tape.QuantumTape], Callable):
    tape.circuit.pop(index)
    return [tape], lambda x: x


def no_processing_fn_transform(tape: qml.tape.QuantumTape) -> Sequence[qml.tape.QuantumTape]:
    tape_copy = tape.copy()
    return [tape, tape_copy]


def no_tape_sequence_transform(tape: qml.tape.QuantumTape) -> (qml.tape.QuantumTape, Callable):
    return tape, lambda x: x


def no_callable_return(
    tape: qml.tape.QuantumTape,
) -> (Sequence[qml.tape.QuantumTape], qml.tape.QuantumTape):
    return tape, lambda x: x


non_valid_transforms = [
    non_callable,
    no_processing_fn_transform,
    no_tape_sequence_transform,
    no_tape_transform,
    no_quantum_tape_transform,
    no_callable_return,
]


##########################################
# Valid transforms


def first_valid_transform(
    tape: qml.tape.QuantumTape, index: int
) -> (Sequence[qml.tape.QuantumTape], Callable):
    tape.circuit.pop(index)
    return [tape], lambda x: x


def second_valid_transform(
    tape: qml.tape.QuantumTape, index: int
) -> (Sequence[qml.tape.QuantumTape], Callable):
    tape1 = tape.copy()
    tape2 = tape.circuit.pop(index)

    def fn(results):
        return qml.math.sum(results)

    return [tape1, tape2], fn


valid_transforms = [first_valid_transform, second_valid_transform]


##########################################
# Non-valid expand transforms
def multiple_args_expand_transform(
    tape: qml.tape.QuantumTape, index: int
) -> (Sequence[qml.tape.QuantumTape], Callable):
    return [tape], lambda x: x


class TestTransformDispatcher:
    """Test the transform function (validate and dispatch)."""

    @pytest.mark.parametrize("valid_transform", valid_transforms)
    def test_integration_dispatcher_with_valid_transform(self, valid_transform):
        """Test that no error is raised with the transform function and that the transform dispatcher returns
        the right object."""

        dispatched_transform = transform(valid_transform)

        # Applied on a tape
        tapes, fn = dispatched_transform(tape_circuit, 0)

        assert isinstance(tapes, Sequence)
        assert callable(fn)

        # Applied on a qfunc (return a qfunc)
        qfunc = dispatched_transform(qfunc_circuit, 0)
        assert callable(qfunc)

        # Applied on a qnode (return a qnode with populated the program)
        qnode = dispatched_transform(qnode_circuit, 0)
        assert isinstance(qnode, qml.QNode)
        assert isinstance(qnode.transform_program, list)
        assert isinstance(qnode.transform_program[0], qml.transforms.core.TransformContainer)

    @pytest.mark.parametrize("non_valid_transform", non_valid_transforms)
    def test_dispatcher_signature_non_valid_transform(self, non_valid_transform):
        """Test the non-valid transforms raises a Transform error."""

        with pytest.raises(TransformError):
            transform(non_valid_transform)

    def test_error_not_callable_transform(self):
        """Test that a non-callable is not a valid transforms."""

        with pytest.raises(TransformError, match="The function to register, "):
            transform(non_callable)

    def test_error_no_tape_transform(self):
        """Test that a transform without tape as arg is not valid."""

        with pytest.raises(TransformError, match="The first argument of a transform must be tape."):
            transform(no_tape_transform)

    def test_error_no_quantumtape_transform(self):
        """Test that a transform needs tape to be a quantum tape in order to be valid."""

        with pytest.raises(
            TransformError, match="The type of the tape argument must be a QuantumTape."
        ):
            transform(no_quantum_tape_transform)

    def test_error_no_processing_fn_transform(self):
        """Test that a transform without processing fn return is not valid."""

        with pytest.raises(TransformError, match="The return of a transform must match"):
            transform(no_processing_fn_transform)

    def test_error_no_tape_sequence_transform(self):
        """Test that a transform not returning a sequence of tape is not valid."""

        with pytest.raises(
            TransformError, match="The first return of a transform must be a sequence of tapes:"
        ):
            transform(no_tape_sequence_transform)

    def test_error_no_callable_return(self):
        """Test that a transform not returning a callable is not valid."""

        with pytest.raises(
            TransformError, match="The second return of a transform must be a callable"
        ):
            transform(no_callable_return)

    def test_expand_transform_not_callable(self):
        """Test that an expand transform must be a callable otherwise it is not valid."""

        with pytest.raises(
            TransformError, match="The expand function must be a valid Python function."
        ):
            transform(first_valid_transform, expand_transform=non_callable)

    def test_multiple_args_expand_transform(self):
        """Test that an expand transform must take a single argument which is the tape."""

        with pytest.raises(
            TransformError,
            match="The expand transform does not support arg and kwargs other than tape.",
        ):
            transform(first_valid_transform, expand_transform=multiple_args_expand_transform)

    def test_cotransform_not_callable(self):
        """Test that a co-transform must be a callable."""

        with pytest.raises(
            TransformError, match="The classical co-transform must be a valid Python function."
        ):
            transform(first_valid_transform, classical_cotransform=non_callable)

    def test_apply_dispatched_transform_non_valid_obj(self):
        """Test that applying a dispatched function on a non-valid object raises an error."""
        dispatched_transform = transform(first_valid_transform)
        with pytest.raises(
            TransformError,
            match="The object on which is the transform is applied is not valid. It "
            "can only be a tape, a QNode or a qfunc.",
        ):
            obj = qml.RX(0.1, wires=0)
            dispatched_transform(obj)

    def test_qfunc_transform_multiple_tapes(self):
        """Test that quantum function is not compatible with multiple tapes."""
        dispatched_transform = transform(second_valid_transform)
        with pytest.raises(
            TransformError, match="Impossible to dispatch your transform on quantum function"
        ):
            dispatched_transform(qfunc_circuit, 0)(0.42)

    def test_dispatched_transform_attribute(self):
        """Test the dispatcher attributes."""
        dispatched_transform = transform(first_valid_transform)

        assert dispatched_transform.transform == first_valid_transform
        assert dispatched_transform.expand_transform is None
        assert dispatched_transform.classical_cotransform is None

    def test_the_transform_container_attributes(self):
        """Test the transform container attributes."""
        container = qml.transforms.core.TransformContainer(
            first_valid_transform, args=[0], kwargs={}, classical_cotransform=None
        )

        transform, args, kwargs, cotransform = container

        assert transform == first_valid_transform
        assert args == [0]
        assert kwargs == {}
        assert cotransform is None

        assert container.transform == first_valid_transform
        assert container.args == [0]
        assert container.kwargs == {}
        assert container.classical_cotransform is None
