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
Unit tests for the ParametrizedEvolution class
"""
# pylint: disable=unused-argument, too-few-public-methods
import pytest

import pennylane as qml
from pennylane.operation import AnyWires
from pennylane.ops import Evolution, Evolve, ParametrizedHamiltonian, QubitUnitary


class MyOp(qml.RX):  # pylint: disable=too-few-public-methods
    """Variant of qml.RX that claims to not have `adjoint` or a matrix defined."""

    has_matrix = False
    has_adjoint = False
    has_decomposition = False
    has_diagonalizing_gates = False


def time_independent_hamiltonian():
    ops = [qml.PauliX(0), qml.PauliZ(1), qml.PauliY(0), qml.PauliX(1)]

    def f1(params, t):
        return params[0]  # constant

    def f2(params, t):
        return params[1]  # constant

    coeffs = [f1, f2, 4, 9]

    return ParametrizedHamiltonian(coeffs, ops)


def time_dependent_hamiltonian():
    from jax import numpy as jnp

    ops = [qml.PauliX(0), qml.PauliZ(1), qml.PauliY(0), qml.PauliX(1)]

    def f1(params, t):
        return params[0] * t

    def f2(params, t):
        return params[1] * jnp.cos(t)

    def f3(params, t):
        return 4

    def f4(params, t):
        return 9

    coeffs = [f1, f2, f3, f4]
    return ParametrizedHamiltonian(coeffs, ops)


class TestInitialization:
    """Unit tests for the ParametrizedEvolution class."""

    def test_init(self):
        """Test the initialization."""
        ops = [qml.PauliX(0), qml.PauliY(1)]
        coeffs = [1, 2]
        H = ParametrizedHamiltonian(coeffs, ops)
        ev = Evolve(H=H, params=[1, 2], t=2)

        assert ev.H is H
        assert ev.dt is None
        assert qml.math.allequal(ev.t, [0, 2])
        assert qml.math.allequal(ev.h_params, [1, 2])

        assert ev.wires == H.wires
        assert ev.num_wires == AnyWires
        assert ev.name == "Evolve"
        assert ev.id is None
        assert ev.queue_idx is None

        assert ev.data == []
        assert ev.parameters == []
        assert ev.num_params == 0

    def test_has_matrix_true(self):
        """Test that a parametrized evolution always has ``has_matrix=True``."""
        ops = [qml.PauliX(0), qml.PauliY(1)]
        coeffs = [1, 2]
        H = ParametrizedHamiltonian(coeffs, ops)
        ev = Evolve(H=H, params=[1, 2], t=2)
        assert ev.has_matrix is True

    def test_evolve_with_operator_without_matrix_raises_error(self):
        """Test that an error is raised when an ``Evolve`` operator is initialized with a
        ``ParametrizedHamiltonian`` that contains an operator without a matrix defined."""
        ops = [qml.PauliX(0), MyOp(phi=0, wires=0)]
        coeffs = [1, 2]
        H = ParametrizedHamiltonian(coeffs, ops)
        with pytest.raises(
            ValueError,
            match="All operators inside the parametrized hamiltonian must have a matrix defined",
        ):
            _ = Evolve(H=H, params=[1, 2], t=2)


class TestMatrix:
    """Test matrix method."""

    # pylint: disable=unused-argument
    @pytest.mark.jax
    def test_time_independent_hamiltonian(self):
        """Test matrix method for a time independent hamiltonian."""
        H = time_independent_hamiltonian()
        t = 4
        params = [1, 2]
        ev = Evolve(H=H, params=params, t=t, dt=1e-6)
        true_mat = qml.math.expm(-1j * qml.matrix(H(params, t)) * t)
        assert qml.math.allclose(ev.matrix(), true_mat, atol=1e-3)

    @pytest.mark.slow
    @pytest.mark.jax
    def test_time_dependent_hamiltonian(self):
        """Test matrix method for a time dependent hamiltonian. This test approximates the
        time-ordered exponential with a product of exponentials using small time steps.
        For more information, see https://en.wikipedia.org/wiki/Ordered_exponential."""
        from jax import numpy as jnp

        H = time_dependent_hamiltonian()

        t = jnp.pi / 4
        params = [1, 2]
        ev = Evolve(H=H, params=params, t=t)

        time_step = 1e-4
        times = jnp.arange(0, t, step=time_step)
        true_mat = jnp.eye(2 ** len(ev.wires))
        for ti in times[::-1]:
            true_mat @= qml.math.expm(-1j * time_step * qml.matrix(H(params, ti)))

        assert qml.math.allclose(ev.matrix(), true_mat, atol=1e-2)


class TestIntegration:
    """Integration tests for the ParametrizedEvolution class."""

    # pylint: disable=unused-argument
    @pytest.mark.jax
    def test_time_independent_hamiltonian(self):
        """Test the execution of a time independent hamiltonian."""
        import jax
        from jax import numpy as jnp

        H = time_independent_hamiltonian()

        dev = qml.device("default.qubit", wires=2)

        t = 4

        @qml.qnode(dev, interface="jax")
        def circuit(params):
            Evolve(H=H, params=params, t=t, dt=1e-6)
            return qml.expval(qml.PauliX(0) @ qml.PauliX(1))

        @jax.jit
        @qml.qnode(dev, interface="jax")
        def jitted_circuit(params):
            Evolve(H=H, params=params, t=t, dt=1e-6)
            return qml.expval(qml.PauliX(0) @ qml.PauliX(1))

        @qml.qnode(dev, interface="jax")
        def true_circuit(params):
            true_mat = qml.math.expm(-1j * qml.matrix(H(params, t)) * t)
            QubitUnitary(U=true_mat, wires=[0, 1])
            return qml.expval(qml.PauliX(0) @ qml.PauliX(1))

        params = jnp.array([1.0, 2.0])

        assert qml.math.allclose(circuit(params), true_circuit(params), atol=1e-3)
        assert qml.math.allclose(jitted_circuit(params), true_circuit(params), atol=1e-3)
        assert qml.math.allclose(
            jax.grad(circuit)(params), jax.grad(true_circuit)(params), atol=1e-3
        )
        assert qml.math.allclose(
            jax.grad(jitted_circuit)(params), jax.grad(true_circuit)(params), atol=1e-3
        )

    @pytest.mark.slow
    @pytest.mark.jax
    def test_time_dependent_hamiltonian(self):
        """Test the execution of a time dependent hamiltonian. This test approximates the
        time-ordered exponential with a product of exponentials using small time steps.
        For more information, see https://en.wikipedia.org/wiki/Ordered_exponential."""
        import jax.numpy as jnp

        H = time_dependent_hamiltonian()

        dev = qml.device("default.qubit", wires=2)

        @qml.qnode(dev, interface="jax")
        def circuit(params, t):
            Evolve(H=H, params=params, t=t)
            return qml.expval(qml.PauliZ(0) @ qml.PauliX(1))

        @qml.qnode(dev, interface="jax")
        def true_circuit(params, t):
            time_step = 1e-4
            times = jnp.arange(0, t, step=time_step)
            true_mat = jnp.eye(2 ** len(H.wires))
            for ti in times[::-1]:
                true_mat @= qml.math.expm(-1j * time_step * qml.matrix(H(params, ti)))
            QubitUnitary(U=true_mat, wires=[0, 1])
            return qml.expval(qml.PauliZ(0) @ qml.PauliX(1))

        t = jnp.pi / 4
        params = jnp.array([1.0, 2.0])

        # testing grad here is super slow!
        assert qml.math.allclose(circuit(params, t), true_circuit(params, t), atol=1e-2)


class TestEvolveConstructor:
    """Unit tests for the evolve function"""

    def test_evolve_returns_evolution_op(self):
        """Test that the evolve function returns the `Evolution` operator when the input is
        a generic operator."""
        op = qml.s_prod(2, qml.PauliX(0))
        final_op = qml.evolve(op)
        assert isinstance(final_op, Evolution)

    def test_matrix(self):
        """Test that the matrix of the evolved function is correct."""
        op = qml.s_prod(2, qml.PauliX(0))
        final_op = qml.evolve(op)
        mat = qml.math.expm(1j * qml.matrix(op))
        assert qml.math.allequal(qml.matrix(final_op), mat)

    def test_evolve_returns_callable(self):
        """Test that the evolve function returns a callable when the input is a
        ParametrizedHamiltonian."""
        coeffs = [1, 2, 3]
        ops = [qml.PauliX(0), qml.PauliY(1), qml.PauliZ(2)]
        H = ParametrizedHamiltonian(coeffs=coeffs, observables=ops)
        final_op = qml.evolve(H)
        assert callable(final_op)
        param_evolution = final_op(params=[], t=1)
        assert isinstance(param_evolution, Evolve)
        assert param_evolution.H is H
