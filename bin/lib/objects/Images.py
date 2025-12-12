#!/usr/bin/env python3
# -*-coding:UTF-8 -*

import base64
import magic
import os
import sys

from hashlib import sha256
from io import BytesIO

from flask import url_for
from pymisp import MISPObject

try:
    from PIL import Image as PILImage
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

try:
    import open_clip
    import torch
    import json
    import numpy as np
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False

sys.path.append(os.environ['AIL_BIN'])
##################################
# Import Project packages
##################################
from lib.ConfigLoader import ConfigLoader
from lib.objects.abstract_daterange_object import AbstractDaterangeObject, AbstractDaterangeObjects
from lib.ail_core import get_default_image_description_model
from lib.clip_items_to_find import CLIP_FEATURE_ITEMS, CLIP_FEATURE_THRESHOLD

config_loader = ConfigLoader()
# r_cache = config_loader.get_redis_conn("Redis_Cache")
r_serv_metadata = config_loader.get_db_conn("Kvrocks_Objects")
IMAGE_FOLDER = config_loader.get_files_directory('images')
baseurl = config_loader.get_config_str("Notifications", "ail_domain")
config_loader = None

# CLIP model cache (singleton pattern)
_CLIP_MODEL = None
_CLIP_PREPROCESS = None
_CLIP_DEVICE = None

# CLIP text embeddings cache (singleton pattern)
# Stores pre-computed text embeddings for feature items to avoid recomputation
_CLIP_TEXT_EMBEDDINGS = None

def _load_clip_model():
    """
    Load and cache the CLIP model for image embeddings.
    Uses singleton pattern to avoid reloading the model.
    
    Returns:
        tuple: (model, preprocess, device) or (None, None, None) if unavailable
    """
    global _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE
    
    if not CLIP_AVAILABLE:
        return None, None, None
    
    # Return cached model if already loaded
    if _CLIP_MODEL is not None:
        return _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE
    
    try:
        # Detect available device (GPU if available, else CPU)
        _CLIP_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load CLIP model
        # ViT-H-14: Vision Transformer Huge with 14x14 patches (1024-dim embeddings)
        # Note: Can be changed to smaller models for speed (e.g., 'ViT-B-32' for 512-dim, 'ViT-L-14' for 768-dim)
        # laion2b_s32b_b79k: Pre-trained on LAION-2B dataset
        _CLIP_MODEL, _, _CLIP_PREPROCESS = open_clip.create_model_and_transforms(
            'ViT-H-14', 
            pretrained='laion2b_s32b_b79k'
        )
        
        # Move model to appropriate device
        _CLIP_MODEL = _CLIP_MODEL.to(_CLIP_DEVICE)
        
        # Set model to evaluation mode (no training)
        _CLIP_MODEL.eval()
        
        return _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_DEVICE
        
    except Exception as e:
        # Log error but don't crash - CLIP is optional
        print(f"Error loading CLIP model: {str(e)}")
        return None, None, None


def _load_clip_text_embeddings():
    """
    Load and cache text embeddings for CLIP feature detection items.
    Uses singleton pattern to avoid recomputing text embeddings.
    
    Returns:
        dict: Dictionary mapping item names to normalized text embeddings (tensors),
              or None if CLIP is unavailable
    """
    global _CLIP_TEXT_EMBEDDINGS
    
    if not CLIP_AVAILABLE:
        return None
    
    # Return cached embeddings if already loaded
    if _CLIP_TEXT_EMBEDDINGS is not None:
        return _CLIP_TEXT_EMBEDDINGS
    
    try:
        # Load CLIP model (required for text encoding)
        model, _, device = _load_clip_model()
        if model is None:
            return None
        
        # Generate text prompts for all categories
        # Each category has multiple prompts - we'll encode all of them
        all_prompts = []
        prompt_to_category = []  # Track which category each prompt belongs to
        
        for category, prompts in CLIP_FEATURE_ITEMS.items():
            for prompt in prompts:
                all_prompts.append(prompt)
                prompt_to_category.append(category)
        
        # Tokenize and encode text prompts
        with torch.no_grad():
            # Tokenize text
            text_tokens = open_clip.tokenize(all_prompts).to(device)
            
            # Encode text to get embeddings
            text_features = model.encode_text(text_tokens)
            
            # Normalize text features (L2 normalization for cosine similarity)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        
        # Group embeddings by category
        # We'll store all embeddings for each category, then take max during similarity calculation
        _CLIP_TEXT_EMBEDDINGS = {}
        for category in CLIP_FEATURE_ITEMS.keys():
            _CLIP_TEXT_EMBEDDINGS[category] = []
        
        for i, category in enumerate(prompt_to_category):
            _CLIP_TEXT_EMBEDDINGS[category].append(text_features[i])
        
        return _CLIP_TEXT_EMBEDDINGS
        
    except Exception as e:
        # Log error but don't crash - CLIP features are optional
        print(f"Error loading CLIP text embeddings: {str(e)}")
        return None


class Image(AbstractDaterangeObject):
    """
    AIL Screenshot Object. (strings)
    """

    # ID = SHA256
    def __init__(self, image_id):
        super(Image, self).__init__('image', image_id)

    # def get_ail_2_ail_payload(self):
    #     payload = {'raw': self.get_gzip_content(b64=True),
    #                 'compress': 'gzip'}
    #     return payload

    # # WARNING: UNCLEAN DELETE /!\ TEST ONLY /!\
    def delete(self):
        # # TODO:
        pass

    def exists(self):
        return os.path.isfile(self.get_filepath())

    def get_link(self, flask_context=False):
        if flask_context:
            url = url_for('correlation.show_correlation', type=self.type, id=self.id)
        else:
            url = f'/correlation/show?type={self.type}&id={self.id}'
        return url

    def get_svg_icon(self):
        return {'style': 'far', 'icon': '\uf03e', 'color': '#E1F5DF', 'radius': 5}

    def get_rel_path(self):
        rel_path = os.path.join(self.id[0:2], self.id[2:4], self.id[4:6], self.id[6:8], self.id[8:10], self.id[10:12], self.id[12:])
        return rel_path

    def get_filepath(self):
        filename = os.path.join(IMAGE_FOLDER, self.get_rel_path())
        return os.path.realpath(filename)

    def is_gif(self, filepath=None):
        if not filepath:
            filepath = self.get_filepath()
        mime = magic.from_file(filepath, mime=True)
        if mime == 'image/gif':
            return True
        return False

    def get_file_content(self):
        filepath = self.get_filepath()
        with open(filepath, 'rb') as f:
            file_content = BytesIO(f.read())
        return file_content

    def get_base64(self):
        return base64.b64encode(self.get_file_content().read()).decode()

    def get_content(self, r_type='str'):
        if r_type == 'str':
            return None
        else:
            return self.get_file_content()

    def get_description_models(self):
        models = []
        for key in self._get_fields_keys():
            # Handle both bytes and string keys from database
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            if key.startswith('desc:'):
                model = key[5:]
                models.append(model)
        return models

    def add_description_model(self, model, description):
        self._set_field(f'desc:{model}', description)

    def get_description(self, model=None):
        if model is None:
            model = get_default_image_description_model()
        description = self._get_field(f'desc:{model}')
        if description:
            description = description.replace("`", ' ')
        return description

    def calculate_phash(self):
        """Calculate perceptual hash (pHash) for the image."""
        if not IMAGEHASH_AVAILABLE:
            return None
        
        if not self.exists():
            return None
        
        try:
            filepath = self.get_filepath()
            with PILImage.open(filepath) as img:
                phash = imagehash.phash(img)
                return str(phash)
        except Exception as e:
            self.logger.warning(f"Failed to calculate phash for image {self.id}: {e}")
            return None

    def get_phash(self):
        """Get perceptual hash, calculating it if not stored."""
        phash = self._get_field('phash')
        if phash:
            return phash
        
        # Calculate and store if not exists
        phash = self.calculate_phash()
        if phash:
            self._set_field('phash', phash)
        return phash

    def calculate_clip_embedding(self):
        """Calculate CLIP embedding for the image."""
        if not CLIP_AVAILABLE:
            return None
        
        if not self.exists():
            return None
        
        try:
            # Load CLIP model (cached)
            model, preprocess, device = _load_clip_model()
            if model is None:
                return None
            
            # Load and preprocess image
            filepath = self.get_filepath()
            # Use context manager to ensure file is properly closed (like calculate_phash does)
            with PILImage.open(filepath) as pil_image:
                image = pil_image.convert('RGB')
                image_tensor = preprocess(image).unsqueeze(0).to(device)
                
                # Get image features (embedding)
                with torch.no_grad():  # No gradient computation needed
                    image_features = model.encode_image(image_tensor)
                    
                    # Normalize the features (L2 normalization)
                    # This makes cosine similarity work correctly
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                
                # Convert to numpy array and flatten
                embedding = image_features.cpu().numpy().flatten()
                
                # Convert to list for JSON serialization
                embedding_list = embedding.tolist()
                
                return embedding_list
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate CLIP embedding for image {self.id}: {e}")
            return None

    def get_clip_embedding(self):
        """Get CLIP embedding, calculating it if not stored."""
        # Try to get from cache
        clip_json = self._get_field('clip_embedding')
        if clip_json:
            try:
                return json.loads(clip_json)
            except (json.JSONDecodeError, TypeError):
                # If stored value is invalid, recalculate
                pass
        
        # Calculate and store if not exists
        embedding = self.calculate_clip_embedding()
        if embedding:
            # Store as JSON string
            self._set_field('clip_embedding', json.dumps(embedding))
        return embedding

    def calculate_clip_features(self):
        """
        Calculate CLIP feature detection scores for predefined items.
        Compares image embedding with text embeddings to determine if items are present.
        
        Returns:
            dict: Dictionary mapping item names to confidence scores (0.0-1.0),
                  or None if CLIP is unavailable or calculation fails
        """
        if not CLIP_AVAILABLE:
            return None
        
        if not self.exists():
            return None
        
        try:
            # Get image embedding (normalized)
            image_embedding = self.get_clip_embedding()
            if not image_embedding:
                return None
            
            # Get text embeddings for feature items
            text_embeddings = _load_clip_text_embeddings()
            if not text_embeddings:
                return None
            
            # Get device from model
            model, _, device = _load_clip_model()
            if model is None:
                return None
            
            # Convert image embedding to tensor on correct device
            image_tensor = torch.tensor(image_embedding, dtype=torch.float32).to(device)
            # Ensure it's normalized (should already be from calculate_clip_embedding)
            image_tensor = image_tensor / image_tensor.norm()
            
            # Calculate cosine similarity between image and each text embedding
            # For each category, we have multiple prompts - take the max score
            features = {}
            with torch.no_grad():
                for category, category_embeddings in text_embeddings.items():
                    # Calculate similarity with all prompts for this category
                    similarities = []
                    for text_embedding in category_embeddings:
                        # Cosine similarity: dot product of normalized vectors
                        # Both are already normalized, so dot product gives cosine similarity
                        similarity = (image_tensor * text_embedding).sum().item()
                        similarities.append(similarity)
                    
                    # Take the maximum score across all prompts for this category
                    # This gives us the best match for any of the prompts
                    max_similarity = max(similarities)
                    # CLIP similarity is in range [-1, 1], but typically [0.1, 0.3] for matches
                    # Higher values = more similar = item more likely present
                    features[category] = float(max_similarity)
            
            return features
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate CLIP features for image {self.id}: {e}")
            return None

    def get_clip_features(self):
        """
        Get CLIP feature detection results, calculating if not stored.
        Returns items with confidence scores above threshold.
        
        Note: This method uses lazy loading - features are calculated on first access
        and then cached in the database. To ensure features are calculated during
        image processing, call this method in your image processing module.
        
        Returns:
            dict: Dictionary mapping item names to confidence scores (0.0-1.0)
                  for items above threshold, or None if unavailable
        """
        # Try to get from cache
        features_json = self._get_field('clip_features')
        if features_json:
            try:
                all_features = json.loads(features_json)
                # Filter to only items above threshold
                return {item: score for item, score in all_features.items() 
                       if score >= CLIP_FEATURE_THRESHOLD}
            except (json.JSONDecodeError, TypeError):
                # If stored value is invalid, recalculate
                pass
        
        # Calculate and store if not exists
        all_features = self.calculate_clip_features()
        if all_features:
            # Store all features as JSON string (including below-threshold)
            self._set_field('clip_features', json.dumps(all_features))
            # Return only items above threshold
            return {item: score for item, score in all_features.items() 
                   if score >= CLIP_FEATURE_THRESHOLD}
        return None

    def get_search_document(self):
        global_id = self.get_global_id()
        content = self.get_description()
        if content:
            return {'uuid': self.get_uuid5(global_id), 'id': global_id, 'content': content}
        else:
            return None

    def get_misp_object(self):
        obj_attrs = []
        obj = MISPObject('file')

        obj_attrs.append(obj.add_attribute('sha256', value=self.id))
        obj_attrs.append(obj.add_attribute('attachment', value=self.id, data=self.get_file_content()))
        for obj_attr in obj_attrs:
            for tag in self.get_tags():
                obj_attr.add_tag(tag)
        return obj

    def get_meta(self, options=set(), flask_context=False):
        meta = self._get_meta(options=options, flask_context=flask_context)
        meta['id'] = self.id
        meta['img'] = self.id
        meta['tags'] = self.get_tags(r_list=True)
        if 'content' in options:
            meta['content'] = self.get_content()
        if 'description' in options:
            meta['description'] = self.get_description()
        if 'phash' in options or 'all' in options:
            meta['phash'] = self.get_phash()
        if 'clip_embedding' in options or 'all' in options:
            meta['clip_embedding'] = self.get_clip_embedding()
        if 'clip_features' in options or 'all' in options:
            meta['clip_features'] = self.get_clip_features()
        if 'ai_detector' in options or 'all' in options:
            # TODO: AI Detector - not implemented yet
            meta['ai_detector'] = None
        if 'meta_data' in options or 'all' in options:
            # TODO: Meta data - not implemented yet
            meta['meta_data'] = None
        if 'tags_safe' in options:
            meta['tags_safe'] = self.is_tags_safe(meta['tags'])
        return meta

    def create(self, content):
        filepath = self.get_filepath()
        dirname = os.path.dirname(filepath)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(filepath, 'wb') as f:
            f.write(content)

def get_screenshot_dir():
    return IMAGE_FOLDER

def get_all_images():
    images = []
    for root, dirs, files in os.walk(get_screenshot_dir()):
        for file in files:
            path = f'{root}{file}'
            image_id = path.replace(IMAGE_FOLDER, '').replace('/', '')
            images.append(image_id)
    return images


def get_all_images_objects(filters={}):
    for image_id in get_all_images():
        yield Image(image_id)


def create(content, size_limit=5000000, b64=False, force=False):
    size = (len(content)*3) / 4
    if size <= size_limit or size_limit < 0 or force:
        if b64:
            content = base64.standard_b64decode(content.encode())
        image_id = sha256(content).hexdigest()
        image = Image(image_id)
        if not image.exists():
            image.create(content)
        return image


class Images(AbstractDaterangeObjects):
    """
        CookieName Objects
    """
    def __init__(self):
        super().__init__('image', Image)

    def get_name(self):
        return 'Images'

    def get_icon(self):
        return {'fas': 'fas', 'icon': 'image'}

    def get_link(self, flask_context=False):
        if flask_context:
            url = url_for('objects_image.objects_images')
        else:
            url = f'{baseurl}/objects/images'
        return url

    def sanitize_id_to_search(self, name_to_search):
        return name_to_search  # TODO


# if __name__ == '__main__':
#     print(json.dumps(get_all_images()))
#     name_to_search = '29ba'
#     print(search_screenshots_by_name(name_to_search))
