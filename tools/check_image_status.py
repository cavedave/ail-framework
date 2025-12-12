#!/usr/bin/env python3
# -*-coding:UTF-8 -*
"""
Script to check image status and diagnose issues
"""

import os
import sys
from hashlib import sha256

# Set AIL environment variables
if 'AIL_BIN' not in os.environ:
    os.environ['AIL_BIN'] = '/opt/ail-framework/bin'
if 'AIL_HOME' not in os.environ:
    os.environ['AIL_HOME'] = '/opt/ail-framework'

sys.path.append(os.environ['AIL_BIN'])

from lib.objects import Images
from lib.ConfigLoader import ConfigLoader
from packages import Date

def check_image_status(image_path=None):
    """Check status of images in AIL"""
    config = ConfigLoader()
    r_object = config.get_db_conn("Kvrocks_Objects")
    
    print("="*60)
    print("AIL Image Status Check")
    print("="*60)
    
    # Check if image:all set exists and count
    all_images = r_object.smembers('image:all')
    print(f"\nTotal images in 'image:all' set: {len(all_images)}")
    
    if len(all_images) == 0:
        print("⚠️  No images found in database!")
        print("\nThis could mean:")
        print("  - The image wasn't properly added")
        print("  - The image file exists but wasn't registered")
        return
    
    # Check specific image if path provided
    if image_path and os.path.exists(image_path):
        print(f"\nChecking specific image: {image_path}")
        with open(image_path, 'rb') as f:
            content = f.read()
        image_id = sha256(content).hexdigest()
        print(f"Expected SHA256: {image_id}")
        
        image = Images.Image(image_id)
        print(f"Image exists in DB: {image.exists()}")
        print(f"Image file exists: {os.path.exists(image.get_filepath())}")
        print(f"First seen: {image.get_first_seen()}")
        print(f"Last seen: {image.get_last_seen()}")
        print(f"In 'image:all' set: {image_id in all_images or image_id.encode() in all_images}")
        
        # Check date ranges
        current_date = Date.get_today_date_str()
        date_key = f'image:date:{current_date}'
        in_date_range = r_object.zscore(date_key, image_id)
        print(f"In today's date range ({current_date}): {in_date_range is not None}")
        
        if in_date_range is None:
            print(f"\n⚠️  Image is NOT in date range for {current_date}")
            print("This is why it doesn't show up in the date range view!")
    
    # List all images with their dates
    print(f"\n{'='*60}")
    print("All images in system:")
    print(f"{'='*60}")
    for img_id in list(all_images)[:10]:  # Show first 10
        if isinstance(img_id, bytes):
            img_id = img_id.decode('utf-8')
        img = Images.Image(img_id)
        first_seen = img.get_first_seen()
        last_seen = img.get_last_seen()
        file_exists = os.path.exists(img.get_filepath())
        print(f"  {img_id[:16]}... | first_seen: {first_seen or 'None'} | file: {'✓' if file_exists else '✗'}")
    
    if len(all_images) > 10:
        print(f"  ... and {len(all_images) - 10} more")

if __name__ == '__main__':
    import sys
    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    check_image_status(image_path)
