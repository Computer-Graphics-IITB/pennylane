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
This file contains the implementation of the SProd class which contains logic for
computing the scalar product of operations.
"""
from typing import Union

import pennylane as qml
import pennylane.math as qnp
from pennylane.operation import Operator
from pennylane.ops.op_math.pow import Pow
from pennylane.ops.op_math.sum import Sum
from pennylane.queuing import QueuingManager

from .symbolicop import ScalarSymbolicOp


def s_prod(scalar, operator, lazy=True, do_queue=True, id=None):
    r"""Construct an operator which is the scalar product of the
    given scalar and operator provided.

    Args:
        scalar (float or complex): the scale factor being multiplied to the operator.
        operator (~.operation.Operator): the operator which will get scaled.

    Keyword Args:
        lazy=True (bool): If ``lazy=False`` and the operator is already a scalar product operator, the scalar provided will simply be combined with the existing scaling factor.
        do_queue (bool): determines if the scalar product operator will be queued. Default is True.
        id (str or None): id for the scalar product operator. Default is None.
    Returns:
        ~ops.op_math.SProd: The operator representing the scalar product.

    .. note::

        This operator supports a batched base, a batched coefficient and a combination of both:

        >>> op = qml.s_prod(scalar=4, operator=qml.RX([1, 2, 3], wires=0))
        >>> qml.matrix(op).shape
        (3, 2, 2)
        >>> op = qml.s_prod(scalar=[1, 2, 3], operator=qml.RX(1, wires=0))
        >>> qml.matrix(op).shape
        (3, 2, 2)
        >>> op = qml.s_prod(scalar=[4, 5, 6], operator=qml.RX([1, 2, 3], wires=0))
        >>> qml.matrix(op).shape
        (3, 2, 2)

        But it doesn't support batching of operators:

        >>> op = qml.s_prod(scalar=4, operator=[qml.RX(1, wires=0), qml.RX(2, wires=0)])
        AttributeError: 'list' object has no attribute 'batch_size'

    .. seealso:: :class:`~.ops.op_math.SProd` and :class:`~.ops.op_math.SymbolicOp`

    **Example**

    >>> sprod_op = s_prod(2.0, qml.PauliX(0))
    >>> sprod_op
    2.0*(PauliX(wires=[0]))
    >>> sprod_op.matrix()
    array([[ 0., 2.],
           [ 2., 0.]])
    """
    if lazy or not isinstance(operator, SProd):
        return SProd(scalar, operator, do_queue=do_queue, id=id)

    sprod_op = SProd(scalar=scalar * operator.scalar, base=operator.base, do_queue=do_queue, id=id)

    if do_queue:
        QueuingManager.remove(operator)

    return sprod_op


class SProd(ScalarSymbolicOp):
    r"""Arithmetic operator representing the scalar product of an
    operator with the given scalar.

    Args:
        scalar (float or complex): the scale factor being multiplied to the operator.
        base (~.operation.Operator): the operator which will get scaled.

    Keyword Args:
        do_queue (bool): determines if the scalar product operator will be queued
            (currently not supported). Default is True.
        id (str or None): id for the scalar product operator. Default is None.

    .. note::
        Currently this operator can not be queued in a circuit as an operation, only measured terminally.

    .. seealso:: :func:`~.ops.op_math.s_prod`

    **Example**

    >>> sprod_op = SProd(1.23, qml.PauliX(0))
    >>> sprod_op
    1.23*(PauliX(wires=[0]))
    >>> qml.matrix(sprod_op)
    array([[0.  , 1.23],
           [1.23, 0.  ]])
    >>> sprod_op.terms()
    ([1.23], [PauliX(wires=[0]])

    .. details::
        :title: Usage Details

        The SProd operation can also be measured inside a qnode as an observable.
        If the circuit is parameterized, then we can also differentiate through the observable.

        .. code-block:: python

            dev = qml.device("default.qubit", wires=1)

            @qml.qnode(dev, diff_method="best")
            def circuit(scalar, theta):
                qml.RX(theta, wires=0)
                return qml.expval(qml.s_prod(scalar, qml.Hadamard(wires=0)))

        >>> scalar, theta = (1.2, 3.4)
        >>> qml.grad(circuit, argnum=[0,1])(scalar, theta)
        (array(-0.68362956), array(0.21683382))

    """
    _name = "SProd"

    def __init__(self, scalar: Union[int, float, complex], base: Operator, do_queue=True, id=None):
        super().__init__(base=base, scalar=scalar, do_queue=do_queue, id=id)

        if base_pauli_rep := getattr(self.base, "_pauli_rep", None):
            pr = {pw: qnp.dot(coeff, self.scalar) for pw, coeff in base_pauli_rep.items()}
            self._pauli_rep = qml.pauli.PauliSentence(pr)
        else:
            self._pauli_rep = None

    def __repr__(self):
        """Constructor-call-like representation."""
        return f"{self.scalar}*({self.base})"

    def label(self, decimals=None, base_label=None, cache=None):
        """The label produced for the SProd op."""
        scalar_val = (
            f"{self.scalar}"
            if decimals is None
            else format(qml.math.toarray(self.scalar), f".{decimals}f")
        )

        return base_label or f"{scalar_val}*{self.base.label(decimals=decimals, cache=cache)}"

    @property
    def data(self):
        """The trainable parameters"""
        return [[self.scalar], self.base.data]  # Not sure if this is the best way to deal with this

    @data.setter
    def data(self, new_data):
        self.scalar = new_data[0][0]
        if len(new_data) > 1:
            self.base.data = new_data[1]

    @property
    def num_params(self):
        return 1 + self.base.num_params

    def terms(self):  # is this method necessary for this class?
        r"""Representation of the operator as a linear combination of other operators.

        .. math:: O = \sum_i c_i O_i

        A ``TermsUndefinedError`` is raised if no representation by terms is defined.

        Returns:
            tuple[list[tensor_like or float], list[.Operation]]: list of coefficients :math:`c_i`
            and list of operations :math:`O_i`
        """
        return [self.scalar], [self.base]

    @property
    def is_hermitian(self):
        """If the base operator is hermitian and the scalar is real,
        then the scalar product operator is hermitian."""
        return self.base.is_hermitian and not qml.math.iscomplex(self.scalar)

    # pylint: disable=arguments-renamed,invalid-overridden-method
    @property
    def has_diagonalizing_gates(self):
        return self.base.has_diagonalizing_gates

    def diagonalizing_gates(self):
        r"""Sequence of gates that diagonalize the operator in the computational basis.

        Given the eigendecomposition :math:`O = U \Sigma U^{\dagger}` where
        :math:`\Sigma` is a diagonal matrix containing the eigenvalues,
        the sequence of diagonalizing gates implements the unitary :math:`U^{\dagger}`.

        The diagonalizing gates rotate the state into the eigenbasis
        of the operator.

        A ``DiagGatesUndefinedError`` is raised if no representation by decomposition is defined.

        .. seealso:: :meth:`~.Operator.compute_diagonalizing_gates`.

        Returns:
            list[.Operator] or None: a list of operators
        """
        return self.base.diagonalizing_gates()

    def eigvals(self):
        r"""Return the eigenvalues of the specified operator.

        This method uses pre-stored eigenvalues for standard observables where
        possible and stores the corresponding eigenvectors from the eigendecomposition.

        Returns:
            array: array containing the eigenvalues of the operator.
        """
        return self.scalar * self.base.eigvals()

    def sparse_matrix(self, wire_order=None):
        return self.base.sparse_matrix(wire_order=wire_order).multiply(self.scalar)

    @property
    def has_matrix(self):
        return isinstance(self.base, qml.Hamiltonian) or self.base.has_matrix

    @staticmethod
    def _matrix(scalar, mat):
        if qml.math.get_interface(scalar) == "tensorflow":
            # we must cast ``scalar`` to complex to avoid an error
            scalar = qml.math.cast_like(scalar, mat)
        return scalar * mat

    @property
    def _queue_category(self):  # don't queue scalar prods as they might not be Unitary!
        """Used for sorting objects into their respective lists in `QuantumTape` objects.
        This property is a temporary solution that should not exist long-term and should not be
        used outside of ``QuantumTape._process_queue``.

        Returns: None
        """
        return None

    def pow(self, z):
        return [SProd(scalar=self.scalar**z, base=Pow(base=self.base, z=z))]

    def adjoint(self):
        return SProd(scalar=qml.math.conjugate(self.scalar), base=qml.adjoint(self.base))

    def simplify(self) -> Operator:
        if self.scalar == 1:
            return self.base.simplify()
        if isinstance(self.base, SProd):
            scalar = self.scalar * self.base.scalar
            if scalar == 1:
                return self.base.base.simplify()
            return SProd(scalar=scalar, base=self.base.base.simplify())

        new_base = self.base.simplify()
        if isinstance(new_base, Sum):
            return Sum(
                *(SProd(scalar=self.scalar, base=summand).simplify() for summand in new_base)
            )
        if isinstance(new_base, SProd):
            return SProd(scalar=self.scalar, base=new_base).simplify()
        return SProd(scalar=self.scalar, base=new_base)
