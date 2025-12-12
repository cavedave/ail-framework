#!/usr/bin/env python3
# -*-coding:UTF-8 -*
"""
Script to fix images that don't have dates set
This will make them appear in date range views
"""

import os
import sys

# Set AIL environment variables
if 'AIL_BIN' not in os.environ:
    os.environ['AIL_BIN'] = '/opt/ail-framework/bin'
if 'AIL_HOME' not in os.environ:
    os.environ['AIL_HOME'] = '/opt/ail-framework'

sys.path.append(os.environ['AIL_BIN'])

from lib.objects import Images
from lib.ConfigLoader import ConfigLoader
from packages import Date

def fix_images_without_dates():
    """Find and fix all images that don't have a date set"""
    config = ConfigLoader()
    r_object = config.get_db_conn("Kvrocks_Objects")
    
    current_date = Date.get_today_date_str()
    print(f"Setting date to: {current_date}")
    print("="*60)
    
    # Find images without first_seen
    all_images = r_object.smembers('image:all')
    fixed_count = 0
    
    for img_id in all_images:
        if isinstance(img_id, bytes):
            img_id = img_id.decode('utf-8')
        
        img = Images.Image(img_id)
        first_seen = img.get_first_seen()
        
        if not first_seen:
            img.add(current_date, None)
            print(f"✓ Set date for image: {img_id[:16]}...")
            fixed_count += 1
        else:
            print(f"  Image {img_id[:16]}... already has date: {first_seen}")
    
    print("="*60)
    print(f"Fixed {fixed_count} image(s) without dates")
    return fixed_count

if __name__ == '__main__':
    fix_images_without_dates()
