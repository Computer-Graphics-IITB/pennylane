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
"""This experimental directory contains the next generation interface
for PennyLane devices.

"""
from .execution_config import ExecutionConfig, DefaultExecutionConfig
from .device_api import Device
from .default_qubit_2 import DefaultQubit2
from .quimb_qubit import QuimbQubit
from .mps_qubit import MPSQubit
