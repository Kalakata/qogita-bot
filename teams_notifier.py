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
    """Color gradient: green 90%+, attention/red 75%+, warning/orange 50%+, accent 25%+, default below."""
    if prog >= 0.90:
        return "Good"
    if prog >= 0.75:
        return "Attention"
    if prog >= 0.50:
        return "Warning"
    if prog >= 0.25:
        return "Accent"
    return "Light"


def _alloc_row(fid: str, prog: float, mov_text: str, gap_text: str, gap_color: str = "Default", gap_bold: bool = False) -> dict:
    """Build a single allocation row with fid, progress bar, MOV amount, and gap."""
    return {
        "type": "ColumnSet",
        "spacing": "Small",
        "columns": [
            {
                "type": "Column",
                "width": "70px",
                "items": [
                    {"type": "TextBlock", "text": f"**{fid}**", "spacing": "None"}
                ],
            },
            {
                "type": "Column",
                "width": "45px",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{prog:.0%}",
                        "spacing": "None",
                        "color": _progress_color(prog),
                        "weight": "Bolder",
                    }
                ],
            },
            {
                "type": "Column",
                "width": "110px",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": mov_text,
                        "spacing": "None",
                        "isSubtle": True,
                        "horizontalAlignment": "Right",
                    }
                ],
            },
            {
                "type": "Column",
                "width": "110px",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": gap_text,
                        "spacing": "None",
                        "color": gap_color,
                        "weight": "Bolder" if gap_bold else "Default",
                        "isSubtle": not gap_bold,
                        "horizontalAlignment": "Right",
                    }
                ],
            },
        ],
    }


def send_summary(webhook_url: str, allocations: list[dict], reached_count: int, newly_reached: list[dict] | None = None) -> None:
    """Send a combined summary card to Teams, with MOV alerts at the top if any."""
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
    not_reached = [(p, a) for p, a in valid if round(p * 100) < 100]
    not_reached.sort(key=lambda x: x[0], reverse=True)
    top5 = not_reached[:5]

    # Cheapest to complete
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
    card_body = []

    # --- MOV reached section (if any newly reached) ---
    if newly_reached:
        card_body.append(
            {
                "type": "TextBlock",
                "text": "MOV REACHED!",
                "weight": "Bolder",
                "size": "Large",
                "color": "Good",
            }
        )

        for alloc in newly_reached:
            card_body.append(
                {
                    "type": "ColumnSet",
                    "spacing": "Small",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {"type": "TextBlock", "text": "Cart", "isSubtle": True},
                                {
                                    "type": "TextBlock",
                                    "text": alloc["fid"],
                                    "size": "Large",
                                    "weight": "Bolder",
                                    "spacing": "None",
                                },
                            ],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {"type": "TextBlock", "text": "MOV Target", "isSubtle": True},
                                {
                                    "type": "TextBlock",
                                    "text": f"{alloc['movCurrency']} {alloc['mov']}",
                                    "size": "Large",
                                    "weight": "Bolder",
                                    "spacing": "None",
                                },
                            ],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {"type": "TextBlock", "text": "Cart Value", "isSubtle": True},
                                {
                                    "type": "TextBlock",
                                    "text": f"{alloc['movCurrency']} {alloc['subtotal']}",
                                    "size": "Large",
                                    "weight": "Bolder",
                                    "color": "Good",
                                    "spacing": "None",
                                },
                            ],
                        },
                    ],
                }
            )

        # Separator
        card_body.append(
            {
                "type": "TextBlock",
                "text": " ",
                "spacing": "Medium",
                "separator": True,
            }
        )

    # --- Summary stats ---
    card_body.append(
        {
            "type": "TextBlock",
            "text": "Cart Summary",
            "weight": "Bolder",
            "size": "Large",
        }
    )
    card_body.append(
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
                            "size": "Large",
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
                            "size": "Large",
                            "weight": "Bolder",
                            "color": "Good",
                            "spacing": "None",
                        },
                    ],
                },
            ],
        }
    )
    card_body.append(
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
                            "size": "Large",
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
                            "size": "Large",
                            "weight": "Bolder",
                            "color": _progress_color(avg_progress),
                            "spacing": "None",
                        },
                    ],
                },
            ],
        }
    )

    # --- Top 5 closest ---
    card_body.append(
        {
            "type": "TextBlock",
            "text": "**Top 5 Closest to MOV:**",
            "weight": "Bolder",
            "spacing": "Medium",
        }
    )
    for prog, a in top5:
        gap = float(a["mov"]) - float(a["subtotal"])
        card_body.append(
            _alloc_row(a["fid"], prog, f"{a['movCurrency']} {a['mov']}", f"-{a['movCurrency']} {gap:,.2f}")
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
            _alloc_row(a["fid"], prog, f"{a['movCurrency']} {a['mov']}", f"-{a['movCurrency']} {gap:,.2f}", gap_color="Good", gap_bold=True)
        )

    _post_card(webhook_url, card_body)


def send_price_drop_alert(webhook_url: str, deals: list[dict]) -> None:
    """Send a price drop alert card to Teams. Max 10 items shown."""
    shown = deals[:10]

    card_body = [
        {
            "type": "TextBlock",
            "text": "PRICE DROP ALERT",
            "weight": "Bolder",
            "size": "Large",
            "color": "Good",
        },
        {
            "type": "TextBlock",
            "text": f"**{len(deals)} items** 40%+ below target",
            "spacing": "Small",
        },
    ]

    for deal in shown:
        discount_pct = f"-{deal['discount']:.0%}"
        card_body.append(
            {
                "type": "ColumnSet",
                "spacing": "Small",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**{deal['name'][:35]}** `{deal['gtin']}`",
                                "spacing": "None",
                                "wrap": True,
                            },
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "80px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{deal['priceCurrency']} {deal['targetPrice']}",
                                "spacing": "None",
                                "isSubtle": True,
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "80px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{deal['priceCurrency']} {deal['price']}",
                                "spacing": "None",
                                "weight": "Bolder",
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "50px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": discount_pct,
                                "spacing": "None",
                                "color": "Good",
                                "weight": "Bolder",
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                ],
            }
        )

    if len(deals) > 10:
        card_body.append(
            {
                "type": "TextBlock",
                "text": f"*...and {len(deals) - 10} more*",
                "isSubtle": True,
                "spacing": "Small",
            }
        )

    _post_card(webhook_url, card_body)
