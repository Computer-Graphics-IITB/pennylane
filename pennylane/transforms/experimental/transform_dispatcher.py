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
"""
This module contains the transform dispatcher.
"""
import functools
from typing import get_type_hints

import pennylane as qml


class TransformError(Exception):
    """Raised when there is an error with the transform logic"""


class TransformDispatcher:
    r"""This object is developper facing and should not be used directly.
    Convert a transform that has the signature (tape -> Sequence(tape), fn) to a transform dispatcher that can act
    on tape, qfunc and qnode."""

    def __init__(self, transform, expand_transform=None, qnode_postprocessing=None):
        if not callable(transform):
            raise TransformError(
                f"The function to register, {transform}, "
                "does not appear to be a valid Python function or callable."
            )

        self._transform = transform
        functools.update_wrapper(self, transform)
        self._expand_transform = expand_transform
        self._qnode_postprocessing = qnode_postprocessing

    def __call__(self, *targs, **tkwargs):
        obj = None

        if targs:
            # assume the first argument passed to the transform
            # is the object we wish to transform
            obj, *targs = targs

        if isinstance(obj, qml.tape.QuantumTape):
            return self._transform(obj, *targs, **tkwargs)
        elif isinstance(obj, qml.QNode):
            return self.default_qnode_transform(obj,
                                                targs,
                                                tkwargs,
                                                expand_transform=self._expand_transform,
                                                qnode_postprocessing=self._qnode_postprocessing)
        elif callable(obj):
            return self.default_qfunc_transform(obj, targs, tkwargs)
        else:
            TransformError("The object on which is the transform is applied is not valid."
                           "It can be a tape, a QNode or a qfunc.")

    @property
    def transform(self):
        return self._transform

    @property
    def expand_transform(self):
        return self._expand_transform

    @property
    def qnode_postprocessing(self):
        return self._qnode_postprocessing

    def default_qfunc_transform(self, qfunc, targs, tkwargs):
        """Register a qnode transformation"""

        def wrapper(*args, **kwargs):
            tape = qml.tape.make_qscript(qfunc)(*args, **kwargs)
            new_tape, _ = self._transform(tape, *targs, **tkwargs)

            for op in new_tape[0].circuit:
                qml.apply(op)

        return wrapper

    def default_qnode_transform(self, qnode, targs, tkwargs):
        """Register a qnode transformation"""
        if self.expand_transform:
            qnode.add_transform(
                TransformContainer(self._expand_transform)
            )
        qnode.add_transform(
            TransformContainer(self._transform, targs, tkwargs, self._qnode_postprocessing)
        )
        return qnode


def transform(transform, expand_transform=None, qnode_postprocessing=None):
    """
    Signature and type validation for the transform and its expand function and qnode post processing.

    TODO: Make it clear what is a transform

    TODO: add example of what is expected from a transform.
    """
    # Check signature of transform to force the fn style (tape, ...) - > (batch_tape, fn)
    signature_transform = get_type_hints(transform)
    _transform_signature_check(signature_transform)

    if expand_transform:
        # Check the signature of expand_tranform to force the fn style (tape, ...) - > (batch_tape, fn)
        signature_expand_transform = get_type_hints(expand_transform)
        # TODO: Check it only contains one tape
        _transform_signature_check(signature_expand_transform)

    # Check the signature of qnode_postprocessing

    return TransformDispatcher(transform, expand_transform=expand_transform, qnode_postprocessing=qnode_postprocessing)


def _transform_signature_check(signature):
    """Check the signature of a tranform"""
    tape = signature.get('tape', None)

    if tape is None:
        TransformError("Their must be an argument tape.")
    if not isinstance(tape, qml.tape.QuantumTape):
        TransformError("The type of the tape argument must be a QuantumTape")

    ret = signature.get('return', None)

    if ret is None:
        TransformError("Their must be an argument tape")


class TransformContainer:
    def __init__(self, transform, args=None, kwargs=None, qnode_processing=None):
        self.transform = transform
        self.targs = args if args else []
        self.tkwargs = kwargs if kwargs else {}
        self.qnode_processing = qnode_processing
