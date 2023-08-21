#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from unittest.mock import patch

import torch
import torch.distributed.launcher as launcher
from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
from torch.distributed.fsdp.fully_sharded_data_parallel import MixedPrecision
from torch.nn.parallel import DistributedDataParallel as DDP
from torchtnt.utils.env import init_from_env
from torchtnt.utils.prepare_module import (
    _is_fsdp_module,
    DDPStrategy,
    FSDPStrategy,
    prepare_ddp,
    prepare_fsdp,
)
from torchtnt.utils.test_utils import get_pet_launch_config
from torchtnt.utils.version import is_torch_version_geq_2_0

if is_torch_version_geq_2_0():
    from torch.distributed._composable import fully_shard


class PrepareModelTest(unittest.TestCase):

    # pyre-fixme[4]: Attribute must be annotated.
    cuda_available = torch.cuda.is_available()

    @unittest.skipUnless(
        condition=(cuda_available), reason="This test should run on a GPU host."
    )
    # pyre-fixme[56]: Pyre was not able to infer the type of argument
    #  `torch.distributed.is_available()` to decorator factory `unittest.skipUnless`.
    @unittest.skipUnless(
        torch.distributed.is_available(), reason="Torch distributed is needed to run"
    )
    def test_prepare_ddp(self) -> None:
        config = get_pet_launch_config(2)
        launcher.elastic_launch(config, entrypoint=self._test_prepare_ddp)()

    @staticmethod
    def _test_prepare_ddp() -> None:
        module = torch.nn.Linear(2, 2)
        device = init_from_env()
        ddp_module = prepare_ddp(
            module,
            device,
            DDPStrategy(find_unused_parameters=True, gradient_as_bucket_view=True),
        )
        tc = unittest.TestCase()
        tc.assertTrue(isinstance(ddp_module, DDP))

    @unittest.skipUnless(
        condition=(cuda_available), reason="This test should run on a GPU host."
    )
    # pyre-fixme[56]: Pyre was not able to infer the type of argument
    #  `torch.distributed.is_available()` to decorator factory `unittest.skipUnless`.
    @unittest.skipUnless(
        torch.distributed.is_available(), reason="Torch distributed is needed to run"
    )
    def test_prepare_fsdp(self) -> None:
        config = get_pet_launch_config(2)
        launcher.elastic_launch(config, entrypoint=self._test_prepare_fsdp)()

    @staticmethod
    def _test_prepare_fsdp() -> None:
        module = torch.nn.Linear(2, 2)
        device = init_from_env()
        fsdp_module = prepare_fsdp(module, device, FSDPStrategy(limit_all_gathers=True))
        tc = unittest.TestCase()
        tc.assertTrue(isinstance(fsdp_module, FSDP))

    # pyre-fixme[56]: Pyre was not able to infer the type of argument
    #  `torch.distributed.is_available()` to decorator factory `unittest.skipUnless`.
    @unittest.skipUnless(
        torch.distributed.is_available(), reason="Torch distributed is needed to run"
    )
    @unittest.skipUnless(
        condition=cuda_available, reason="This test needs a GPU host to run."
    )
    def test_fsdp_pytorch_version(self) -> None:
        """
        Test that a RuntimeError is thrown when using FSDP, and PyTorch < v1.12
        """
        config = get_pet_launch_config(2)
        launcher.elastic_launch(config, entrypoint=self._test_fsdp_pytorch_version)()

    @staticmethod
    def _test_fsdp_pytorch_version() -> None:
        device = init_from_env()
        module = torch.nn.Linear(2, 2).to(device)

        tc = unittest.TestCase()
        with patch(
            "torchtnt.utils.prepare_module.is_torch_version_geq_1_12",
            return_value=False,
        ), tc.assertRaisesRegex(
            RuntimeError,
            "Please install PyTorch 1.12 or higher to use FSDP: https://pytorch.org/get-started/locally/",
        ):
            _ = prepare_fsdp(module, device, FSDPStrategy())

    @staticmethod
    def _test_is_fsdp_module() -> None:
        torch.distributed.init_process_group("gloo")
        model = torch.nn.Linear(1, 1)
        assert not _is_fsdp_module(model)
        model = FSDP(torch.nn.Linear(1, 1))
        assert _is_fsdp_module(model)
        model = torch.nn.Linear(1, 1)
        if is_torch_version_geq_2_0():
            fully_shard(model)
            assert _is_fsdp_module(model)

    @unittest.skipUnless(
        torch.distributed.is_available(), reason="Torch distributed is needed to run"
    )
    # pyre-fixme[56]: Pyre was not able to infer the type of argument
    #  `torch.cuda.is_available() and torch.cuda.device_count() > 2` to decorator
    #  factory `unittest.skipUnless`.
    @unittest.skipUnless(
        condition=torch.cuda.is_available() and torch.cuda.device_count() > 2,
        reason="This test needs 2 GPUs to run.",
    )
    def test_is_fsdp_module(self) -> None:
        config = get_pet_launch_config(2)
        launcher.elastic_launch(config, entrypoint=self._test_is_fsdp_module)()

    # pyre-fixme[56]: Pyre was not able to infer the type of argument
    #  `torch.distributed.is_available()` to decorator factory `unittest.skipUnless`.
    @unittest.skipUnless(
        torch.distributed.is_available(), reason="Torch distributed is needed to run"
    )
    @unittest.skipUnless(
        condition=cuda_available, reason="This test needs a GPU host to run."
    )
    def test_fdsp_precision(self) -> None:
        config = get_pet_launch_config(2)
        launcher.elastic_launch(config, entrypoint=self._test_fdsp_precision)()

    @staticmethod
    def _test_fdsp_precision() -> None:
        module = torch.nn.Linear(1, 1)
        device = init_from_env()
        mixed_precision = MixedPrecision(
            param_dtype=torch.float64,
        )
        fsdp_module = prepare_fsdp(
            module, device, FSDPStrategy(mixed_precision=mixed_precision)
        )
        tc = unittest.TestCase()
        tc.assertTrue(isinstance(fsdp_module, FSDP))
        tc.assertEqual(
            fsdp_module.mixed_precision.param_dtype, mixed_precision.param_dtype
        )
