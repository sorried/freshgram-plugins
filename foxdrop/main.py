from urllib.parse import urlsplit

import freshgram
from freshgram import aio


API_URL = "https://randomfox.ca/floof/"
MAX_IMAGE_SIZE = 16 * 1024 * 1024


def image_name(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "fox.jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "fox.png"
    return None


async def show_notice(message):
    try:
        await aio.ui.toast(message, duration=5)
    except freshgram.FreshgramError as error:
        freshgram.log(f"foxdrop: failed to show notice: {error}")


async def fetch_fox():
    response = await aio.net.get(API_URL, headers={"Accept": "application/json"}, timeout=15000)
    if not response.ok:
        raise ValueError(f"Fox service unavailable: HTTP {response.status}.")

    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("Fox service returned invalid JSON.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("image"), str):
        raise ValueError("Fox service did not return an image URL.")

    image_url = payload["image"]
    if not image_url.isascii() or len(image_url) > 2048:
        raise ValueError("Fox service returned an invalid image URL.")
    try:
        parsed = urlsplit(image_url)
        valid_url = (
            parsed.scheme == "https"
            and parsed.hostname == "randomfox.ca"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
        )
    except ValueError as error:
        raise ValueError("Fox service returned an invalid image URL.") from error
    if not valid_url:
        raise ValueError("Fox service returned an invalid image URL.")

    image_response = await aio.net.get(image_url, timeout=20000)
    if not image_response.ok:
        raise ValueError(f"Could not download fox image: HTTP {image_response.status}.")

    data = image_response.body
    if not data or len(data) > MAX_IMAGE_SIZE:
        raise ValueError("Fox image is empty or larger than 16 MiB.")
    filename = image_name(data)
    if filename is None:
        raise ValueError("Fox service returned an unsupported image format.")
    return data, filename


@freshgram.on_menu("foxdrop", surface="composer")
async def send_fox(event):
    chat = event.get("chat")
    if not isinstance(chat, int) or isinstance(chat, bool) or chat <= 0:
        await show_notice("Open a chat to send a fox.")
        return

    await show_notice("Loading a fox…")

    try:
        data, filename = await fetch_fox()
    except freshgram.Denied as error:
        freshgram.log(f"foxdrop: HTTPS access denied: {error}")
        await show_notice("HTTPS access denied. Check the plugin permissions.")
        return
    except ValueError as error:
        freshgram.log(f"foxdrop: invalid image response: {error}")
        await show_notice(str(error))
        return
    except freshgram.FreshgramError as error:
        freshgram.log(f"foxdrop: image request failed: {error}")
        await show_notice("Could not load a fox. Check your connection.")
        return

    try:
        await aio.messages.send_media(
            chat, data, filename, kind="auto", topic=event.get("topic", 0), reply_to=0,
        )
    except freshgram.Denied as error:
        freshgram.log(f"foxdrop: sending denied: {error}")
        await show_notice("Photo sending is not allowed in this chat.")
    except freshgram.FreshgramError as error:
        freshgram.log(f"foxdrop: send failed: {error}")
        await show_notice("Could not send the photo. Check the chat and try again.")


freshgram.run()
