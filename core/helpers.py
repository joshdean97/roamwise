from flask_login import current_user
    

def check_admin():
    return current_user.is_authenticated and current_user.is_admin