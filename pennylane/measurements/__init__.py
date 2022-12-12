# Copyright 2018-2021 Xanadu Quantum Technologies Inc.

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
This module contains all the measurements supported by PennyLane.

Description
-----------

Measurements
~~~~~~~~~~~~
The :class:`MeasurementProcess` class serves as a base class for measurements, and is inherited
from the :class:`SampleMeasurement`, :class:`StateMeasurement` and :class:`MeasurementTransform`
classes. These classes are subclassed to implement measurements in PennyLane.

* Each :class:`SampleMeasurement` subclass represents a sample-based measurement, which contains a
  :func:`SampleMeasurement.process_samples` method that processes the sequence of samples generated
  by the device. See the :class:`CountsMP` class for an example.

* Each :class:`StateMeasurement` subclass represents a state-based measurement, which contains a
  :func:`StateMeasurement.process_state` method that processes the quantum state generated by the
  device. See the :class:`StateMP` class for an example.

* Each :class:`MeasurementTransform` subclass represents a measurement process that requires
  the application of a batch transform, which converts the given quantum script into a batch of
  quantum scripts and executes them using the device. The main difference between a
  :class:`MeasurementTransform` and a :func:`~pennylane.batch_transform` is that a batch transform is
  tracked by the gradient transform, while a :class:`MeasurementTransform` process isn't.
  See the :class:`ClassicalShadowMP` class for an example.

.. note::
    A measurement process can inherit from both :class:`SampleMeasurement` and
    :class:`StateMeasurement` classes, defining the needed logic to process either samples or the
    quantum state. See the :class:`VarianceMP` for an example.

Differentiation
^^^^^^^^^^^^^^^
In general, a :class:`MeasurementProcess` is differentiable with respect to a parameter if the domain of
that parameter is continuous. When using the analytic method of differentiation, it must satisfy an
additional constraint: the output of the measurement process must be a real scalar value.

Creating custom measurements
----------------------------
A custom measurement process can be created by inheriting from any of the classes mentioned above.

The following is an example for a sample-based measurement that computes the number of samples
obtained of a given state:

.. code-block:: python

    import pennylane as qml
    from pennylane.measurements import SampleMeasurement

    class CountState(SampleMeasurement):
        def __init__(self, state: str):
            self.state = state  # string identifying the state e.g. "0101"
            wires = list(range(len(state)))
            super().__init__(wires=wires)

        def process_samples(self, samples, wire_order, shot_range, bin_size):
            counts_mp = qml.counts(wires=self._wires)
            counts = counts_mp.process_samples(samples, wire_order, shot_range, bin_size)
            return 0 if self.state not in counts else counts[self.state]

        def __copy__(self):
            return CountState(state=self.state)

The measurement process in this example makes use of :func:`~pennylane.counts`, which is a
measurement process in pennylane which returns a dictionary containing the number of times a quantum
state has been sampled.

.. note::

    The `__copy__` method needs to be overriden when new arguments are added into the `__init__`
    method.

We can now execute the new measurement in a :class:`~pennylane.QNode`:

.. code-block:: python

    dev = qml.device("default.qubit", wires=4, shots=1000)

    @qml.qnode(dev)
    def circuit():
        [qml.Hadamard(w) for w in range(4)]
        [qml.CNOT(wires=[i, i + 1]) for i in range(3)]
        return CountState(state="011")

>>> circuit()
tensor(129., requires_grad=True)

If the differentiation constraints mentioned above are met, we can also differentiate measurement
processes:

.. code-block:: python

    @qml.qnode(dev)
    def circuit(x):
        [qml.RX(x, w) for w in range(4)]
        [qml.CNOT(wires=[i, i + 1]) for i in range(3)]
        return CountState(state="011")

>>> from pennylane import numpy as np
>>> x = np.array(0.123, requires_grad=True)
>>> qml.grad(circuit)(x)
63.50000000000001
"""
from .classical_shadow import ClassicalShadowMP, ShadowExpvalMP, classical_shadow, shadow_expval
from .counts import CountsMP, counts
from .expval import ExpectationMP, expval
from .measurements import (
    AllCounts,
    Counts,
    Expectation,
    MeasurementProcess,
    MeasurementShapeError,
    MeasurementTransform,
    MidMeasure,
    MutualInfo,
    ObservableReturnTypes,
    Probability,
    Sample,
    SampleMeasurement,
    Shadow,
    ShadowExpval,
    State,
    StateMeasurement,
    Variance,
    VnEntropy,
)
from .mid_measure import MeasurementValue, MeasurementValueError, MidMeasureMP, measure
from .mutual_info import MutualInfoMP, mutual_info
from .probs import ProbabilityMP, probs
from .sample import SampleMP, sample
from .state import StateMP, density_matrix, state
from .var import VarianceMP, var
from .vn_entropy import VnEntropyMP, vn_entropy
