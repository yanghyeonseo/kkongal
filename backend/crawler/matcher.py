from __future__ import annotations

from account.models import Interest
from notices.models import InboxNotice, Notice
from sources.models import SourceSubscription


def match_notice_to_subscribers(notice: Notice) -> int:
    """Create InboxNotice rows for subscribed users whose interests match a notice."""

    created_count = 0
    subscriptions = SourceSubscription.objects.filter(source_id=notice.source_id).select_related("user_id")
    haystack = f"{notice.title} {notice.content}".lower()

    for subscription in subscriptions:
        interests = Interest.objects.filter(user_id=subscription.user_id).order_by("-priority", "-created_at")
        matched_keywords = [
            interest.keyword
            for interest in interests
            if interest.keyword and interest.keyword.lower() in haystack
        ]
        if not matched_keywords:
            continue

        _, created = InboxNotice.objects.get_or_create(
            user_id=subscription.user_id,
            notice_id=notice,
            defaults={
                "relevance_score": 1.0,
                "matched_keywords": ", ".join(matched_keywords),
                "reason": "Keyword match",
            },
        )
        if created:
            created_count += 1

    return created_count
