"""
Replicate API controller for video generation and webhook handling
"""
import hashlib
import hmac
from typing import Dict, Any
from fastapi import Request, Header, HTTPException, Path
from loguru import logger

from app.config import config
from app.controllers.v1.base import new_router
from app.models.replicate_schema import (
    ReplicateVideoRequest,
    ReplicateVideoResponse,
    ReplicateWebhookRequest,
    ReplicatePredictionStatusRequest,
)
from app.models.schema import BaseResponse
from app.services import replicate as replicate_service
from app.services.webhook_manager import webhook_result_manager

# Create router
router = new_router()


@router.post("/replicate/videos", response_model=BaseResponse, summary="Generate video using Replicate API")
def generate_video(body: ReplicateVideoRequest):
    """
    Generate a video using Replicate's bytedance/seedance-1-pro model

    Args:
        body: Video generation parameters including prompt, image URL, duration, etc.

    Returns:
        BaseResponse containing prediction ID and status

    Raises:
        HTTPException: If video generation fails
    """
    try:
        # Build webhook URL if configured
        webhook_url = None
        webhook_base_url = config.replicate.get("webhook_base_url", "")
        if webhook_base_url:
            webhook_url = f"{webhook_base_url}/api/v1/replicate/webhook"

        # Call Replicate service
        result = replicate_service.generate_video(
            prompt=body.prompt,
            image_url=body.image_url,
            duration=body.duration,
            resolution=body.resolution,
            aspect_ratio=body.aspect_ratio,
            camera_fixed=body.camera_fixed,
            webhook_url=webhook_url
        )

        # Prepare response
        response_data = ReplicateVideoResponse(
            prediction_id=result.get("id", ""),
            status=result.get("status", ""),
            output=result.get("output"),
            error=result.get("error"),
            logs=result.get("logs"),
            created_at=result.get("created_at"),
            urls=result.get("urls")
        )

        return BaseResponse(
            status=200,
            message="Video generation request submitted successfully",
            data=response_data.dict()
        )

    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")


@router.post("/replicate/predictions/status", response_model=BaseResponse, summary="Get prediction status")
def get_prediction_status(body: ReplicatePredictionStatusRequest):
    """
    Get the status of a Replicate prediction

    Args:
        body: Request containing prediction ID

    Returns:
        BaseResponse containing prediction status and output

    Raises:
        HTTPException: If status check fails
    """
    try:
        result = replicate_service.get_prediction_status(body.prediction_id)

        response_data = ReplicateVideoResponse(
            prediction_id=result.get("id", ""),
            status=result.get("status", ""),
            output=result.get("output"),
            error=result.get("error"),
            logs=result.get("logs"),
            created_at=result.get("created_at"),
            urls=result.get("urls")
        )

        return BaseResponse(
            status=200,
            message="Prediction status retrieved successfully",
            data=response_data.dict()
        )

    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get prediction status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@router.post("/replicate/webhook/{callback_id}", summary="Webhook endpoint for Replicate completion notifications")
async def replicate_webhook(
    callback_id: str = Path(..., description="Unique callback identifier"),
    request: Request = None,
    webhook_id: str = Header(None, alias="webhook-id"),
    webhook_timestamp: str = Header(None, alias="webhook-timestamp"),
    webhook_signature: str = Header(None, alias="webhook-signature"),
):
    """
    Webhook endpoint to receive Replicate prediction completion notifications

    This endpoint receives POST requests from Replicate when a prediction completes.
    It stores the result so the waiting video generation process can continue.

    Args:
        callback_id: Unique callback identifier from URL path
        request: FastAPI request object
        webhook_id: Webhook event ID from headers
        webhook_timestamp: Webhook timestamp from headers
        webhook_signature: Webhook signature for verification from headers

    Returns:
        Dict confirming receipt

    Raises:
        HTTPException: If webhook validation fails
    """
    try:
        # Parse request body
        body = await request.json()

        logger.info(f"Received webhook from Replicate for callback_id: {callback_id}")
        logger.debug(f"Webhook ID: {webhook_id}")
        logger.debug(f"Webhook Timestamp: {webhook_timestamp}")
        logger.debug(f"Webhook Signature: {webhook_signature}")
        logger.debug(f"Webhook Body: {body}")

        # Validate webhook payload
        if not body:
            raise HTTPException(status_code=400, detail="Empty webhook payload")

        # Parse webhook request
        webhook_request = ReplicateWebhookRequest(**body)

        # Log prediction details
        logger.info(f"Prediction ID: {webhook_request.id}")
        logger.info(f"Status: {webhook_request.status}")
        logger.info(f"Model: {webhook_request.model}")

        # Store the result for the waiting process
        result_data = {
            "id": webhook_request.id,
            "status": webhook_request.status,
            "output": webhook_request.output,
            "error": webhook_request.error,
            "logs": webhook_request.logs,
            "created_at": webhook_request.created_at,
        }
        webhook_result_manager.set_result(callback_id, result_data)

        if webhook_request.status == "succeeded":
            logger.success(f"Video generation succeeded for callback_id: {callback_id}")
            logger.info(f"Output: {webhook_request.output}")

        elif webhook_request.status == "failed":
            logger.error(f"Video generation failed for callback_id: {callback_id}")
            logger.error(f"Error: {webhook_request.error}")

        elif webhook_request.status == "canceled":
            logger.warning(f"Video generation was canceled for callback_id: {callback_id}")

        else:
            logger.info(f"Prediction in status: {webhook_request.status} for callback_id: {callback_id}")

        return {
            "status": "received",
            "callback_id": callback_id,
            "prediction_id": webhook_request.id,
            "webhook_id": webhook_id,
            "message": "Webhook processed and result stored successfully"
        }

    except Exception as e:
        logger.error(f"Webhook processing failed for callback_id {callback_id}: {str(e)}")
        # Return 200 to prevent Replicate from retrying
        # You might want to change this behavior based on your needs
        return {
            "status": "error",
            "callback_id": callback_id,
            "message": str(e)
        }


def verify_webhook_signature(
    webhook_id: str,
    webhook_timestamp: str,
    webhook_signature: str,
    body: bytes,
    secret: str
) -> bool:
    """
    Verify the webhook signature from Replicate

    Args:
        webhook_id: Webhook event ID
        webhook_timestamp: Webhook timestamp
        webhook_signature: Signature to verify
        body: Raw request body
        secret: Webhook secret for verification

    Returns:
        True if signature is valid, False otherwise
    """
    # Construct the signed content
    signed_content = f"{webhook_id}.{webhook_timestamp}.{body.decode('utf-8')}"

    # Calculate expected signature
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        signed_content.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Compare signatures
    return hmac.compare_digest(webhook_signature, f"v1,{expected_signature}")
