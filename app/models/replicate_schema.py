"""
Pydantic models for Replicate API integration
"""
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class ReplicateVideoRequest(BaseModel):
    """Request model for Replicate video generation"""
    prompt: str = Field(..., description="Text prompt for video generation")
    image_url: str = Field(..., description="URL of the input image", alias="image")
    duration: Optional[int] = Field(10, description="Video duration in seconds", ge=1, le=30)
    resolution: Optional[str] = Field("720p", description="Video resolution (e.g., '720p', '1080p')")
    aspect_ratio: Optional[str] = Field("9:16", description="Video aspect ratio (e.g., '9:16', '16:9')")
    camera_fixed: Optional[bool] = Field(False, description="Whether camera should be fixed")

    class Config:
        populate_by_name = True


class ReplicateVideoResponse(BaseModel):
    """Response model for Replicate video generation"""
    prediction_id: str = Field(..., description="Unique prediction ID from Replicate")
    status: str = Field(..., description="Status of the prediction (starting, processing, succeeded, failed, canceled)")
    output: Optional[Any] = Field(None, description="Output video URL(s) when completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    logs: Optional[str] = Field(None, description="Processing logs")
    created_at: Optional[str] = Field(None, description="Prediction creation timestamp")
    urls: Optional[Dict[str, str]] = Field(None, description="URLs for various operations")


class ReplicateWebhookRequestUrls(BaseModel):
    """URLs returned in webhook request"""
    get: Optional[str] = None
    cancel: Optional[str] = None


class ReplicateWebhookRequest(BaseModel):
    """Webhook payload from Replicate"""
    id: str = Field(..., description="Prediction ID")
    model: str = Field(..., description="Model used for prediction")
    version: str = Field(..., description="Model version")
    logs: Optional[str] = Field("", description="Processing logs")
    output: Optional[Any] = Field(None, description="Output video URL(s) or data")
    data_removed: bool = Field(False, description="Whether prediction data was removed")
    error: Optional[str] = Field(None, description="Error message if failed")
    status: str = Field(..., description="Prediction status")
    created_at: str = Field(..., description="Creation timestamp")
    urls: Optional[ReplicateWebhookRequestUrls] = Field(None, description="Related URLs")


class WebhookData(BaseModel):
    """Complete webhook data including headers"""
    webhook_id: str = Field(..., description="Webhook event ID", alias="webhook-id")
    webhook_timestamp: str = Field(..., description="Webhook timestamp", alias="webhook-timestamp")
    webhook_signature: str = Field(..., description="Webhook signature for verification", alias="webhook-signature")
    raw_body: ReplicateWebhookRequest = Field(..., description="Webhook request payload")

    class Config:
        populate_by_name = True


class ReplicatePredictionStatusRequest(BaseModel):
    """Request model for checking prediction status"""
    prediction_id: str = Field(..., description="Prediction ID to check")
