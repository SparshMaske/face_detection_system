import re

def validate_email(email):
    if not email:
        return True
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

def validate_phone(phone):
    if not phone:
        return True
    return re.match(r"^[+]?[0-9\s\-]{9,15}$", phone) is not None