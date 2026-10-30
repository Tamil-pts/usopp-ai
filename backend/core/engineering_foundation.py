"""Account-bound access to the independent engineering graph foundation."""
from backend.core.project_intelligence import opened
from backend.core.run_history import current_user
from python_engine.engineering_model import EngineeringModel, build


def model(key, user=None):
    user = current_user.get() if user is None else user
    if not user or not user.get('id'):raise PermissionError('Sign in before accessing engineering blocks.')
    return EngineeringModel(opened(key,user['id']))


def build_model(key,user=None):return build(model(key,user).index)
