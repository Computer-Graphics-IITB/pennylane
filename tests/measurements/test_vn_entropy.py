# Copyright 2018-2020 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the vn_entropy module"""
import numpy as np

import pennylane as qml


class TestVnEntropy:
    def test_vn_entropy(self):
        """Tests the output of qml.vn_entropy"""
        dev = qml.device("default.mixed", wires=2)

        @qml.qnode(dev)
        def circuit():
            return qml.vn_entropy(wires=0, log_base=2)

        res = circuit()
        expected = 0
        assert np.allclose(res, expected)
        assert np.allclose(
            qml.vn_entropy(wires=0, log_base=2).process_state(
                state=dev.state, device_wires=dev.wires
            ),
            expected,
        )