import requests


def send_notification(webhook_url: str, allocation: dict) -> None:
    """Send a Teams notification for an allocation that reached MOV."""
    fid = allocation["fid"]
    mov = allocation["mov"]
    currency = allocation["movCurrency"]

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"Cart allocation **{fid}** has reached its MOV! ({currency} {mov})",
                            "wrap": True,
                        }
                    ],
                },
            }
        ],
    }

    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()
