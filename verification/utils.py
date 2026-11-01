from django.contrib.auth.hashers import check_password, make_password


def normalize_answer(text):
    """'  Blue   Lining ' and 'blue lining' count as the same answer."""
    return " ".join((text or "").lower().split())


def hash_answer(text):
    """Return a salted hash (same technique as passwords), or '' when no answer is given."""
    normalized = normalize_answer(text)
    return make_password(normalized) if normalized else ""


def answer_matches(text, answer_hash):
    """True/False when an expected answer exists, None when the owner did not set one."""
    if not answer_hash:
        return None
    return check_password(normalize_answer(text), answer_hash)
