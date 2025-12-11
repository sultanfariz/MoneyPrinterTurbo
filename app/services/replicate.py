"""
Replicate API integration for video generation
"""
import json
import requests
from typing import Optional, Dict, Any
from loguru import logger

from app.config import config


def generate_video(
    prompt: str,
    image_url: str,
    duration: int = 10,
    resolution: str = "720p",
    aspect_ratio: str = "9:16",
    camera_fixed: bool = False,
    webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate video using Replicate's bytedance/seedance-1-pro model

    Args:
        prompt: Text prompt for video generation
        image_url: URL of the input image
        duration: Video duration in seconds (default: 10)
        resolution: Video resolution (default: "720p")
        aspect_ratio: Video aspect ratio (default: "9:16")
        camera_fixed: Whether camera should be fixed (default: False)
        webhook_url: Optional webhook URL for completion notification

    Returns:
        Dict containing the prediction response from Replicate API

    Raises:
        ValueError: If API key is not configured
        requests.exceptions.RequestException: If API request fails
    """
    # Get API key from config
    api_key = config.replicate.get("api_key", "")
    if not api_key:
        raise ValueError("Replicate API key not configured. Please set replicate.api_key in config.toml")

    # Get model from config or use default
    model = config.replicate.get("model", "bytedance/seedance-1-pro")

    # Construct API URL
    api_url = f"https://api.replicate.com/v1/models/{model}/predictions"

    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Add Prefer: wait header if no webhook is provided
    if not webhook_url:
        headers["Prefer"] = "wait"

    # Prepare request payload
    payload = {
        "input": {
            "prompt": prompt,
            "image": image_url,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "camera_fixed": camera_fixed
        }
    }

    # Add webhook configuration if provided
    if webhook_url:
        payload["webhook"] = webhook_url
        payload["webhook_events_filter"] = ["completed"]

    logger.info(f"Sending video generation request to Replicate API for model: {model}")
    logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

    try:
        # Make API request
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=300  # 5 minute timeout for synchronous requests
        )

        # Raise exception for error status codes
        response.raise_for_status()

        result = response.json()
        logger.info(f"Replicate API request successful. Prediction ID: {result.get('id', 'N/A')}")
        logger.debug(f"Response: {json.dumps(result, indent=2)}")

        return result

    except requests.exceptions.Timeout:
        logger.error("Replicate API request timed out")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Replicate API request failed: {str(e)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        raise


def get_prediction_status(prediction_id: str) -> Dict[str, Any]:
    """
    Get the status of a prediction

    Args:
        prediction_id: The ID of the prediction to check

    Returns:
        Dict containing the prediction status

    Raises:
        ValueError: If API key is not configured
        requests.exceptions.RequestException: If API request fails
    """
    # Get API key from config
    api_key = config.replicate.get("api_key", "")
    if not api_key:
        raise ValueError("Replicate API key not configured. Please set replicate.api_key in config.toml")

    # Construct API URL
    api_url = f"https://api.replicate.com/v1/predictions/{prediction_id}"

    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    logger.info(f"Checking prediction status for ID: {prediction_id}")

    try:
        # Make API request
        response = requests.get(api_url, headers=headers, timeout=30)

        # Raise exception for error status codes
        response.raise_for_status()

        result = response.json()
        logger.info(f"Prediction status: {result.get('status', 'N/A')}")

        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get prediction status: {str(e)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        raise


def cancel_prediction(prediction_id: str) -> Dict[str, Any]:
    """
    Cancel a running prediction

    Args:
        prediction_id: The ID of the prediction to cancel

    Returns:
        Dict containing the cancellation response

    Raises:
        ValueError: If API key is not configured
        requests.exceptions.RequestException: If API request fails
    """
    # Get API key from config
    api_key = config.replicate.get("api_key", "")
    if not api_key:
        raise ValueError("Replicate API key not configured. Please set replicate.api_key in config.toml")

    # Construct API URL
    api_url = f"https://api.replicate.com/v1/predictions/{prediction_id}/cancel"

    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    logger.info(f"Cancelling prediction ID: {prediction_id}")

    try:
        # Make API request
        response = requests.post(api_url, headers=headers, timeout=30)

        # Raise exception for error status codes
        response.raise_for_status()

        result = response.json()
        logger.info(f"Prediction cancelled successfully")

        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to cancel prediction: {str(e)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        raise
