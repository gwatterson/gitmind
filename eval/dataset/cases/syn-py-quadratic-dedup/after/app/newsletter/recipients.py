from app.models import Contact


def unique_recipients(contacts: list[Contact]) -> list[Contact]:
    seen_emails: list[str] = []
    unique = []
    for contact in contacts:
        email = contact.email.strip().lower()
        if email in seen_emails:
            continue
        seen_emails.append(email)
        unique.append(contact)
    return unique
