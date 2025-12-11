# Replicate API Integration

This document describes the Replicate API integration for video generation using the `bytedance/seedance-1-pro` model.

## Configuration

Add the following configuration to your `config.toml` file:

```toml
[replicate]
# Replicate API Key
# Get your API key at https://replicate.com/account/api-tokens
api_key = "your_api_key_here"

# Default model for video generation
model = "bytedance/seedance-1-pro"

# Webhook base URL (optional)
# This should be your publicly accessible endpoint (e.g., via ngrok or production domain)
# Example: "https://your-domain.com" or "https://xxxx.ngrok-free.app"
webhook_base_url = ""
```

## API Endpoints

### 1. Generate Video

**Endpoint:** `POST /api/v1/replicate/videos`

**Description:** Generate a video using Replicate's bytedance/seedance-1-pro model.

**Request Body:**
```json
{
  "prompt": "continuous slow fluid motion, swirling transitions, naturally evolving marbled dynamics, seamless flow, real paint behavior simulation.",
  "image": "https://example.com/image.jpg",
  "duration": 10,
  "resolution": "720p",
  "aspect_ratio": "9:16",
  "camera_fixed": false
}
```

**Response:**
```json
{
  "status": 200,
  "message": "Video generation request submitted successfully",
  "data": {
    "prediction_id": "abc123...",
    "status": "starting",
    "output": null,
    "error": null,
    "created_at": "2024-01-01T00:00:00.000Z",
    "urls": {
      "get": "https://api.replicate.com/v1/predictions/abc123...",
      "cancel": "https://api.replicate.com/v1/predictions/abc123.../cancel"
    }
  }
}
```

**Example cURL:**
```bash
curl -X POST "http://localhost:8080/api/v1/replicate/videos" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "continuous slow fluid motion, swirling transitions",
    "image": "https://example.com/image.jpg",
    "duration": 10,
    "resolution": "720p",
    "aspect_ratio": "9:16",
    "camera_fixed": false
  }'
```

### 2. Get Prediction Status

**Endpoint:** `POST /api/v1/replicate/predictions/status`

**Description:** Check the status of a video generation prediction.

**Request Body:**
```json
{
  "prediction_id": "abc123..."
}
```

**Response:**
```json
{
  "status": 200,
  "message": "Prediction status retrieved successfully",
  "data": {
    "prediction_id": "abc123...",
    "status": "succeeded",
    "output": ["https://replicate.delivery/pbxt/.../output.mp4"],
    "error": null,
    "logs": "...",
    "created_at": "2024-01-01T00:00:00.000Z"
  }
}
```

**Example cURL:**
```bash
curl -X POST "http://localhost:8080/api/v1/replicate/predictions/status" \
  -H "Content-Type: application/json" \
  -d '{
    "prediction_id": "abc123..."
  }'
```

### 3. Webhook Endpoint

**Endpoint:** `POST /api/v1/replicate/webhook`

**Description:** Receives webhook notifications from Replicate when a prediction completes.

**Webhook Configuration:**
When you configure `webhook_base_url` in your config, the system automatically sets up webhook notifications to `{webhook_base_url}/api/v1/replicate/webhook`.

**Webhook Payload Example:**
```json
{
  "id": "abc123...",
  "model": "bytedance/seedance-1-pro",
  "version": "...",
  "status": "succeeded",
  "output": ["https://replicate.delivery/pbxt/.../output.mp4"],
  "error": null,
  "logs": "...",
  "created_at": "2024-01-01T00:00:00.000Z",
  "urls": {
    "get": "https://api.replicate.com/v1/predictions/abc123...",
    "cancel": "https://api.replicate.com/v1/predictions/abc123.../cancel"
  }
}
```

**Webhook Headers:**
- `webhook-id`: Unique webhook event ID
- `webhook-timestamp`: Timestamp of the webhook event
- `webhook-signature`: HMAC signature for webhook verification (not yet implemented)

## Usage Examples

### Python Example

```python
import requests

# Generate video
response = requests.post(
    "http://localhost:8080/api/v1/replicate/videos",
    json={
        "prompt": "continuous slow fluid motion, swirling transitions",
        "image": "https://example.com/image.jpg",
        "duration": 10,
        "resolution": "720p",
        "aspect_ratio": "9:16",
        "camera_fixed": False
    }
)

result = response.json()
prediction_id = result["data"]["prediction_id"]

# Check status
status_response = requests.post(
    "http://localhost:8080/api/v1/replicate/predictions/status",
    json={"prediction_id": prediction_id}
)

status_result = status_response.json()
print(f"Status: {status_result['data']['status']}")
print(f"Output: {status_result['data']['output']}")
```

### JavaScript Example

```javascript
// Generate video
const response = await fetch('http://localhost:8080/api/v1/replicate/videos', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    prompt: 'continuous slow fluid motion, swirling transitions',
    image: 'https://example.com/image.jpg',
    duration: 10,
    resolution: '720p',
    aspect_ratio: '9:16',
    camera_fixed: false
  })
});

const result = await response.json();
const predictionId = result.data.prediction_id;

// Check status
const statusResponse = await fetch('http://localhost:8080/api/v1/replicate/predictions/status', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prediction_id: predictionId })
});

const statusResult = await statusResponse.json();
console.log('Status:', statusResult.data.status);
console.log('Output:', statusResult.data.output);
```

## Testing with ngrok

To test webhook functionality locally:

1. Install ngrok: `npm install -g ngrok` or download from https://ngrok.com/

2. Start your MoneyPrinterTurbo server:
   ```bash
   python main.py
   ```

3. In another terminal, start ngrok:
   ```bash
   ngrok http 8080
   ```

4. Copy the ngrok URL (e.g., `https://abc123.ngrok-free.app`)

5. Update your `config.toml`:
   ```toml
   [replicate]
   webhook_base_url = "https://abc123.ngrok-free.app"
   ```

6. Restart the server and make a video generation request. Replicate will send webhook notifications to your local server via ngrok.

## Status Values

Possible prediction statuses:
- `starting` - Prediction is initializing
- `processing` - Prediction is running
- `succeeded` - Prediction completed successfully
- `failed` - Prediction failed with an error
- `canceled` - Prediction was canceled

## Error Handling

The API returns appropriate HTTP status codes:
- `200` - Success
- `400` - Bad request (invalid parameters)
- `500` - Server error (API key not configured, network errors, etc.)

## Notes

- Video generation may take several minutes depending on the duration and resolution
- If no webhook is configured, the API uses synchronous mode with `Prefer: wait` header (may timeout for long operations)
- Webhook mode is recommended for production use
- The output is typically an array of video URLs
- Generated videos are hosted on Replicate's CDN

## Implementation Files

- Configuration: `app/config/config.py`
- Service Layer: `app/services/replicate.py`
- Controllers: `app/controllers/v1/replicate.py`
- Models/Schemas: `app/models/replicate_schema.py`
- Router: `app/router.py`

## Support

For issues or questions:
- Replicate API Documentation: https://replicate.com/docs
- MoneyPrinterTurbo Issues: https://github.com/harry0703/MoneyPrinterTurbo/issues
