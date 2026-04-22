from fastapi import Header, HTTPException, status


def require_role(required_role: str):
    def _validator(x_role: str = Header(default="viewer"), x_tenant_id: str = Header(default="demo-tenant")) -> tuple[str, str]:
        allowed = {
            "viewer": {"viewer"},
            "editor": {"viewer", "editor"},
            "admin": {"viewer", "editor", "admin"},
        }
        if required_role not in allowed.get(x_role, set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {x_role} cannot access {required_role} endpoint",
            )
        return x_tenant_id, x_role

    return _validator
