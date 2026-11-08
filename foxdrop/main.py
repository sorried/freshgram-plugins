import random
from urllib.parse import urlsplit

import freshgram
from freshgram import aio


FOX_APIS = (
    ("https://randomfox.ca/floof/", "image", "https://", {"randomfox.ca"}),
    ("https://api.sefinek.net/api/v2/random/animal/fox", "message", "https://", {"cdn.sefinek.net"}),
    ("https://api.some-random-api.com/animal/fox", "image", "https://", {"i.imgur.com"}),
    ("https://api.some-random-api.com/img/fox", "link", "https://", {"i.imgur.com"}),
    ("https://api.tinyfox.dev/img?animal=fox&json", "loc", "https://api.tinyfox.dev", {"api.tinyfox.dev"}),
)
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
    sources = list(FOX_APIS)
    random.shuffle(sources)
    errors = []
    for api_url, image_field, image_prefix, hosts in sources:
        try:
            response = await aio.net.get(
                api_url, headers={"Accept": "application/json"}, timeout=15000,
            )
            if not response.ok:
                raise ValueError(f"API HTTP {response.status}")
            try:
                payload = response.json()
            except ValueError as error:
                raise ValueError("invalid JSON") from error
            if not isinstance(payload, dict) or not isinstance(payload.get(image_field), str):
                raise ValueError("image URL is missing")

            image_url = payload[image_field]
            if image_field == "loc" and image_url.startswith("/"):
                image_url = image_prefix + image_url
            if not image_url.isascii() or len(image_url) > 2048:
                raise ValueError("invalid image URL")
            try:
                parsed = urlsplit(image_url)
                valid_url = (
                    parsed.scheme == "https"
                    and parsed.hostname in hosts
                    and parsed.port in (None, 443)
                    and not parsed.username
                    and not parsed.password
                )
            except ValueError as error:
                raise ValueError("invalid image URL") from error
            if not valid_url:
                raise ValueError("image URL host is not allowed")

            image_response = await aio.net.get(image_url, timeout=20000)
            if not image_response.ok:
                raise ValueError(f"image HTTP {image_response.status}")
            data = image_response.body
            if not data or len(data) > MAX_IMAGE_SIZE:
                raise ValueError("image is empty or larger than 16 MiB")
            filename = image_name(data)
            if filename is None:
                raise ValueError("unsupported image format")
            return data, filename
        except freshgram.Denied:
            raise
        except (ValueError, freshgram.FreshgramError) as error:
            freshgram.log(f"foxdrop: source {api_url} failed: {error}")
            errors.append(str(error))

    raise ValueError("All fox image sources failed. Please try again later.")


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
