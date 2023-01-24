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
This module contains the qml.sample measurement.
"""
import functools
import warnings
from typing import Sequence, Tuple, Union

import pennylane as qml
from pennylane.operation import Observable
from pennylane.wires import Wires

from .measurements import MeasurementShapeError, Sample, SampleMeasurement


def sample(op: Union[Observable, None] = None, wires=None):
    r"""Sample from the supplied observable, with the number of shots
    determined from the ``dev.shots`` attribute of the corresponding device,
    returning raw samples. If no observable is provided then basis state samples are returned
    directly from the device.

    Note that the output shape of this measurement process depends on the shots
    specified on the device.

    Args:
        op (Observable or None): a quantum observable object
        wires (Sequence[int] or int or None): the wires we wish to sample from, ONLY set wires if
            op is ``None``

    Returns:
        SampleMP: measurement process instance

    Raises:
        ValueError: Cannot set wires if an observable is provided

    The samples are drawn from the eigenvalues :math:`\{\lambda_i\}` of the observable.
    The probability of drawing eigenvalue :math:`\lambda_i` is given by
    :math:`p(\lambda_i) = |\langle \xi_i | \psi \rangle|^2`, where :math:`| \xi_i \rangle`
    is the corresponding basis state from the observable's eigenbasis.

    **Example**

    .. code-block:: python3

        dev = qml.device("default.qubit", wires=2, shots=4)

        @qml.qnode(dev)
        def circuit(x):
            qml.RX(x, wires=0)
            qml.Hadamard(wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.sample(qml.PauliY(0))

    Executing this QNode:

    >>> circuit(0.5)
    array([ 1.,  1.,  1., -1.])

    If no observable is provided, then the raw basis state samples obtained
    from device are returned (e.g., for a qubit device, samples from the
    computational device are returned). In this case, ``wires`` can be specified
    so that sample results only include measurement results of the qubits of interest.

    .. code-block:: python3

        dev = qml.device("default.qubit", wires=2, shots=4)

        @qml.qnode(dev)
        def circuit(x):
            qml.RX(x, wires=0)
            qml.Hadamard(wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.sample()

    Executing this QNode:

    >>> circuit(0.5)
    array([[0, 1],
           [0, 0],
           [1, 1],
           [0, 0]])

    .. note::

        QNodes that return samples cannot, in general, be differentiated, since the derivative
        with respect to a sample --- a stochastic process --- is ill-defined. The one exception
        is if the QNode uses the parameter-shift method (``diff_method="parameter-shift"``), in
        which case ``qml.sample(obs)`` is interpreted as a single-shot expectation value of the
        observable ``obs``.
    """
    if op is not None and not op.is_hermitian:  # None type is also allowed for op
        warnings.warn(f"{op.name} might not be hermitian.")

    if wires is not None:
        if op is not None:
            raise ValueError(
                "Cannot specify the wires to sample if an observable is "
                "provided. The wires to sample will be determined directly from the observable."
            )
        wires = Wires(wires)

    return SampleMP(obs=op, wires=wires)


class SampleMP(SampleMeasurement):
    """Measurement process that returns the samples of a given observable. If no observable is
    provided then basis state samples are returned directly from the device.

    Please refer to :func:`sample` for detailed documentation.

    Args:
        obs (.Observable): The observable that is to be measured as part of the
            measurement process. Not all measurement processes require observables (for
            example ``Probability``); this argument is optional.
        wires (.Wires): The wires the measurement process applies to.
            This can only be specified if an observable was not provided.
        eigvals (array): A flat array representing the eigenvalues of the measurement.
            This can only be specified if an observable was not provided.
        id (str): custom label given to a measurement instance, can be useful for some applications
            where the instance has to be identified
    """

    @property
    def return_type(self):
        return Sample

    @property
    @functools.lru_cache()
    def numeric_type(self):
        # Note: we only assume an integer numeric type if the observable is a
        # built-in observable with integer eigenvalues or a tensor product thereof
        if self.obs is None:

            # Computational basis samples
            return int
        int_eigval_obs = {qml.PauliX, qml.PauliY, qml.PauliZ, qml.Hadamard, qml.Identity}
        tensor_terms = self.obs.obs if hasattr(self.obs, "obs") else [self.obs]
        every_term_standard = all(o.__class__ in int_eigval_obs for o in tensor_terms)
        return int if every_term_standard else float

    @property
    def samples_computational_basis(self):
        return self.obs is None

    # pylint: disable=protected-access
    def shape(self, config, num_wires):
        if qml.active_return():
            return self._shape_new(config, num_wires)
        if config is None:
            raise MeasurementShapeError(
                "The config argument is required to obtain the shape of the measurement "
                f"{self.__class__.__name__}."
            )
        if config.shot_vector is not None:
            if self.obs is None:
                # TODO: revisit when qml.sample without an observable fully
                # supports shot vectors
                raise MeasurementShapeError(
                    "Getting the output shape of a measurement returning samples along with "
                    "a device with a shot vector is not supported."
                )

            shape_list = []
            for s in config.shot_vector:
                shape_list.extend([(s.shots,) if s.shots != 1 else tuple()] * s.copies)
            return tuple(shape_list)

        return (1, config.shots) if self.obs is not None else (1, config.shots, num_wires)

    def _shape_new(self, config, num_wires):
        if config is None:
            raise MeasurementShapeError(
                "The config argument is required to obtain the shape of the measurement "
                f"{self.__class__.__name__}."
            )
        if config.shot_vector is not None:
            shape_list = []
            if self.obs is not None:
                for s in config.shot_vector:
                    shape_list.extend([(s.shots,) if s.shots != 1 else tuple()] * s.copies)
            else:
                for s in config.shot_vector:
                    shape_list.extend(
                        [(s.shots, num_wires) if s.shots != 1 else (num_wires,)] * s.copies
                    )
            return tuple(shape_list)

        if self.obs is None:
            return (config.shots, num_wires) if config.shots != 1 else (num_wires,)
        return (config.shots,) if config.shots != 1 else ()

    def process_samples(
        self,
        samples: Sequence[complex],
        wire_order: Wires,
        shot_range: Tuple[int] = None,
        bin_size: int = None,
    ):
        wire_map = dict(zip(wire_order, range(len(wire_order))))
        mapped_wires = [wire_map[w] for w in self.wires]
        name = self.obs.name if self.obs is not None else None
        # Select the samples from samples that correspond to ``shot_range`` if provided
        if shot_range is not None:
            # Indexing corresponds to: (potential broadcasting, shots, wires). Note that the last
            # colon (:) is required because shots is the second-to-last axis and the
            # Ellipsis (...) otherwise would take up broadcasting and shots axes.
            samples = samples[..., slice(*shot_range), :]

        if mapped_wires:
            # if wires are provided, then we only return samples from those wires
            samples = samples[..., mapped_wires]

        num_wires = samples.shape[-1]  # wires is the last dimension

        if self.obs is None:
            # if no observable was provided then return the raw samples
            return samples if bin_size is None else samples.T.reshape(num_wires, bin_size, -1)

        if name in {"PauliX", "PauliY", "PauliZ", "Hadamard"}:
            # Process samples for observables with eigenvalues {1, -1}
            samples = 1 - 2 * qml.math.squeeze(samples)
        else:
            # Replace the basis state in the computational basis with the correct eigenvalue.
            # Extract only the columns of the basis samples required based on ``wires``.
            powers_of_two = 2 ** qml.math.arange(num_wires)[::-1]
            indices = samples @ powers_of_two
            indices = qml.math.array(indices)  # Add np.array here for Jax support.
            try:
                samples = self.obs.eigvals()[indices]
            except qml.operation.EigvalsUndefinedError as e:
                # if observable has no info on eigenvalues, we cannot return this measurement
                raise qml.operation.EigvalsUndefinedError(
                    f"Cannot compute samples of {self.obs.name}."
                ) from e

        return samples if bin_size is None else samples.reshape((bin_size, -1))
