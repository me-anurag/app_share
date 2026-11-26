"""Docs-style access control. Roles are ranked; a user's effective role is the
highest one they get from ownership, a direct share, a group share, or org-wide link access."""
import re

RANK = {None: 0, "submitter": 1, "viewer": 2, "editor": 3, "owner": 4}
ROLES = ("editor", "viewer", "submitter")


def effective_role(conn, app, user_id):
    if app["owner_id"] == user_id:
        return "owner"
    best = None
    rows = conn.execute(
        """
        SELECT role FROM permissions WHERE app_id = ? AND principal_type = 'user' AND principal_id = ?
        UNION ALL
        SELECT p.role FROM permissions p
          JOIN group_members gm ON gm.group_id = p.principal_id
         WHERE p.app_id = ? AND p.principal_type = 'group' AND gm.user_id = ?
        """,
        (app["id"], user_id, app["id"], user_id),
    ).fetchall()
    for r in rows:
        if RANK[r["role"]] > RANK[best]:
            best = r["role"]
    if app["link_access"] in ("org", "public") and RANK[best] < RANK["submitter"]:
        best = "submitter"
    # Drafts are private to people who can edit them.
    if app["status"] == "draft" and RANK[best] < RANK["editor"]:
        return None
    return best


def at_least(role, needed):
    return RANK[role] >= RANK[needed]


def audience(conn, app_id):
    """Users expected to submit: direct submitters + members of submitter groups."""
    rows = conn.execute(
        """
        SELECT u.id, u.name, u.email FROM permissions p JOIN users u ON u.id = p.principal_id
         WHERE p.app_id = ? AND p.principal_type = 'user' AND p.role = 'submitter'
        UNION
        SELECT u.id, u.name, u.email FROM permissions p
          JOIN group_members gm ON gm.group_id = p.principal_id
          JOIN users u ON u.id = gm.user_id
         WHERE p.app_id = ? AND p.principal_type = 'group' AND p.role = 'submitter'
        ORDER BY 2
        """,
        (app_id, app_id),
    ).fetchall()
    return [dict(r) for r in rows]


def list_shares(conn, app_id):
    rows = conn.execute(
        """
        SELECT p.principal_type AS type, p.principal_id AS id, p.role,
               CASE WHEN p.principal_type = 'user' THEN u.name ELSE g.name END AS name,
               CASE WHEN p.principal_type = 'user' THEN u.title ELSE g.kind END AS kind,
               CASE WHEN p.principal_type = 'user' THEN u.email ELSE
                    (SELECT COUNT(*) || ' members' FROM group_members WHERE group_id = g.id) END AS detail
          FROM permissions p
          LEFT JOIN users u ON p.principal_type = 'user' AND u.id = p.principal_id
          LEFT JOIN groups g ON p.principal_type = 'group' AND g.id = p.principal_id
         WHERE p.app_id = ?
         ORDER BY p.principal_type, name
        """,
        (app_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_principal(conn, kind, name):
    """Map a name/email the agent proposed to a real principal, or None."""
    name = (name or "").strip()
    if kind == "group":
        r = conn.execute("SELECT id, name FROM groups WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    elif kind == "user":
        if re.fullmatch(r"u\d+", name):        # the internal ref the agents use instead of an email address
            r = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (int(name[1:]),)).fetchone()
        else:
            r = conn.execute("SELECT id, name, email FROM users WHERE email = ? OR name = ? COLLATE NOCASE",
                             (name.lower(), name)).fetchone()
    else:
        return None
    return dict(r) if r else None
