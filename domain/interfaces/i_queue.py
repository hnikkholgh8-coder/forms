#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from typing import Dict, Any
from security.audit_logger import exir_boundary_tracer

class IQueueProvider(ABC):
    """
    Abstract Queue Provider Interface.
    Allows sending task messages or events asynchronously without knowing the message broker (RabbitMQ/Redis/Celery).
    """

    @abstractmethod
    async def publish_task(self, queue_name: str, payload: Dict[str, Any]) -> bool:
        """
        Asynchronously publishes a task to the specified queue.
        """
        pass
