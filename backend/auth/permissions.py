"""Role-based access control dependencies."""

from fastapi import Depends, HTTPException, status

from auth.dependencies import get_current_user
from models.user import User, UserRole


def require_roles(*roles: UserRole):
    """Dependency factory: allow only users whose role is in `roles`."""

    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return checker


require_admin = require_roles(UserRole.ADMIN)
