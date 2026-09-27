import cv2
import numpy as np
from typing import Union
import os

def prepare_image_for_vision_model(
    image_input: Union[str, bytes],
    max_dimension: int = 1024,
    jpeg_quality: int = 80
) -> bytes:
    """
    Reads an image from a file path or bytes, resizes it such that its maximum
    dimension is at most `max_dimension` while maintaining aspect ratio, and
    compresses it to JPEG format with the specified quality.

    Args:
        image_input: File path (str) or image bytes (bytes).
        max_dimension: Maximum allowed dimension (width or height).
        jpeg_quality: JPEG compression quality (0-100).

    Returns:
        Processed image as bytes in JPEG format.

    Raises:
        ValueError: If the image cannot be read or processed.
        TypeError: If the input type is unsupported.
    """
    try:
        # Load image
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise ValueError(f"Image path does not exist: {image_input}")
            img = cv2.imread(image_input)
            if img is None:
                raise ValueError(f"Failed to read image from path: {image_input}")
        elif isinstance(image_input, bytes):
            nparr = np.frombuffer(image_input, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Failed to decode image from bytes.")
        else:
            raise TypeError("image_input must be a string (path) or bytes.")

        # Calculate new dimensions while maintaining aspect ratio
        height, width = img.shape[:2]
        if max(height, width) > max_dimension:
            scaling_factor = max_dimension / float(max(height, width))
            new_width = int(width * scaling_factor)
            new_height = int(height * scaling_factor)
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)

        # Compress to JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        success, encoded_img = cv2.imencode('.jpg', img, encode_param)

        if not success:
            raise ValueError("Failed to encode image to JPEG.")

        return encoded_img.tobytes()

    except Exception as e:
        raise ValueError(f"Error processing image: {e}") from e
