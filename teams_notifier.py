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


def _progress_color(prog: float) -> str:
    """Color based on progress: green 100%+, warning 75%+, accent 50%+, default below."""
    if prog >= 1.0:
        return "Good"
    if prog >= 0.75:
        return "Warning"
    if prog >= 0.50:
        return "Accent"
    return "Default"


def send_notification(webhook_url: str, allocation: dict) -> None:
    """Send a Teams notification for an allocation that reached MOV."""
    fid = allocation["fid"]
    mov = allocation["mov"]
    currency = allocation["movCurrency"]
    subtotal = allocation["subtotal"]

    card_body = [
        {
            "type": "TextBlock",
            "text": "MOV REACHED!",
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
    ]

    _post_card(webhook_url, card_body)


def send_summary(webhook_url: str, allocations: list[dict], reached_count: int) -> None:
    """Send a summary of all allocations to Teams."""
    total = len(allocations)

    # Parse all allocations with valid progress
    valid = []
    for a in allocations:
        try:
            prog = float(a.get("movProgress", "0"))
            valid.append((prog, a))
        except (ValueError, TypeError):
            continue

    # Compute stats
    total_value = sum(float(a.get("subtotal", "0")) for _, a in valid)
    avg_progress = sum(p for p, _ in valid) / len(valid) if valid else 0
    currency = valid[0][1]["movCurrency"] if valid else "EUR"

    # Split into reached and not-reached
    not_reached = [(p, a) for p, a in valid if p < 1.0]
    not_reached.sort(key=lambda x: x[0], reverse=True)
    top5 = not_reached[:5]

    # Cheapest to complete: smallest gap to MOV (excluding reached)
    with_gap = []
    for p, a in not_reached:
        try:
            gap = float(a["mov"]) - float(a["subtotal"])
            if gap > 0:
                with_gap.append((gap, p, a))
        except (ValueError, TypeError):
            continue
    with_gap.sort(key=lambda x: x[0])
    cheapest5 = with_gap[:5]

    # --- Build card ---

    card_body = [
        {
            "type": "TextBlock",
            "text": "Cart Summary",
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
            "type": "ColumnSet",
            "spacing": "Small",
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {"type": "TextBlock", "text": "Total Value", "isSubtle": True},
                        {
                            "type": "TextBlock",
                            "text": f"{currency} {total_value:,.2f}",
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
                        {"type": "TextBlock", "text": "Avg Progress", "isSubtle": True},
                        {
                            "type": "TextBlock",
                            "text": f"{avg_progress:.0%}",
                            "size": "ExtraLarge",
                            "weight": "Bolder",
                            "color": _progress_color(avg_progress),
                            "spacing": "None",
                        },
                    ],
                },
            ],
        },
        # --- Top 5 closest ---
        {
            "type": "TextBlock",
            "text": "**Top 5 Closest to MOV:**",
            "weight": "Bolder",
            "spacing": "Medium",
        },
    ]

    for prog, a in top5:
        gap = float(a["mov"]) - float(a["subtotal"])
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
                                "text": f"{_progress_bar(prog)} {prog:.0%}",
                                "spacing": "None",
                                "color": _progress_color(prog),
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"needs {a['movCurrency']} {gap:,.2f}",
                                "isSubtle": True,
                                "spacing": "None",
                            }
                        ],
                    },
                ],
            }
        )

    # --- Cheapest to complete ---
    card_body.append(
        {
            "type": "TextBlock",
            "text": "**Cheapest to Complete:**",
            "weight": "Bolder",
            "spacing": "Medium",
        }
    )

    for gap, prog, a in cheapest5:
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
                                "text": f"{_progress_bar(prog)} {prog:.0%}",
                                "spacing": "None",
                                "color": _progress_color(prog),
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"needs {a['movCurrency']} {gap:,.2f}",
                                "weight": "Bolder",
                                "spacing": "None",
                                "color": "Good",
                            }
                        ],
                    },
                ],
            }
        )

    _post_card(webhook_url, card_body)
