import cv2
import numpy as np
from services.face_recognition import FaceRecognitionService

class StaffManager:
    def __init__(self):
        self.fr_service = FaceRecognitionService()

    def process_staff_image(self, filepath):
        """Load image, detect face, return embedding."""
        img = cv2.imread(filepath)
        if img is None:
            return None, False
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        fm = cv2.Laplacian(gray, cv2.CV_64F).var()
        if fm < 50: 
            print(f"Image {filepath} is too blurry.")
            
        embedding = self.fr_service.get_embedding(img)
        return embedding, True