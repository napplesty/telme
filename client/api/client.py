"""HTTP client for server communication."""
import asyncio
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import ClientError, ClientResponseError, ClientTimeout

from client.config import config
from client.utils.logger import get_logger

logger = get_logger(__name__)


class APIClientError(Exception):
    """API client error."""
    pass


class APIClient:
    """Async HTTP client for server communication."""

    def __init__(self, server_url: Optional[str] = None, api_version: str = "v1"):
        """Initialize API client.

        Args:
            server_url: Server URL (e.g., http://localhost:8000). Defaults to config value.
            api_version: API version string.
        """
        self.server_url = server_url or config.SERVER_URL
        self.api_version = api_version
        self.api_prefix = f"/api/{api_version}"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                base_url=self.server_url,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("HTTP session closed")

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path (without API prefix).
            **kwargs: Additional arguments for aiohttp request.

        Returns:
            Response JSON data.

        Raises:
            APIClientError: If request fails.
        """
        session = await self._get_session()
        # Add API prefix to endpoint
        full_url = f"{self.api_prefix}{endpoint}"

        # Retry logic with exponential backoff
        max_retries = config.MAX_RETRY
        retry_delay = config.RETRY_DELAY

        for attempt in range(max_retries):
            try:
                async with session.request(method, full_url, **kwargs) as response:
                    # Check for HTTP errors
                    if response.status >= 400:
                        error_data = await response.json()
                        error_msg = error_data.get("detail", "Unknown error")
                        raise APIClientError(f"HTTP {response.status}: {error_msg}")

                    # Return JSON response
                    return await response.json()

            except ClientResponseError as e:
                logger.error(f"HTTP error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    raise APIClientError(f"Request failed after {max_retries} attempts: {e}") from e

            except ClientError as e:
                logger.error(f"Network error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    raise APIClientError(f"Network error after {max_retries} attempts: {e}") from e

            # Wait before retrying (exponential backoff)
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))

        # This should never be reached, but just in case
        raise APIClientError("Request failed")

    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path.
            **kwargs: Additional arguments.

        Returns:
            Response JSON data.
        """
        return await self._request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path.
            **kwargs: Additional arguments.

        Returns:
            Response JSON data.
        """
        return await self._request("POST", endpoint, **kwargs)

    async def health_check(self) -> bool:
        """Check server health.

        Returns:
            True if server is healthy, False otherwise.
        """
        try:
            # Health endpoint is at root, not under /api/v1
            session = await self._get_session()
            async with session.get("/health") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "healthy"
                return False
        except Exception:
            return False

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
