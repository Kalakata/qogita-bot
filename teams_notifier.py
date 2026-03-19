import requests


def _post_card(webhook_url: str, card_body: list, version: str = "1.4") -> None:
    """Post an Adaptive Card to a Teams webhook."""
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": version,
                    "body": card_body,
                },
            }
        ],
    }
    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()


def _progress_bar(progress: float) -> str:
    """Create a text-based progress bar."""
    filled = round(progress * 10)
    filled = min(filled, 10)
    return "\u2588" * filled + "\u2591" * (10 - filled)


def send_notification(webhook_url: str, allocation: dict) -> None:
    """Send a Teams notification for an allocation that reached MOV."""
    fid = allocation["fid"]
    mov = allocation["mov"]
    currency = allocation["movCurrency"]
    subtotal = allocation["subtotal"]

    card_body = [
        {
            "type": "TextBlock",
            "text": "\U0001F389 MOV REACHED!",
            "weight": "Bolder",
            "size": "Large",
            "color": "Good",
        },
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "Cart",
                            "weight": "Bolder",
                            "isSubtle": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": fid,
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "spacing": "None",
                        },
                    ],
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "MOV Target",
                            "weight": "Bolder",
                            "isSubtle": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": f"{currency} {mov}",
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "spacing": "None",
                        },
                    ],
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "Cart Value",
                            "weight": "Bolder",
                            "isSubtle": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": f"{currency} {subtotal}",
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "color": "Good",
                            "spacing": "None",
                        },
                    ],
                },
            ],
        },
        {
            "type": "TextBlock",
            "text": f"{_progress_bar(1.0)} **100%**",
            "fontType": "Monospace",
            "spacing": "Medium",
        },
    ]

    _post_card(webhook_url, card_body)


def send_summary(webhook_url: str, allocations: list[dict], reached_count: int) -> None:
    """Send a summary of all allocations to Teams."""
    total = len(allocations)

    valid = []
    for a in allocations:
        try:
            valid.append((float(a.get("movProgress", "0")), a))
        except (ValueError, TypeError):
            continue
    valid.sort(key=lambda x: x[0], reverse=True)
    top5 = valid[:5]

    card_body = [
        {
            "type": "TextBlock",
            "text": "\U0001F4CA Cart Summary",
            "weight": "Bolder",
            "size": "Large",
        },
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {"type": "TextBlock", "text": "Total Carts", "isSubtle": True},
                        {
                            "type": "TextBlock",
                            "text": str(total),
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "spacing": "None",
                        },
                    ],
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {"type": "TextBlock", "text": "Reached MOV", "isSubtle": True},
                        {
                            "type": "TextBlock",
                            "text": str(reached_count),
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "color": "Good",
                            "spacing": "None",
                        },
                    ],
                },
            ],
        },
        {
            "type": "TextBlock",
            "text": "**Top 5 Closest to MOV:**",
            "weight": "Bolder",
            "spacing": "Medium",
        },
    ]

    for prog, a in top5:
        color = "Good" if prog >= 1.0 else "Warning" if prog >= 0.75 else "Default"
        card_body.append(
            {
                "type": "ColumnSet",
                "spacing": "Small",
                "columns": [
                    {
                        "type": "Column",
                        "width": "80px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**{a['fid']}**",
                                "spacing": "None",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"`{_progress_bar(prog)}` {prog:.0%}",
                                "fontType": "Monospace",
                                "spacing": "None",
                                "color": color,
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{a['movCurrency']} {a['subtotal']} / {a['mov']}",
                                "isSubtle": True,
                                "spacing": "None",
                            }
                        ],
                    },
                ],
            }
        )

    _post_card(webhook_url, card_body)
