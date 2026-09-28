from app.models import AuditEntry


def export_csv(entries: list[AuditEntry]) -> str:
    output = "timestamp,user,action,target\n"
    for entry in entries:
        output += f"{entry.timestamp.isoformat()},{entry.user},{entry.action},{entry.target}\n"
    return output
