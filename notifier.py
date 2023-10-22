import requests

import params

TOKEN = params.TELEGRAM_BOT_TOKEN
CHAT_ID = params.TELEGRAM_BOT_CHAT_ID
URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def notify(message: str):
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_notification": True
    }

    print(f"Sending {data} to {URL}")

    response = requests.post(
        URL,
        json=data,
        headers={"Content-Type": "application/json"},
    )

    print(response)


if __name__ == "__main__":
    notify("testing...")
