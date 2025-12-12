#!/usr/bin/env python3
# -*-coding:UTF-8 -*
"""
============================================================================
UTILITY SCRIPT - NOT PART OF CORE AIL FRAMEWORK
============================================================================

This is a utility script for manually loading images into AIL.
It is NOT part of the standard AIL codebase and is excluded from:
  - Code coverage checks
  - Standard AIL testing
  - Production deployments

Purpose:
  Load an image file into AIL for testing or manual import.

Usage:
  python3 tools/load_image.py <path_to_image>

Example:
  python3 tools/load_image.py tests/images/RightWing.PNG

============================================================================
"""

import os
import sys

# Set AIL environment variables if not already set
if 'AIL_BIN' not in os.environ:
    # Try to detect AIL_BIN from script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ail_bin = os.path.join(script_dir, '..', 'bin')
    if os.path.exists(ail_bin):
        os.environ['AIL_BIN'] = os.path.abspath(ail_bin)
    else:
        print("Error: AIL_BIN not set and could not auto-detect")
        print("Please set AIL_BIN environment variable or run from AIL directory")
        sys.exit(1)

if 'AIL_HOME' not in os.environ:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ail_home = os.path.join(script_dir, '..')
    if os.path.exists(os.path.join(ail_home, 'bin')):
        os.environ['AIL_HOME'] = os.path.abspath(ail_home)

sys.path.append(os.environ['AIL_BIN'])

from lib.objects import Images
from lib.ail_queues import AILQueue
from packages import Date

def load_image(image_path):
    """
    Load an image file into AIL
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Image object if successful, None otherwise
    """
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        return None
    
    print(f"Reading image from: {image_path}")
    
    # Read image content
    with open(image_path, 'rb') as f:
        content = f.read()
    
    if not content:
        print("Error: Image file is empty")
        return None
    
    print(f"Image size: {len(content)} bytes")
    
    # Create image object (this calculates SHA256 and stores the file)
    print("Creating image object...")
    image = Images.create(content, size_limit=-1, b64=False, force=False)
    
    if not image:
        print("Error: Failed to create image object")
        return None
    
    print(f"Image created with ID: {image.id}")
    print(f"Image global ID: {image.get_global_id()}")
    
    # Set the date so it appears in date range views
    current_date = Date.get_today_date_str()
    print(f"Setting date to: {current_date}")
    image.add(current_date, None)  # None because it's not associated with a message/item
    
    # Ensure image is in image:all set (even if it already existed)
    # This fixes the case where metadata exists but image wasn't in the set
    from lib.ConfigLoader import ConfigLoader
    config = ConfigLoader()
    r_object = config.get_db_conn("Kvrocks_Objects")
    r_object.sadd('image:all', image.id)
    
    # Check if image already existed
    if image.exists():
        print("Image already exists in AIL (date updated, ensured in image:all set)")
    else:
        print("New image added to AIL")
    
    # Add to queue for processing by modules
    print("Adding image to processing queue...")
    try:
        queue = AILQueue('Global', os.getpid())
        message = f'{current_date}'
        queue.send_message(image.get_global_id(), message=message, queue_name='Global')
        print(f"Image queued for processing in Global module")
        print(f"Modules will process: OcrExtractor, CodeReader, Exif, etc.")
    except Exception as e:
        print(f"Warning: Could not add to queue (this is okay if running outside AIL environment): {e}")
        print("Image object created but not queued for processing")
    
    return image

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 tools/load_image.py <path_to_image>")
        print("\nExample:")
        print("  python3 tools/load_image.py tests/images/RightWing.PNG")
        sys.exit(1)
    
    image_path = sys.argv[1]
    image = load_image(image_path)
    
    if image:
        print("\n" + "="*60)
        print("SUCCESS: Image loaded into AIL")
        print("="*60)
        print(f"Image ID (SHA256): {image.id}")
        print(f"Global ID: {image.get_global_id()}")
        print(f"File path: {image.get_filepath()}")
        print(f"\nYou can view the image in AIL using:")
        print(f"  - Correlation view: /correlation/show?type=image&id={image.id}")
        print(f"  - Direct image: /image/{image.id}")
        print("\nThe image will be processed by AIL modules:")
        print("  - OcrExtractor: Extract text from image")
        print("  - CodeReader: Extract QR codes and barcodes")
        print("  - Exif: Extract EXIF metadata")
        print("  - Images: Generate description via Ollama (if enabled)")
    else:
        print("\nFAILED: Could not load image")
        sys.exit(1)
