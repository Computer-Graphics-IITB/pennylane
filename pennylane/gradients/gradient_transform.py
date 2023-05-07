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
"""This module contains utilities for defining custom gradient transforms,
including a decorator for specifying gradient expansions."""
# pylint: disable=too-few-public-methods
import warnings
from collections.abc import Sequence
import numpy as np

import pennylane as qml
from pennylane._device import _get_num_copies
from pennylane.transforms.tape_expand import expand_invalid_trainable
from pennylane.measurements import MutualInfoMP, StateMP, VarianceMP, VnEntropyMP, ProbabilityMP

SUPPORTED_GRADIENT_KWARGS = [
    "approx_order",
    "argnum",
    "aux_wire",
    "broadcast",  # [TODO: This is in param_shift. Unify with use_broadcasting in stoch_pulse_grad
    "device_wires",
    "diagonal_shifts",
    "f0",
    "force_order2",
    "gradient_recipes",
    "gradient_kwargs",
    "h",
    "n",
    "num",
    "num_directions",
    "num_split_times",
    "off_diagonal_shifts",
    "order",
    "reduction",
    "sampler",
    "sampler_seed",
    "shifts",
    "shots",
    "strategy",
    "use_broadcasting",
    "validate_params",
]


def assert_active_return(transform_name):
    """Check that the new return type system is active. Raise an error if this is not the case.

    Args:
        transform_name (str): Name of the gradient transform that queries the return system
    """
    if not qml.active_return():
        raise NotImplementedError(
            f"The {transform_name} gradient transform only supports the new "
            "return type system. Use qml.enable_return() to activate it."
        )


def assert_multimeasure_not_broadcasted(measurements, broadcast):
    """Assert that there are not simultaneously multiple measurements and
    broadcasting activated.Otherwise raises an error."""
    if broadcast and len(measurements) > 1:
        raise NotImplementedError(
            "Broadcasting with multiple measurements is not supported yet. "
            f"Set broadcast to False instead. The tape measurements are {measurements}."
        )


def assert_no_state_returns(measurements, transform_name):
    """Check whether a set of measurements contains a measurement process that returns the quantum
    state and raise an error if this is the case.

    Args:
        measurements (list[MeasurementProcess]): measurements to analyze
        transform_name (str): Name of the gradient transform that queries the measurements

    Currently, the measurement processes that are considered to return the state are
    ``~.measurements.StateMP``, ``~.measurements.VnEntropyMP``, and ``~.measurements.MutualInfoMP``.
    """
    if any(isinstance(m, (StateMP, VnEntropyMP, MutualInfoMP)) for m in measurements):
        raise ValueError(
            f"Computing the gradient of circuits that return the state with the {transform_name} "
            "gradient transform is not supported, as it is a hardware-compatible method."
        )


def assert_no_variance(measurements, transform_name):
    """Check whether a set of measurements contains a variance measurement
    raise an error if this is the case.

    Args:
        measurements (list[MeasurementProcess]): measurements to analyze
        transform_name (str): Name of the gradient transform that queries the measurements
    """
    if any(isinstance(m, VarianceMP) for m in measurements):
        raise ValueError(
            f"Computing the gradient of variances with the {transform_name} "
            "gradient transform is not supported."
        )


def _gradient_analysis(tape, use_graph=True, grad_fn=None):
    """Update the parameter information dictionary of the tape with
    gradient information of each parameter.
    """
    # pylint:disable=protected-access
    if grad_fn is not None:
        if getattr(tape, "_gradient_fn", None) is grad_fn:
            # gradient analysis has already been performed on this tape
            return

        tape._gradient_fn = grad_fn

    for idx, info in enumerate(tape._par_info):
        if idx not in tape.trainable_params:
            # non-trainable parameters do not require a grad_method
            info["grad_method"] = None
        else:
            op = tape._par_info[idx]["op"]

            if not qml.operation.has_grad_method(op):
                # no differentiation method is registered for this operation
                info["grad_method"] = None

            elif (tape._graph is not None) or use_graph:
                if not any(tape.graph.has_path(op, ob) for ob in tape.observables):
                    # there is no influence of this operation on any of the observables
                    info["grad_method"] = "0"
                    continue

            info["grad_method"] = op.grad_method


def _grad_method_validation(method, tape):
    """Validates if the gradient method requested is supported by the trainable
    parameters of a tape, and returns the allowed parameter gradient methods."""
    diff_methods = {
        idx: info["grad_method"]
        for idx, info in enumerate(tape._par_info)  # pylint: disable=protected-access
        if idx in tape.trainable_params
    }

    # check and raise an error if any parameters are non-differentiable
    nondiff_params = {idx for idx, g in diff_methods.items() if g is None}

    if nondiff_params:
        raise ValueError(f"Cannot differentiate with respect to parameter(s) {nondiff_params}")

    numeric_params = {idx for idx, g in diff_methods.items() if g == "F"}

    # If explicitly using analytic mode, ensure that all parameters
    # support analytic differentiation.
    if method == "analytic" and numeric_params:
        raise ValueError(
            f"The analytic gradient method cannot be used with the parameter(s) {numeric_params}."
        )

    return tuple(diff_methods.values())


def gradient_analysis_and_validation(tape, method, use_graph=True, grad_fn=None, overwrite=True):
    """Update the parameter information dictionary of the tape with gradient information of
    each parameter. Then validates if the gradient method requested is supported by the trainable
    parameters of a tape, and returns the allowed parameter gradient methods.

    Parameter gradient methods include:

    * ``None``: the parameter does not support differentiation.

    * ``"0"``: the variational circuit output does not depend on this
      parameter (the partial derivative is zero).

    In addition, the operator might define its own grad method
    via :attr:`.Operator.grad_method`.

    .. note::

        Note that this function modifies the input tape in-place.

    Args:
        tape (.QuantumTape): the quantum tape to analyze
        method (str): the overall Jacobian differentiation method
        use_graph (bool): whether to use a directed-acyclic graph to determine
            if the parameter has a gradient of 0
        grad_fn (None or callable): The gradient transform performing the analysis.
            This is an optional argument; if provided, and the tape has already
            been analyzed for the gradient information by the same gradient transform,
            the cached gradient analysis will be used.
        overwrite (bool): Whether to overwrite existing parameter gradient methods during the
            first part of the function.

    Raises:
        ValueError: If there exist non-differentiable trainable parameters on the tape.
        ValueError: If the Jacobian method is ``"analytic"`` but there exist some trainable
            parameters on the tape that only support numeric differentiation.

    Returns:
        tuple[str, None]: the allowed parameter gradient methods for each trainable parameter
    """
    if overwrite or "grad_method" not in tape._par_info[0]:  # pylint: disable=protected-access
        _gradient_analysis(tape, use_graph=use_graph, grad_fn=grad_fn)
    return _grad_method_validation(method, tape)


def choose_grad_methods(diff_methods, argnum):
    """Chooses the trainable parameters to use for computing the Jacobian
    by returning a map of their indices and differentiation methods.

    When there are fewer parameters specified than the total number of
    trainable parameters, the Jacobian is estimated by using the parameters
    specified using the ``argnum`` keyword argument.

    Args:
        diff_methods (list): the ordered list of differentiation methods
            for each parameter
        argnum (int, list(int), None): Indices for argument(s) with respect
            to which to compute the Jacobian.

    Returns:
        dict: map of the trainable parameter indices and
        differentiation methods
    """
    if argnum is None:
        return dict(enumerate(diff_methods))

    if isinstance(argnum, int):
        argnum = [argnum]

    num_params = len(argnum)

    if num_params == 0:
        warnings.warn(
            "No trainable parameters were specified for computing the Jacobian.",
            UserWarning,
        )
        return {}

    return {idx: diff_methods[idx] for idx in argnum}


def _all_zero_grad(tape, shots=None):
    """Auxiliary function to return zeros for the all-zero gradient case."""
    list_zeros = []

    par_shapes = [qml.math.shape(p) for p in tape.get_parameters()]
    for m in tape.measurements:
        # TODO: Update shape for CV variables
        if isinstance(m, ProbabilityMP):
            shape = (2 ** len(m.wires),)
        else:
            shape = ()

        if len(tape.trainable_params) == 1:
            sub_list_zeros = qml.math.zeros(par_shapes[0] + shape)
        else:
            sub_list_zeros = tuple(qml.math.zeros(sh + shape) for sh in par_shapes)

        list_zeros.append(sub_list_zeros)

    if isinstance(shots, Sequence):
        len_shot_vec = _get_num_copies(shots)
        if len(tape.measurements) == 1:
            return [], lambda _: tuple(list_zeros[0] for _ in range(len_shot_vec))
        return [], lambda _: tuple(tuple(list_zeros) for _ in range(len_shot_vec))

    if len(tape.measurements) == 1:
        return [], lambda _: list_zeros[0]

    return [], lambda _: tuple(list_zeros)


_no_trainable_grad_warning = (
    "Attempted to compute the gradient of a tape with no trainable parameters. "
    "If this is unintended, please mark trainable parameters in accordance with the "
    "chosen auto differentiation framework, or via the 'tape.trainable_params' property."
)


def _no_trainable_grad(tape, shots=None):
    """Auxiliary function that returns correctly formatted gradients when there
    are no trainable parameters."""
    warnings.warn(_no_trainable_grad_warning)
    if isinstance(shots, Sequence):
        len_shot_vec = _get_num_copies(shots)
        if len(tape.measurements) == 1:
            return [], lambda _: tuple(qml.math.zeros([0]) for _ in range(len_shot_vec))
        return [], lambda _: tuple(
            tuple(qml.math.zeros([0]) for _ in range(len(tape.measurements)))
            for _ in range(len_shot_vec)
        )

    if len(tape.measurements) == 1:
        return [], lambda _: qml.math.zeros([0])
    return [], lambda _: tuple(qml.math.zeros([0]) for _ in range(len(tape.measurements)))


def _no_trainable_grad_legacy(tape):
    """Auxiliary function that returns correctly formatted gradients when there
    are no trainable parameters. This version is for the old return type system."""
    warnings.warn(_no_trainable_grad_warning)
    return [], lambda _: np.zeros((tape.output_dim, 0))


def _swap_first_two_axes(grads, first_axis_size, second_axis_size):
    """Transpose the first two axes of an iterable of iterables, returning
    a tuple of tuples."""
    if first_axis_size == 1:
        return tuple(grads[0][i] for i in range(second_axis_size))
    return tuple(
        tuple(grads[j][i] for j in range(first_axis_size)) for i in range(second_axis_size)
    )


def _reorder_grad_axes_single_measure_shot_vector(grads, num_params, len_shot_vec):
    """Reorder the axes for gradient results obtained for a tape with a single measurement from
    a device that defined a shot vector.

    The order of axes of the gradient output matches the structure outputted by jax.jacobian
    for a tuple-valued function. Internally, this may not be the case when computing the
    gradients, so the axes are reordered here.

    The first axis always corresponds to the number of trainable parameters because the
    parameter-shift transform defines multiple tapes each of which corresponds to a trainable
    parameter. Those tapes are then executed using a device, which at the moment outputs results
    with the first axis corresponding to each tape output.

    The final order of axes of gradient results should be:
    1. Shot vector
    2. Measurements
    3. Number of trainable parameters (Num params)
    4. Broadcasting dimension
    5. Measurement shape

    According to the order above, the following reordering is done:

    Shot vectors:

        Go from
        1. Num params
        2. Shot vector
        3. Measurement shape

        To
        1. Shot vector
        2. Num params
        3. Measurement shape
    """
    return _swap_first_two_axes(grads, num_params, len_shot_vec)


def _reorder_grad_axes_multi_measure(
    grads, num_params, num_measurements, len_shot_vec, shot_vector_multi_measure
):
    """Reorder the axes for gradient results obtained for a tape with multiple measurements.

    The order of axes of the gradient output matches the structure outputted by jax.jacobian for
    a tuple-valued function. Internally, this may not be the case when computing the gradients,
    so the axes are reordered here.

    The first axis always corresponds to the number of trainable parameters because the
    parameter-shift transform defines multiple tapes each of which corresponds to a trainable
    parameter. Those tapes are then executed using a device, which at the moment outputs
    results with the first axis corresponding to each tape output.

    The final order of axes of gradient results should be:
    1. Shot vector
    2. Measurements
    3. Number of trainable parameters (Num params)
    4. Broadcasting dimension
    5. Measurement shape

    Parameter broadcasting doesn't yet support multiple measurements, hence such cases are not
    dealt with at the moment by this function.

    According to the order above, the following reorderings are done:

    A) Analytic (``shots=None``) or finite shots:

        Go from
        1. Num params
        2. Measurements
        3. Measurement shape

        To
        1. Measurements
        2. Num params
        3. Measurement shape

    B) Shot vectors:

        Go from
        1. Num params
        2. Shot vector
        3. Measurements
        4. Measurement shape

        To
        1. Shot vector
        2. Measurements
        3. Num params
        4. Measurement shape
    """
    multi_param = num_params > 1
    if not shot_vector_multi_measure:
        new_grad = _swap_first_two_axes(grads, num_params, num_measurements)
    else:
        new_grad = []
        for i in range(len_shot_vec):
            shot_vec_grad = []
            for j in range(num_measurements):
                measurement_grad = []
                for k in range(num_params):
                    measurement_grad.append(grads[k][i][j])

                measurement_grad = tuple(measurement_grad) if multi_param else measurement_grad[0]
                shot_vec_grad.append(measurement_grad)
            new_grad.append(tuple(shot_vec_grad))

    return new_grad


def reorder_grads(grads, tape_specs):
    """Reorder the axes of tape gradients according to the original tape specifications.

    Args:
        grads (list[tensorlike] or list[tuple[tensorlike]] or list[tuple[tuple[tensorlike]]]:
            Gradient entries with leading parameter axis to be reordered.
        tape_specs (tuple): Information about the differentiated original tape in the order
            ``(bool: single_measure, int: num_params, int: num_measurements, bool: shot_vector,
            mixed: shots)``.

    Returns:
        tensor_like or tuple[tensor_like] or tuple[tuple[tensor_like]]: The reordered gradient
            entries. Consider the details below for the ordering of the axes.

    - If the original tape returned a single measurement and has a single parameter, the
      first entry is returned.
    - If the original tape returned a single measurement and a shot vector was used,
      reorder the gradient axes with ``_reorder_grad_axes_single_measure_shot_vector``
    - If the original tape returned multiple measurements,
      reorder the gradient axes with ``_reorder_grad_axes_multi_measure``.
    """
    single_measure, num_params, num_measurements, shot_vector, shots = tape_specs
    if single_measure and num_params == 1:
        return grads[0]
    len_shot_vec = _get_num_copies(shots) if shot_vector else None
    if single_measure and shot_vector:
        return _reorder_grad_axes_single_measure_shot_vector(grads, num_params, len_shot_vec)
    if not single_measure:
        grads = _reorder_grad_axes_multi_measure(
            grads,
            num_params,
            num_measurements,
            len_shot_vec,
            shot_vector,
        )
    return tuple(grads)


class gradient_transform(qml.batch_transform):
    """Decorator for defining quantum gradient transforms.

    Quantum gradient transforms are a specific case of :class:`~.batch_transform`.
    All quantum gradient transforms accept a tape, and output
    a batch of tapes to be independently executed on a quantum device, alongside
    a post-processing function that returns the result.

    Args:
        expand_fn (function): An expansion function (if required) to be applied to the
            input tape before the gradient computation takes place. If not provided,
            the default expansion function simply expands all operations that
            have ``Operation.grad_method=None`` until all resulting operations
            have a defined gradient method.
        differentiable (bool): Specifies whether the gradient transform is differentiable or
            not. A transform may be non-differentiable if it does not use an
            autodiff framework for its tensor manipulations. In such a case, setting
            ``differentiable=False`` instructs the decorator
            to mark the output as 'constant', reducing potential overhead.
        hybrid (bool): Specifies whether classical processing inside a QNode
            should be taken into account when transforming a QNode.

            - If ``True``, and classical processing is detected and this
              option is set to ``True``, the Jacobian of the classical
              processing will be computed and included. When evaluated, the
              returned Jacobian will be with respect to the QNode arguments.

            - If ``False``, any internal QNode classical processing will be
              **ignored**. When evaluated, the returned Jacobian will be with
              respect to the **gate** arguments, and not the QNode arguments.

    Supported gradient transforms must be of the following form:

    .. code-block:: python

        @gradient_transform
        def my_custom_gradient(tape, argnum=None, **kwargs):
            ...
            return gradient_tapes, processing_fn

    where:

    - ``tape`` (*QuantumTape*): the input quantum tape to compute the gradient of

    - ``argnum`` (*int* or *list[int]* or *None*): Which trainable parameters of the tape
      to differentiate with respect to. If not provided, the derivatives with respect to all
      trainable inputs of the tape should be returned (``tape.trainable_params``).

    - ``gradient_tapes`` (*list[QuantumTape]*): is a list of output tapes to be evaluated.
      If this list is empty, no quantum evaluations will be made.

    - ``processing_fn`` is a processing function to be applied to the output of the evaluated
      ``gradient_tapes``. It should accept a list of numeric results with length ``len(gradient_tapes)``,
      and return the Jacobian matrix.

    Once defined, the quantum gradient transform can be used as follows:

    >>> gradient_tapes, processing_fn = my_custom_gradient(tape, *gradient_kwargs)
    >>> res = execute(tapes, dev, interface="autograd", gradient_fn=qml.gradients.param_shift)
    >>> jacobian = processing_fn(res)

    Alternatively, gradient transforms can be applied directly to QNodes,
    in which case the execution is implicit:

    >>> fn = my_custom_gradient(qnode, *gradient_kwargs)
    >>> fn(weights) # transformed function takes the same arguments as the QNode
    1.2629730888100839

    .. note::

        The input tape might have parameters of various types, including
        NumPy arrays, JAX Arrays, and TensorFlow and PyTorch tensors.

        If the gradient transform is written in a autodiff-compatible manner, either by
        using a framework such as Autograd or TensorFlow, or by using ``qml.math`` for
        tensor manipulation, then higher-order derivatives will also be supported.

        Alternatively, you may use the ``tape.unwrap()`` context manager to temporarily
        convert all tape parameters to NumPy arrays and floats:

        >>> with tape.unwrap():
        ...     params = tape.get_parameters()  # list of floats
    """

    def __init__(
        self, transform_fn, expand_fn=expand_invalid_trainable, differentiable=True, hybrid=True
    ):
        self.hybrid = hybrid
        super().__init__(transform_fn, expand_fn=expand_fn, differentiable=differentiable)

    def default_qnode_wrapper(self, qnode, targs, tkwargs):  # pylint: disable=too-many-statements
        # Here, we overwrite the QNode execution wrapper in order
        # to take into account that classical processing may be present
        # inside the QNode.
        hybrid = tkwargs.pop("hybrid", self.hybrid)
        _wrapper = super().default_qnode_wrapper(qnode, targs, tkwargs)

        def jacobian_wrapper(
            *args, **kwargs
        ):  # pylint: disable=too-many-return-statements, too-many-branches, too-many-statements
            argnum = tkwargs.get("argnum", None)
            argnums = tkwargs.get("argnums", None)

            interface = qml.math.get_interface(*args)
            trainable_params = qml.math.get_trainable_indices(args)

            if interface == "jax" and argnum:
                warnings.warn(
                    "argnum is deprecated with the Jax interface. You should use argnums instead."
                )
                tkwargs.pop("argnum")
                argnums = argnum

            if interface == "jax" and not trainable_params:
                if argnums is None:
                    argnums_ = [0]

                else:
                    argnums_ = [argnums] if isinstance(argnums, int) else argnums

                params = qml.math.jax_argnums_to_tape_trainable(
                    qnode, argnums_, self.expand_fn, args, kwargs
                )
                argnums_ = qml.math.get_trainable_indices(params)
                kwargs["argnums"] = argnums_

            elif not trainable_params:
                warnings.warn(
                    "Attempted to compute the gradient of a QNode with no trainable parameters. "
                    "If this is unintended, please add trainable parameters in accordance with "
                    "the chosen auto differentiation framework."
                )
                return ()

            qjac = _wrapper(*args, **kwargs)

            if not hybrid:
                return qjac

            kwargs.pop("shots", False)

            # Special case where we apply a Jax transform (jacobian e.g.) on the gradient transform and argnums are
            # defined on the outer transform and therefore on the args.
            if interface == "jax":
                argnum_cjac = trainable_params or argnums
            else:
                argnum_cjac = None

            cjac = qml.transforms.classical_jacobian(
                qnode, argnum=argnum_cjac, expand_fn=self.expand_fn
            )(*args, **kwargs)

            if qml.active_return():
                if isinstance(cjac, tuple) and len(cjac) == 1:
                    cjac = cjac[0]

                if not isinstance(cjac, tuple):
                    is_square = cjac.ndim == 2 and cjac.shape[0] == cjac.shape[1]

                    if not qml.math.is_abstract(cjac):
                        if is_square and qml.math.allclose(cjac, qml.numpy.eye(cjac.shape[0])):
                            # Classical Jacobian is the identity. No classical processing
                            # is present inside the QNode.
                            return qjac

                multi_meas = len(qnode.tape.measurements) > 1

                if multi_meas:
                    multi_params = isinstance(cjac, tuple) or isinstance(qjac[0], tuple)
                else:
                    multi_params = isinstance(cjac, tuple) or isinstance(qjac, tuple)

                if not multi_params and not multi_meas:
                    if qjac.shape == ():
                        qjac = qml.math.reshape(qjac, (1,))

                    # With dimension e.g. probs
                    else:
                        qjac = qml.math.reshape(qjac, (1, -1))

                    return qml.math.tensordot(qjac, cjac, [[0], [0]])

                if multi_meas and not multi_params:
                    jacs = tuple(
                        qml.math.tensordot(qml.math.reshape(q, (1,)), cjac, [[0], [0]])
                        if q.shape == ()
                        else qml.math.tensordot(qml.math.reshape(q, (1, -1)), cjac, [[0], [0]])
                        for q in qjac
                    )
                    return jacs
                if not multi_meas and multi_params:
                    if not isinstance(cjac, tuple):
                        jacs = qml.math.tensordot(
                            qml.math.stack(qjac), qml.math.stack(cjac), [[0], [0]]
                        )
                    else:
                        jacs = tuple(
                            qml.math.tensordot(qml.math.stack(qjac), c, [[0], [0]])
                            for c in cjac
                            if c is not None
                        )
                    return jacs
                # Multi measurement and multi params
                if not isinstance(cjac, tuple):
                    jacs = tuple(
                        qml.math.tensordot(qml.math.stack(q), qml.math.stack(cjac), [[0], [0]])
                        for q in qjac
                    )
                else:
                    jacs = tuple(
                        tuple(
                            qml.math.tensordot(qml.math.stack(q), c, [[0], [0]])
                            for c in cjac
                            if c is not None
                        )
                        for q in qjac
                    )
                return jacs

            if isinstance(cjac, tuple):
                # Classical processing of multiple arguments is present. Return qjac @ cjac.
                jacs = tuple(
                    qml.math.tensordot(qjac, c, [[-1], [0]]) for c in cjac if c is not None
                )
                if len(jacs) == 1:
                    return jacs[0]
                return jacs

            is_square = cjac.ndim == 2 and cjac.shape[0] == cjac.shape[1]

            if is_square and qml.math.allclose(cjac, qml.numpy.eye(cjac.shape[0])):
                # Classical Jacobian is the identity. No classical processing
                # is present inside the QNode.
                return qjac

            return qml.math.tensordot(qjac, cjac, [[-1], [0]])

        return jacobian_wrapper
