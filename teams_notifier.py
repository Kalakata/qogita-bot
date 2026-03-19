import requests


def send_notification(webhook_url: str, allocation: dict) -> None:
    """Send a Teams notification for an allocation that reached MOV."""
    fid = allocation["fid"]
    mov = allocation["mov"]
    currency = allocation["movCurrency"]

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"Cart allocation {fid} reached MOV",
        "text": f"Cart allocation **{fid}** has reached its MOV! ({currency} {mov})",
    }

    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()
