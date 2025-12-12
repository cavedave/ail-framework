#!/usr/bin/env python3
# -*-coding:UTF-8 -*
"""
Script to register an existing image file in the AIL database
"""

import os
import sys
import os
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

def register_image(image_path):
    """Register an existing image file in AIL database"""
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        return None
    
    print(f"Reading image: {image_path}")
    with open(image_path, 'rb') as f:
        content = f.read()
    
    # Calculate SHA256 (this is the image ID)
    image_id = sha256(content).hexdigest()
    print(f"Image SHA256: {image_id}")
    
    # Create image object
    image = Images.Image(image_id)
    
    # Check if file exists on disk
    filepath = image.get_filepath()
    if not os.path.exists(filepath):
        print(f"Creating image file at: {filepath}")
        image.create(content)
    else:
        print(f"Image file exists at: {filepath}")
    
    # Check current status
    config = ConfigLoader()
    r_object = config.get_db_conn("Kvrocks_Objects")
    
    # Check if in database
    in_meta = r_object.exists(f'meta:image:{image_id}')
    in_all_set = image_id in r_object.smembers('image:all') or image_id.encode() in r_object.smembers('image:all')
    
    print(f"\nCurrent status:")
    print(f"  In meta: {in_meta}")
    print(f"  In 'image:all' set: {in_all_set}")
    print(f"  First seen: {image.get_first_seen()}")
    
    # Register it
    current_date = Date.get_today_date_str()
    print(f"\nRegistering with date: {current_date}")
    
    # Call add() which will:
    # 1. Add to image:all set
    # 2. Set first_seen/last_seen
    # 3. Add to date range
    image.add(current_date, None)
    
    # Verify
    print(f"\nAfter registration:")
    in_meta_after = r_object.exists(f'meta:image:{image_id}')
    all_images = r_object.smembers('image:all')
    in_all_after = image_id in all_images or image_id.encode() in all_images
    first_seen = image.get_first_seen()
    
    print(f"  In meta: {in_meta_after}")
    print(f"  In 'image:all' set: {in_all_after}")
    print(f"  First seen: {first_seen}")
    
    # Check date range
    date_key = f'image:date:{current_date}'
    in_date_range = r_object.zscore(date_key, image_id)
    print(f"  In date range ({current_date}): {in_date_range is not None}")
    
    if in_all_after and first_seen:
        print(f"\n✓ SUCCESS! Image is now registered")
        print(f"  Image ID: {image_id}")
        print(f"  Global ID: {image.get_global_id()}")
        return image
    else:
        print(f"\n⚠️  Warning: Registration may have failed")
        print(f"  Try checking the logs or reloading the image")
        return None

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 register_existing_image.py <path_to_image>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    image = register_image(image_path)
    
    if image:
        current_date = Date.get_today_date_str()
        date_str = f"{current_date[:4]}-{current_date[4:6]}-{current_date[6:8]}"
        print(f"\n" + "="*60)
        print("Image should now appear at:")
        print(f"  /objects/images?date_from={date_str}&date_to={date_str}&show_objects=True")
        print("="*60)
