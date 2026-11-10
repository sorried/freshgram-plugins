import freshgram
from freshgram import aio


chat_id = None
name = ""


@freshgram.on_menu("maxinstall", surface="composer")
async def ask_name(event):
    global chat_id, name
    chat = event.get("chat")
    if not isinstance(chat, int) or isinstance(chat, bool):
        return

    chat_id = chat
    name = ""
    await aio.ui.dialog(
        "MaxInstall",
        [{"type": "input", "id": "name", "label": "имя", "max": 120}],
        buttons=[
            {"id": "confirm", "label": "подставить", "style": "primary"},
            {"id": "cancel", "label": "отмена"},
        ],
    )


@freshgram.on("dialog.change")
def update_name(event):
    global name
    if event.get("id") == "name" and isinstance(event.get("value"), str):
        name = event["value"].strip()


@freshgram.on("dialog.click")
async def handle_dialog(event):
    global chat_id, name
    action = event.get("id")
    if action == "confirm" and chat_id is not None and name:
        text = (
            "Внимание, срочные новости\n\n"
            f"{name} подвергся вербовке со стороны мошенников и установил "
            "вредоносное приложение MAX! С этого момента за ним начали следить "
            "сотрудники: УМВД, МВД, ДПС, ППС, РКН, Росгвардии, ФСБ, СВР, ФСО, "
            "ФСИН, СОБР, ОВД, УР, СКР, ВПЛ, МЧС, СМП, СВР."
        )
        result = freshgram.call({
            "op": "composer.set_draft",
            "a": {"chat": chat_id, "text": text, "replace": True},
        })
        if not result.get("ok"):
            freshgram.log(f"maxinstall: composer.set_draft failed: {result.get('e', 'unknown')}")

    if action in ("confirm", "cancel"):
        chat_id = None
        name = ""
        await aio.ui.close_dialog()


@freshgram.on("dialog.close")
def clear_dialog_state(event):
    global chat_id, name
    chat_id = None
    name = ""


freshgram.run()
