import cv2
import numpy as np
import os

def is_image_blurry(image_path, threshold=50.0):
    """Detects if an image is blurry using variance of Laplacian."""
    image = cv2.imread(image_path)
    if image is None:
        return True 
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    fm = cv2.Laplacian(gray, cv2.CV_64F).var()
    return fm < threshold

def resize_image(image_path, max_width=800):
    """Resizes image to save space."""
    image = cv2.imread(image_path)
    if image is None:
        return False
    
    h, w = image.shape[:2]
    if w > max_width:
        ratio = max_width / float(w)
        dim = (max_width, int(h * ratio))
        resized = cv2.resize(image, dim, interpolation=cv2.INTER_AREA)
        cv2.imwrite(image_path, resized)
        
    return True