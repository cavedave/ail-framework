#!/usr/bin/env python3
# -*-coding:UTF-8 -*
"""
CLIP Feature Detection Configuration
Items to detect in images using CLIP text-image similarity.

Each category has multiple prompts - we take the max score across all prompts.
This allows for better detection by covering different ways items can appear.
"""

# Items to detect in images using CLIP text-image similarity
# Each category has multiple prompts - we take the max score across all prompts
CLIP_FEATURE_ITEMS = {
    'gun': [
        'a handgun',
        'a pistol',
        'a firearm',
        'a person holding a gun',
        'a group with weapons',
        'an armed person'
    ],
    'logo': [
        'a logo on a piece of clothing',
        'a logo on an object',
        'a company logo',
        'a school crest',
        'a sport team icon'
    ],
    'electricity plug': [
        'a power outlet',
        'an electrical plug',
        'a power socket'
    ],
    'sports jersey': [
        'a sports jersey',
        'a team jersey',
        'an athletic jersey'
    ],
    'person': [
        'people standing in a group',
        'a person in the image',
        'people in a photo'
    ],
    'street sign': [
        'a street sign',
        'a road sign',
        'a traffic sign'
    ]
}

# Default confidence threshold (0.0-1.0) for feature detection
# CLIP cosine similarity scores are typically lower than classification confidence scores.
# Scores above 0.1 indicate the item "might be in the image" (weak but meaningful match)
# Typical ranges: 0.1-0.2 (might be present), 0.2-0.3 (moderate), 0.3+ (strong)
# Note: Can be made per-item specific (e.g., gun could use different threshold)
CLIP_FEATURE_THRESHOLD = 0.1
