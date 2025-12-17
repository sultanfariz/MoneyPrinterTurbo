"""
Webhook result manager for storing and retrieving Replicate webhook results
"""
import threading
import time
from typing import Optional, Dict, Any
from loguru import logger


class WebhookResultManager:
    """Thread-safe manager for storing and retrieving webhook results"""

    def __init__(self):
        self._results = {}  # callback_id -> result data
        self._lock = threading.Lock()

    def set_result(self, callback_id: str, result: Dict[str, Any]):
        """
        Store webhook result

        Args:
            callback_id: Unique callback identifier
            result: Result data from webhook
        """
        with self._lock:
            self._results[callback_id] = result
            logger.info(f"Stored webhook result for callback_id: {callback_id}")

    def get_result(self, callback_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve webhook result

        Args:
            callback_id: Unique callback identifier

        Returns:
            Result data if available, None otherwise
        """
        with self._lock:
            return self._results.get(callback_id)

    def wait_for_result(
        self,
        callback_id: str,
        timeout: int = 600,
        poll_interval: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Wait for webhook result with timeout

        Args:
            callback_id: Unique callback identifier
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check in seconds

        Returns:
            Result data if received, None if timeout
        """
        start_time = time.time()

        logger.info(f"Waiting for webhook result for callback_id: {callback_id}")

        while time.time() - start_time < timeout:
            result = self.get_result(callback_id)
            if result:
                elapsed_time = time.time() - start_time
                logger.success(f"Received webhook result after {elapsed_time:.1f}s for callback_id: {callback_id}")
                return result

            time.sleep(poll_interval)

        elapsed_time = time.time() - start_time
        logger.error(f"Webhook result timeout after {elapsed_time:.1f}s for callback_id: {callback_id}")
        return None

    def remove_result(self, callback_id: str):
        """
        Remove webhook result from storage

        Args:
            callback_id: Unique callback identifier
        """
        with self._lock:
            if callback_id in self._results:
                del self._results[callback_id]
                logger.debug(f"Removed webhook result for callback_id: {callback_id}")


# Global instance
webhook_result_manager = WebhookResultManager()
