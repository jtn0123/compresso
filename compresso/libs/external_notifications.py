#!/usr/bin/env python3

"""
compresso.external_notifications.py

Dispatches external notifications (Discord, Slack, generic webhook)
when system events occur (task completed, task failed, etc.).
"""

import time
from concurrent.futures import ThreadPoolExecutor

import requests

from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType

logger = CompressoLogging.get_logger(name="ExternalNotifications")

# Color map for Discord embeds (hex integers)
DISCORD_COLOR_MAP = {
    "task_completed": 0x1A6B4A,
    "task_failed": 0xFF4444,
    "queue_empty": 0x3498DB,
    "approval_needed": 0xE8A525,
    "health_check_failed": 0xFF4444,
}

VALID_EVENT_TYPES = {
    "task_completed",
    "task_failed",
    "queue_empty",
    "approval_needed",
    "health_check_failed",
}

EVENT_TITLES = {
    "task_completed": "Task Completed",
    "task_failed": "Task Failed",
    "queue_empty": "Queue Empty",
    "approval_needed": "Approval Needed",
    "health_check_failed": "Health Check Failed",
}


class ExternalNotificationDispatcher(metaclass=SingletonType):
    """
    Singleton that dispatches external notifications to configured channels
    (Discord, Slack, generic webhook) in a background thread pool.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=2)

    def dispatch(self, event_type, context):
        """
        Main entry point. Fans out notifications to all channels
        whose trigger list includes the given event_type.

        :param event_type: One of VALID_EVENT_TYPES
        :param context: dict with event details (file_name, codec, size_saved, quality_scores, etc.)
        """
        if event_type not in VALID_EVENT_TYPES:
            logger.warning("Unknown event type '%s'; skipping dispatch", event_type)
            return

        channels = self._get_channels_for_event(event_type)
        for channel in channels:
            self._executor.submit(self._send_to_channel, channel, event_type, context)

    def _get_channels_for_event(self, event_type):
        """
        Read configured notification channels from Config and return only
        those whose triggers list includes the given event_type.
        """
        from compresso.config import Config

        cfg = Config()
        all_channels = cfg.get_notification_channels()
        matched = []
        for ch in all_channels:
            if not ch.get("enabled", True):
                continue
            triggers = ch.get("triggers", [])
            if event_type in triggers:
                matched.append(ch)
        return matched

    def _send_to_channel(self, channel, event_type, context):
        """Route to the correct sender based on channel type."""
        channel_type = channel.get("type", "").lower()
        try:
            if channel_type == "discord":
                self._send_discord(channel, event_type, context)
            elif channel_type == "slack":
                self._send_slack(channel, event_type, context)
            elif channel_type == "webhook":
                self._send_webhook(channel, event_type, context)
            else:
                logger.warning("Unknown channel type '%s' for channel '%s'", channel_type, channel.get("name", "unnamed"))
        except Exception as e:
            logger.error(
                "Failed to send %s notification to channel '%s': %s", channel_type, channel.get("name", "unnamed"), str(e)
            )

    def _send_discord(self, channel, event_type, context):
        """Send a Discord webhook with a rich embed."""
        url = channel.get("url", "")
        color = DISCORD_COLOR_MAP.get(event_type, 0x808080)
        title = EVENT_TITLES.get(event_type, event_type)

        fields = []
        if context.get("file_name"):
            fields.append({"name": "File", "value": context["file_name"], "inline": True})
        if context.get("codec"):
            fields.append({"name": "Codec", "value": context["codec"], "inline": True})
        if context.get("size_saved"):
            fields.append({"name": "Size Saved", "value": context["size_saved"], "inline": True})
        if context.get("quality_scores"):
            scores = context["quality_scores"]
            score_parts = []
            if scores.get("vmaf") is not None:
                score_parts.append("VMAF: {}".format(scores["vmaf"]))
            if scores.get("ssim") is not None:
                score_parts.append("SSIM: {}".format(scores["ssim"]))
            if score_parts:
                fields.append({"name": "Quality", "value": " | ".join(score_parts), "inline": False})
        if context.get("message"):
            fields.append({"name": "Details", "value": context["message"], "inline": False})

        embed = {
            "title": title,
            "color": color,
            "fields": fields,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        payload = {
            "embeds": [embed],
        }

        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code >= 400:
            logger.warning(
                "Discord webhook returned status %d for channel '%s'", resp.status_code, channel.get("name", "unnamed")
            )

    def _send_slack(self, channel, event_type, context):
        """Send a Slack incoming webhook with Block Kit blocks."""
        url = channel.get("url", "")
        title = EVENT_TITLES.get(event_type, event_type)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                },
            },
        ]

        detail_parts = []
        if context.get("file_name"):
            detail_parts.append("*File:* {}".format(context["file_name"]))
        if context.get("codec"):
            detail_parts.append("*Codec:* {}".format(context["codec"]))
        if context.get("size_saved"):
            detail_parts.append("*Size Saved:* {}".format(context["size_saved"]))
        if context.get("quality_scores"):
            scores = context["quality_scores"]
            score_parts = []
            if scores.get("vmaf") is not None:
                score_parts.append("VMAF: {}".format(scores["vmaf"]))
            if scores.get("ssim") is not None:
                score_parts.append("SSIM: {}".format(scores["ssim"]))
            if score_parts:
                detail_parts.append("*Quality:* {}".format(" | ".join(score_parts)))
        if context.get("message"):
            detail_parts.append("*Details:* {}".format(context["message"]))

        if detail_parts:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(detail_parts),
                    },
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Compresso | {}".format(time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())),
                    },
                ],
            }
        )

        payload = {
            "blocks": blocks,
        }

        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code >= 400:
            logger.warning(
                "Slack webhook returned status %d for channel '%s'", resp.status_code, channel.get("name", "unnamed")
            )

    def _send_webhook(self, channel, event_type, context):
        """Send a generic JSON POST to a custom webhook URL."""
        url = channel.get("url", "")
        custom_headers = channel.get("headers", {})

        headers = {"Content-Type": "application/json"}
        headers.update(custom_headers)

        payload = {
            "event": event_type,
            "title": EVENT_TITLES.get(event_type, event_type),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "context": context,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("Webhook returned status %d for channel '%s'", resp.status_code, channel.get("name", "unnamed"))

    def _get_sender_for_type(self, channel_type):
        """Return the sender method for a given channel type, or None."""
        senders = {
            "discord": self._send_discord,
            "slack": self._send_slack,
            "webhook": self._send_webhook,
        }
        return senders.get(channel_type)

    def test_channel(self, channel_config):
        """
        Send a test notification to a single channel.
        Returns a dict with 'success' and optional 'error' keys.

        Unlike dispatch(), this calls the sender directly so that
        exceptions propagate and can be reported to the caller.
        """
        test_context = {
            "file_name": "test_video.mp4",
            "codec": "hevc",
            "size_saved": "150 MB (42%)",
            "quality_scores": {"vmaf": 95.2, "ssim": 0.98},
            "message": "This is a test notification from Compresso.",
        }
        try:
            channel_type = channel_config.get("type", "").lower()
            sender = self._get_sender_for_type(channel_type)
            if sender is None:
                return {"success": False, "error": f"Unknown channel type '{channel_type}'"}
            sender(channel_config, "task_completed", test_context)
            return {"success": True}
        except Exception as e:
            logger.error("Test notification failed for channel '%s': %s", channel_config.get("name", "unnamed"), str(e))
            return {"success": False, "error": str(e)}
