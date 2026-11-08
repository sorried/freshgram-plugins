# licensed under the repository license in ../LICENSE

import re
import time
from urllib.parse import quote

import freshgram
from freshgram import aio


state = {}
last_search = None
user_agent = "Coverdrop/0.1.0 (https://github.com/sorried/freshgram-plugins)"
release_id_pattern = re.compile(r"^[0-9a-f-]{36}$")


def search_dialog(message=""):
    items = [
        {"type": "text", "text": "введите исполнителя и название трека. данные будут отправлены в MusicBrainz для поиска."},
        {"type": "input", "id": "artist", "label": "исполнитель", "value": state.get("artist", ""), "max": 120},
        {"type": "input", "id": "track", "label": "название трека", "value": state.get("track", ""), "max": 120},
    ]
    if message:
        items.append({"type": "text", "text": message, "style": "muted"})
    return items


async def show_search(message=""):
    await aio.ui.dialog(
        "поиск обложки",
        search_dialog(message),
        buttons=[
            {"id": "search", "label": "найти", "style": "primary"},
            {"id": "cancel", "label": "закрыть"},
        ],
    )


async def show_results(message=""):
    items = [{"type": "text", "text": "выберите издание трека:"}]
    for index, result in enumerate(state.get("results", [])):
        label = " · ".join(part for part in (result["release"], result["artist"], result.get("date", "")) if part)
        items.append({"type": "button", "id": f"result_{index}", "label": label[:120]})
    if message:
        items.insert(0, {"type": "text", "text": message, "style": "muted"})
    await aio.ui.dialog("результаты поиска", items, buttons=[{"id": "edit", "label": "изменить поиск"}])


async def show_preview(message=""):
    cover = state.get("cover")
    items = []
    if message:
        items.append({"type": "text", "text": message, "style": "muted"})
    items.extend([
        {"type": "image", "data": cover, "alt": "обложка релиза"},
        {"type": "text", "text": state.get("selected_title", "")},
        {"type": "text", "text": "обложка будет отправлена отдельным сообщением в текущий чат."},
    ])
    await aio.ui.dialog(
        "предпросмотр обложки",
        items,
        buttons=[
            {"id": "send_cover", "label": "отправить отдельно", "style": "primary"},
            {"id": "back", "label": "назад"},
        ],
    )


def escape_query(value):
    special = "+-&|!(){}[]^\"~*?:\\/"
    return "".join("\\" + char if char in special else char for char in value)


async def find_releases(artist, track):
    query = f'recording:"{escape_query(track)}" AND artist:"{escape_query(artist)}"'
    url = "https://musicbrainz.org/ws/2/recording/?" + (
        "query=" + quote(query, safe="") + "&fmt=json&limit=5"
    )
    response = await aio.net.get(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=15000,
    )
    if not response.ok:
        raise ValueError(f"MusicBrainz вернул HTTP {response.status}")

    payload = response.json()
    results = []
    seen = set()
    for recording in payload.get("recordings", []):
        for release in recording.get("releases", []):
            release_id = release.get("id", "")
            if not release_id_pattern.fullmatch(release_id) or release_id in seen:
                continue
            seen.add(release_id)
            credits = release.get("artist-credit", [])
            credited_artist = "".join(
                item if isinstance(item, str) else item.get("name", "")
                for item in credits
            )
            results.append({
                "id": release_id,
                "release": release.get("title", ""),
                "artist": credited_artist,
                "date": release.get("date", ""),
            })
            if len(results) == 5:
                return results
    return results


async def load_cover(release_id):
    response = await aio.net.get(
        f"https://coverartarchive.org/release/{release_id}",
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=15000,
    )
    if not response.ok:
        if response.status == 404:
            return None
        raise ValueError(f"Cover Art Archive вернул HTTP {response.status}")

    payload = response.json()
    front = next((image for image in payload.get("images", []) if image.get("front")), None)
    image_url = front.get("thumbnails", {}).get("250") if front else None
    if not isinstance(image_url, str) or not image_url.startswith("https://coverartarchive.org/"):
        return None

    image_response = await aio.net.get(
        image_url,
        headers={"User-Agent": user_agent},
        timeout=20000,
    )
    if not image_response.ok:
        raise ValueError(f"загрузка изображения завершилась с HTTP {image_response.status}")
    data = image_response.body
    if len(data) > 256 * 1024:
        raise ValueError("изображение превышает лимит предпросмотра 256 КиБ")
    if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("источник вернул неподдерживаемый формат изображения")
    return data


@freshgram.on_command("coverdrop")
async def open_coverdrop(event):
    chat = event.get("chat")
    if not isinstance(chat, int):
        freshgram.log("команда coverdrop пришла без chat")
        return
    state.clear()
    state.update({"chat": chat, "artist": "", "track": "", "results": []})
    await show_search()


@freshgram.on("dialog.change")
def update_input(event):
    field = event.get("id")
    if field in ("artist", "track") and isinstance(event.get("value"), str):
        state[field] = event["value"].strip()


@freshgram.on("dialog.click")
async def handle_dialog(event):
    global last_search
    action = event.get("id", "")

    if action == "cancel":
        state.clear()
        return

    if action == "edit":
        await show_search()
        return

    if action == "search":
        artist = state.get("artist", "")
        track = state.get("track", "")
        if not artist or not track:
            await show_search("укажите исполнителя и название трека.")
            return
        if len(artist) > 120 or len(track) > 120:
            await show_search("исполнитель и название должны быть короче 120 символов.")
            return
        now = time.monotonic()
        if last_search is not None and now - last_search < 1.1:
            await show_search("подождите перед следующим запросом.")
            return
        last_search = now
        try:
            results = await find_releases(artist, track)
        except Exception as error:
            freshgram.log(f"ошибка поиска обложки: {type(error).__name__}: {error}")
            await show_search("источник поиска недоступен. проверьте подключение и разрешение HTTPS.")
            return
        state["results"] = results
        if not results:
            await show_search("релизы не найдены. проверьте написание исполнителя и названия.")
            return
        await show_results()
        return

    if action.startswith("result_"):
        try:
            index = int(action.removeprefix("result_"))
            result = state["results"][index]
        except (ValueError, IndexError):
            await show_results("этот результат больше недоступен. выберите другой.")
            return
        state["selected_title"] = " · ".join(
            part for part in (result["artist"], result["release"]) if part
        )
        try:
            cover = await load_cover(result["id"])
        except Exception as error:
            freshgram.log(f"ошибка загрузки обложки: {type(error).__name__}: {error}")
            await show_results("не удалось загрузить изображение. выберите другой релиз или повторите позже.")
            return
        if cover is None:
            await show_results("для этого релиза нет фронтальной обложки.")
            return
        state["cover"] = cover
        state["cover_name"] = "cover.jpg" if cover.startswith(b"\xff\xd8\xff") else "cover.png"
        state["selected_release"] = result
        await show_preview()
        return

    if action == "back":
        await show_results()
        return

    if action == "send_cover":
        if not state.get("cover") or not state.get("chat"):
            await show_search("сеанс поиска завершён. начните заново командой /coverdrop.")
            return
        result = state["selected_release"]
        caption = f"обложка: {result['artist']} — {result['release']}"
        try:
            await aio.messages.send_media(
                state["chat"],
                state["cover"],
                state["cover_name"],
                caption=caption[:400],
                kind="photo",
            )
        except Exception as error:
            freshgram.log(f"ошибка отправки обложки: {type(error).__name__}: {error}")
            await show_preview("не удалось отправить изображение. проверьте разрешение отправки сообщений.")
            return
        await aio.ui.dialog(
            "обложка отправлена",
            [{"type": "text", "text": "изображение отправлено отдельным сообщением."}],
            buttons=[{"id": "cancel", "label": "закрыть"}],
        )


freshgram.run()
 #
