"""Notification service – mock email, SMS, in-app notifications."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NotificationType
from app.core.logging import get_logger
from app.tools.banking import send_customer_notification

logger = get_logger(__name__)

TEMPLATES = {
    "dispute_created": {
        "subject": "Dispute #{dispute_id} Created",
        "body": "Dear {name}, your dispute #{dispute_id} regarding '{category}' has been created. "
                "We will review it and update you shortly. Reference: {dispute_id}",
    },
    "dispute_under_review": {
        "subject": "Dispute #{dispute_id} Under Review",
        "body": "Dear {name}, your dispute #{dispute_id} is now under review by our team.",
    },
    "auto_resolution": {
        "subject": "Dispute #{dispute_id} Resolved",
        "body": "Dear {name}, your dispute #{dispute_id} has been automatically resolved. "
                "{action_taken}. The amount will be credited within 3-5 business days.",
    },
    "refund_initiated": {
        "subject": "Refund Initiated for Dispute #{dispute_id}",
        "body": "Dear {name}, a refund of INR {amount} has been initiated for dispute #{dispute_id}. "
                "Please allow 3-5 business days for the credit.",
    },
    "escalated": {
        "subject": "Dispute #{dispute_id} Escalated",
        "body": "Dear {name}, your dispute #{dispute_id} has been escalated to our specialist team "
                "for further review. We aim to resolve it within {sla} hours.",
    },
    "dispute_resolved": {
        "subject": "Dispute #{dispute_id} Resolved",
        "body": "Dear {name}, your dispute #{dispute_id} has been resolved. {resolution_summary}",
    },
    "info_required": {
        "subject": "Additional Information Required - Dispute #{dispute_id}",
        "body": "Dear {name}, we need additional information to process your dispute #{dispute_id}. "
                "Please provide: {required_info}",
    },
}


async def notify_customer(
    db: AsyncSession,
    *,
    customer_id: uuid.UUID,
    customer_name: str,
    dispute_id: uuid.UUID,
    template_name: str,
    notification_type: str = NotificationType.IN_APP.value,
    extra_vars: dict | None = None,
) -> None:
    template = TEMPLATES.get(template_name)
    if not template:
        logger.warning("unknown_notification_template", template=template_name)
        return

    fmt_vars = {
        "name": customer_name,
        "dispute_id": str(dispute_id)[:8],
        **(extra_vars or {}),
    }

    subject = template["subject"].format(**{k: fmt_vars.get(k, "") for k in _extract_keys(template["subject"])})
    body = template["body"].format(**{k: fmt_vars.get(k, "") for k in _extract_keys(template["body"])})

    await send_customer_notification(
        db,
        customer_id=customer_id,
        dispute_id=dispute_id,
        notification_type=notification_type,
        template_name=template_name,
        subject=subject,
        body=body,
    )


def _extract_keys(template: str) -> list[str]:
    import re
    return re.findall(r"\{(\w+)\}", template)
