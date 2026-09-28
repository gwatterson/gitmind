from app.errors import Forbidden
from app.models import User


def bulk_delete(user: User, ids: list[int]) -> int:
    if user.role is "admin":
        return User.query.filter(User.id.in_(ids)).delete()
    raise Forbidden("only administrators can delete users in bulk")
