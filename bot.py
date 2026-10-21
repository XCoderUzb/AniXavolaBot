"""
AniManxwa - Telegram mini app havolalarini yaratish va tahrirlash boti.

Admin:  /start -> "Hush kelibsiz" + [Yangi havola yaratish] [Tahrirlash]
Oddiy:  /start -> "Salom, botdan foydalanishingiz mumkin"

Har bir havola = kalit (startapp qismi) + sayt havolasi.
Tayyor havola: https://t.me/<BOT_USERNAME>/<APP_SHORT_NAME>?startapp=<kalit>

Sayt kalit orqali manzilni olishi uchun:  GET /api/link?key=<kalit>
"""
import asyncio
import html
import json
import logging
import os
import re
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------- sozlamalar
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}
BOT_USERNAME = os.getenv("BOT_USERNAME", "AniXavolaBot").lstrip("@")
APP_SHORT_NAME = os.getenv("APP_SHORT_NAME", "animanxwa")
PAGE_SIZE = 10
# callback_data 64 baytdan oshmasligi uchun kalit 50 belgigacha
KEY_RE = re.compile(r"^[A-Za-z0-9_=\-]{1,50}$")


def tg_link(key: str) -> str:
    return f"https://t.me/{BOT_USERNAME}/{APP_SHORT_NAME}?startapp={key}"


def valid_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc) and " " not in url


# ------------------------------------------------------------------ saqlash
class Store:
    """MONGO_URI bo'lsa MongoDB, bo'lmasa JSON fayl (Render'da fayl o'chib ketadi!)."""

    def __init__(self):
        uri = os.getenv("MONGO_URI")
        if uri:
            from motor.motor_asyncio import AsyncIOMotorClient

            db = AsyncIOMotorClient(uri)[os.getenv("MONGO_DB", "animanxwa")]
            self.col = db["links"]
        else:
            self.col = None
            self.file = os.getenv("DATA_FILE", "links.json")
            self.data = {}
            if os.path.exists(self.file):
                with open(self.file, encoding="utf-8") as f:
                    self.data = json.load(f)

    def _dump(self):
        tmp = self.file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.file)

    async def all(self):
        if self.col is not None:
            return [(d["_id"], d["url"]) async for d in self.col.find().sort("_id", 1)]
        return sorted(self.data.items())

    async def get(self, key):
        if self.col is not None:
            d = await self.col.find_one({"_id": key})
            return d["url"] if d else None
        return self.data.get(key)

    async def set(self, key, url):
        if self.col is not None:
            await self.col.update_one({"_id": key}, {"$set": {"url": url}}, upsert=True)
        else:
            self.data[key] = url
            self._dump()

    async def delete(self, key):
        if self.col is not None:
            await self.col.delete_one({"_id": key})
        else:
            self.data.pop(key, None)
            self._dump()


store = Store()


# ------------------------------------------------------------------ tugmalar
def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Yangi havola yaratish", callback_data="new")
    kb.button(text="✏️ Tahrirlash", callback_data="edit")
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Bekor qilish", callback_data="home")
    return kb.as_markup()


async def list_view(page: int):
    items = await store.all()
    total = len(items)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)

    kb = InlineKeyboardBuilder()
    for key, _ in items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
        kb.row(InlineKeyboardButton(text=key, callback_data=f"v:{key}"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"p:{page - 1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"p:{page + 1}"))
    if nav:
        kb.row(*nav)
    kb.row(InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="home"))

    if total == 0:
        text = "Hozircha havolalar yo'q."
    else:
        text = f"Tahrirlash uchun havolani tanlang (jami: {total} ta):"
    return text, kb.as_markup()


async def card_view(key: str):
    url = await store.get(key)
    if url is None:
        return None
    text = (
        f"🔗 <b>Kalit:</b> <code>{html.escape(key)}</code>\n"
        f"🌐 <b>Sayt:</b> {html.escape(url)}\n\n"
        f"📲 <b>Mini app havolasi:</b>\n<code>{html.escape(tg_link(key))}</code>"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🌐 Sayt havolasini o'zgartirish", callback_data=f"u:{key}"))
    kb.row(InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"d:{key}"))
    kb.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="edit"))
    return text, kb.as_markup()


# ------------------------------------------------------------------- holatlar
class NewLink(StatesGroup):
    key = State()
    url = State()


class EditUrl(StatesGroup):
    url = State()


# ------------------------------------------------------------------- routerlar
public = Router()
admin = Router()
admin.message.filter(F.from_user.id.in_(ADMIN_IDS))
admin.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


@public.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    if m.from_user.id in ADMIN_IDS:
        await m.answer("Hush kelibsiz", reply_markup=main_kb())
    else:
        await m.answer("Salom, botdan foydalanishingiz mumkin")


@admin.callback_query(F.data == "home")
async def home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Hush kelibsiz", reply_markup=main_kb())
    await cb.answer()


# ---- yangi havola
@admin.callback_query(F.data == "new")
async def new_link(cb: CallbackQuery, state: FSMContext):
    await state.set_state(NewLink.key)
    await cb.message.edit_text(
        "Havola kalitini yozing (<code>startapp=</code> dan keyingi qism).\n"
        "Masalan: <code>manhwa_1_2</code>\n\n"
        "Ruxsat etilgan belgilar: A-Z, a-z, 0-9, _ - =",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@admin.message(NewLink.key, F.text)
async def got_key(m: Message, state: FSMContext):
    key = m.text.strip()
    if not KEY_RE.match(key):
        await m.answer(
            "❌ Kalit noto'g'ri. Faqat A-Z, a-z, 0-9, _ - = ishlating (50 belgigacha).",
            reply_markup=cancel_kb(),
        )
        return
    if await store.get(key) is not None:
        await m.answer(
            "❌ Bu kalit allaqachon mavjud. Boshqa kalit yozing yoki «Tahrirlash» orqali o'zgartiring.",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(key=key)
    await state.set_state(NewLink.url)
    await m.answer(
        "Endi sayt havolasini yozing (https://... bilan):", reply_markup=cancel_kb()
    )


@admin.message(NewLink.url, F.text)
async def got_url(m: Message, state: FSMContext):
    url = m.text.strip()
    if not valid_url(url):
        await m.answer("❌ Havola noto'g'ri. https:// bilan boshlanishi kerak.", reply_markup=cancel_kb())
        return
    key = (await state.get_data())["key"]
    await store.set(key, url)
    await state.clear()
    text, kb = await card_view(key)
    await m.answer("✅ Havola yaratildi!\n\n" + text, reply_markup=kb)


# ---- tahrirlash
@admin.callback_query(F.data == "edit")
async def edit_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await list_view(0)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@admin.callback_query(F.data.startswith("p:"))
async def edit_page(cb: CallbackQuery):
    text, kb = await list_view(int(cb.data[2:]))
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@admin.callback_query(F.data.startswith("v:"))
async def view_link(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    res = await card_view(cb.data[2:])
    if res is None:
        await cb.answer("Havola topilmadi", show_alert=True)
        return
    await cb.message.edit_text(res[0], reply_markup=res[1])
    await cb.answer()


@admin.callback_query(F.data.startswith("u:"))
async def change_url(cb: CallbackQuery, state: FSMContext):
    key = cb.data[2:]
    await state.set_state(EditUrl.url)
    await state.update_data(key=key)
    await cb.message.edit_text(
        f"<code>{html.escape(key)}</code> uchun yangi sayt havolasini yozing:",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@admin.message(EditUrl.url, F.text)
async def got_new_url(m: Message, state: FSMContext):
    url = m.text.strip()
    if not valid_url(url):
        await m.answer("❌ Havola noto'g'ri. https:// bilan boshlanishi kerak.", reply_markup=cancel_kb())
        return
    key = (await state.get_data())["key"]
    await store.set(key, url)
    await state.clear()
    text, kb = await card_view(key)
    await m.answer("✅ Sayt havolasi yangilandi!\n\n" + text, reply_markup=kb)


@admin.callback_query(F.data.startswith("d:"))
async def ask_delete(cb: CallbackQuery):
    key = cb.data[2:]
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, o'chirish", callback_data=f"dd:{key}")
    kb.button(text="❌ Yo'q", callback_data=f"v:{key}")
    kb.adjust(2)
    await cb.message.edit_text(
        f"<code>{html.escape(key)}</code> havolasini o'chirasizmi?", reply_markup=kb.as_markup()
    )
    await cb.answer()


@admin.callback_query(F.data.startswith("dd:"))
async def do_delete(cb: CallbackQuery):
    await store.delete(cb.data[3:])
    text, kb = await list_view(0)
    await cb.message.edit_text("🗑 O'chirildi.\n\n" + text, reply_markup=kb)
    await cb.answer()


# ------------------------------------------------------------ veb-server (Render)
async def health(_request):
    return web.Response(text="ok")


async def api_link(request):
    headers = {"Access-Control-Allow-Origin": "*"}
    key = request.query.get("key", "")
    url = await store.get(key) if KEY_RE.match(key) else None
    if not url:
        return web.json_response({"ok": False}, status=404, headers=headers)
    return web.json_response({"ok": True, "url": url}, headers=headers)


async def main():
    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(public)
    dp.include_router(admin)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/api/link", api_link)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
