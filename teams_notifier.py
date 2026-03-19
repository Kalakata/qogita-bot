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


def send_summary(webhook_url: str, allocations: list[dict], reached_count: int) -> None:
    """Send a summary of all allocations to Teams."""
    total = len(allocations)

    # Sort by movProgress descending, get top 5
    valid = []
    for a in allocations:
        try:
            valid.append((float(a.get("movProgress", "0")), a))
        except (ValueError, TypeError):
            continue
    valid.sort(key=lambda x: x[0], reverse=True)
    top5 = valid[:5]

    top_lines = [
        f"- **{a['fid']}** — {prog:.1%} ({a['movCurrency']} {a['subtotal']} / {a['mov']})"
        for prog, a in top5
    ]

    text = f"**Cart Summary:** {total} allocations, {reached_count} reached MOV\n\n"
    text += "**Top 5 closest:**\n" + "\n".join(top_lines)

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
                            "text": text,
                            "wrap": True,
                        }
                    ],
                },
            }
        ],
    }

    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()
