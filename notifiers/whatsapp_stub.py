"""WhatsApp notification stub with documentation for future Cloud API / Twilio integration."""

from __future__ import annotations
import logging
from typing import Union, List
from notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class WhatsAppNotifier(BaseNotifier):
    """Documented stub for WhatsApp notifications.

    How to integrate in the future:
    -------------------------------
    Option A: WhatsApp Cloud API (Official Meta Graph API)
      1. Register a Meta Developer App and configure WhatsApp Business API.
      2. Set WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, and RECIPIENT_PHONE in .env / GitHub Secrets.
      3. Use POST https://graph.facebook.com/v19.0/{phone_number_id}/messages
         with header "Authorization: Bearer {token}"
         and payload template or interactive message.

    Option B: Twilio WhatsApp Messaging API
      1. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_NUMBER.
      2. Post via `twilio.rest.Client` or direct REST endpoint to send formatted text digests.
    """

    def __init__(self, enabled: bool = False):
        super().__init__(name="whatsapp", enabled=enabled)

    def send(self, content: Union[str, List[str]]) -> bool:
        if not self.enabled:
            logger.debug("WhatsApp notifier is disabled (stub). Skipping.")
            return True

        logger.info(
            "WhatsApp notifier is currently a documented stub. "
            "To activate, configure Meta Cloud API or Twilio credentials as documented."
        )
        return True
