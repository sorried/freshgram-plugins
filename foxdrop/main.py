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


async def show_error(message):
    try:
        await aio.ui.toast(message, duration=5)
    except freshgram.FreshgramError as error:
        freshgram.log(f"foxdrop: не удалось показать ошибку: {error}")


async def fetch_fox():
    response = await aio.net.get(API_URL, headers={"Accept": "application/json"}, timeout=15000)
    if not response.ok:
        raise ValueError(f"сервис лис недоступен: HTTP {response.status}.")

    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError("сервис вернул некорректный JSON.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("image"), str):
        raise ValueError("сервис не вернул адрес изображения.")

    image_url = payload["image"]
    if not image_url.isascii() or len(image_url) > 2048:
        raise ValueError("сервис вернул недопустимый адрес изображения.")
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
        raise ValueError("сервис вернул недопустимый адрес изображения.") from error
    if not valid_url:
        raise ValueError("сервис вернул недопустимый адрес изображения.")

    image_response = await aio.net.get(image_url, timeout=20000)
    if not image_response.ok:
        raise ValueError(f"не удалось загрузить фото: HTTP {image_response.status}.")

    data = image_response.body
    if not data or len(data) > MAX_IMAGE_SIZE:
        raise ValueError("фото пустое или превышает 16 МиБ.")
    filename = image_name(data)
    if filename is None:
        raise ValueError("сервис вернул фото неизвестного формата.")
    return data, filename


@freshgram.on_menu("foxdrop", surface="composer")
async def send_fox(event):
    chat = event.get("chat")
    if not isinstance(chat, int) or isinstance(chat, bool) or chat <= 0:
        await show_error("откройте чат, чтобы отправить лису.")
        return

    try:
        data, filename = await fetch_fox()
    except freshgram.Denied as error:
        freshgram.log(f"foxdrop: доступ запрещён: {error}")
        await show_error("нет доступа к HTTPS. проверьте разрешения плагина.")
        return
    except ValueError as error:
        freshgram.log(f"foxdrop: ошибка данных изображения: {error}")
        await show_error(str(error))
        return
    except freshgram.FreshgramError as error:
        freshgram.log(f"foxdrop: ошибка загрузки: {error}")
        await show_error("не удалось загрузить лису. проверьте подключение.")
        return

    try:
        await aio.messages.send_media(
            chat, data, filename, kind="auto", topic=event.get("topic", 0), reply_to=0,
        )
    except freshgram.Denied as error:
        freshgram.log(f"foxdrop: отправка запрещена: {error}")
        await show_error("нет разрешения на отправку фото в этот чат.")
    except freshgram.FreshgramError as error:
        freshgram.log(f"foxdrop: ошибка отправки: {error}")
        await show_error("не удалось подтвердить отправку фото. проверьте чат.")


freshgram.run()
