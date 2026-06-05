import os
import threading
import logging
import json
import base64
from datetime import datetime
from flask import Flask, render_template_string, jsonify
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ══════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "SIZNING_TOKENINGIZ")
ADMIN_ID           = int(os.environ.get("ADMIN_ID", "123456789"))
BASE_URL           = os.environ.get("WEBAPP_URL", "https://your-app.onrender.com").rstrip("/")
MENU_URL           = BASE_URL + "/menu"
# ══════════════════════════════════════════════

restaurant = {
    "name":    "Mening Restoran",
    "bio":     "Mazali taomlar, tez yetkazib berish!",
    "address": "Toshkent, Chilonzor",
    "phone":   "+998 90 000 00 00",
    "hours":   "10:00 - 22:00",
}

menu_items = []
users      = {}
orders     = {}
order_cnt  = [0]
item_cnt   = [0]

DATA_FILE = "/tmp/restaurant_data.json"

def save_data():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump({
                "menu_items": menu_items,
                "restaurant": restaurant,
                "item_cnt": item_cnt[0],
            }, f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"save_data xato: {e}")

def load_data():
    global menu_items, restaurant
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            menu_items.extend(data.get("menu_items", []))
            restaurant.update(data.get("restaurant", {}))
            item_cnt[0] = data.get("item_cnt", 0)
    except Exception:
        pass

load_data()

STATUS = {
    "new":      "🆕 Yangi",
    "accepted": "✅ Qabul qilindi",
    "cooking":  "👨‍🍳 Tayyorlanmoqda",
    "delivery": "🛵 Yo'lda",
    "done":     "🎉 Yetkazildi",
    "cancelled":"❌ Bekor qilindi",
}

REG_NAME, REG_PHONE = range(2)
ADMIN_ITEM_NAME, ADMIN_ITEM_DESC, ADMIN_ITEM_PRICE, ADMIN_ITEM_CAT, ADMIN_ITEM_PHOTO = range(10, 15)

flask_app = Flask(__name__)

MENU_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Menyu</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--tg-theme-bg-color,#fff); color: var(--tg-theme-text-color,#000); padding-bottom: 80px; }
.header { background: var(--tg-theme-secondary-bg-color,#f5f5f5); padding: 16px; text-align: center; border-bottom: 1px solid rgba(0,0,0,0.08); }
.header h1 { font-size: 20px; font-weight: 700; }
.header p { font-size: 13px; opacity: 0.6; margin-top: 4px; }
.cats { display: flex; gap: 8px; padding: 12px 16px; overflow-x: auto; scrollbar-width: none; border-bottom: 1px solid rgba(0,0,0,0.06); }
.cats::-webkit-scrollbar { display: none; }
.cat-btn { white-space: nowrap; padding: 6px 14px; border-radius: 20px; border: 1.5px solid rgba(0,0,0,0.12); background: transparent; font-size: 13px; cursor: pointer; color: var(--tg-theme-text-color,#000); }
.cat-btn.active { background: var(--tg-theme-button-color,#2481cc); color: var(--tg-theme-button-text-color,#fff); border-color: transparent; }
.items { padding: 12px 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.item { background: var(--tg-theme-secondary-bg-color,#f5f5f5); border-radius: 14px; overflow: hidden; cursor: pointer; transition: transform 0.1s; }
.item:active { transform: scale(0.97); }
.item-img { width: 100%; aspect-ratio: 1; object-fit: cover; }
.item-img-ph { width: 100%; aspect-ratio: 1; background: rgba(0,0,0,0.06); display: flex; align-items: center; justify-content: center; font-size: 40px; }
.item-body { padding: 10px; }
.item-name { font-size: 14px; font-weight: 600; }
.item-price { font-size: 13px; color: var(--tg-theme-button-color,#2481cc); margin-top: 4px; font-weight: 500; }
.cart-bar { position: fixed; bottom: 0; left: 0; right: 0; background: var(--tg-theme-button-color,#2481cc); color: var(--tg-theme-button-text-color,#fff); padding: 14px 20px; display: none; justify-content: space-between; align-items: center; font-weight: 600; cursor: pointer; }
.overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 100; align-items: flex-end; }
.overlay.show { display: flex; }
.modal { background: var(--tg-theme-bg-color,#fff); border-radius: 20px 20px 0 0; padding: 20px; width: 100%; max-height: 90vh; overflow-y: auto; }
.modal-img { width: 100%; border-radius: 12px; margin-bottom: 12px; }
.modal-name { font-size: 20px; font-weight: 700; }
.modal-desc { font-size: 14px; opacity: 0.6; margin: 6px 0 12px; }
.modal-price { font-size: 22px; font-weight: 700; color: var(--tg-theme-button-color,#2481cc); }
.qty-row { display: flex; align-items: center; gap: 16px; margin: 16px 0; }
.qty-btn { width: 36px; height: 36px; border-radius: 50%; border: none; background: var(--tg-theme-secondary-bg-color,#f0f0f0); font-size: 20px; cursor: pointer; color: var(--tg-theme-text-color); display:flex; align-items:center; justify-content:center; }
.qty-num { font-size: 20px; font-weight: 700; min-width: 30px; text-align: center; }
.add-btn { width: 100%; padding: 14px; border: none; border-radius: 14px; background: var(--tg-theme-button-color,#2481cc); color: var(--tg-theme-button-text-color,#fff); font-size: 16px; font-weight: 600; cursor: pointer; }
.cart-h2 { font-size: 18px; font-weight: 700; margin-bottom: 16px; }
.cart-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(0,0,0,0.06); }
.cart-total { display: flex; justify-content: space-between; padding: 14px 0; font-weight: 700; font-size: 16px; }
.checkout-btn { width: 100%; padding: 14px; border: none; border-radius: 14px; background: #34c759; color: #fff; font-size: 16px; font-weight: 600; cursor: pointer; }
.rm-btn { background: none; border: none; color: #ff453a; font-size: 18px; cursor: pointer; }
.empty { text-align: center; padding: 40px; opacity: 0.5; }
.spinner { display:inline-block; width:40px; height:40px; border:3px solid rgba(0,0,0,0.1); border-top-color: var(--tg-theme-button-color,#2481cc); border-radius:50%; animation:spin 0.8s linear infinite; margin: 40px auto; }
@keyframes spin { to { transform:rotate(360deg); } }
.loading { display:flex; justify-content:center; }
</style>
</head>
<body>
<div class="header"><h1 id="rname">...</h1><p id="rhours"></p></div>
<div class="cats" id="cats"></div>
<div id="items-wrap"><div class="loading"><div class="spinner"></div></div></div>
<div class="cart-bar" id="cart-bar" onclick="showCart()">
  <span id="cart-cnt">0 ta</span><span id="cart-tot-bar">0 so'm</span>
</div>
<div class="overlay" id="item-modal" onclick="if(event.target===this)closeItem()">
  <div class="modal">
    <div id="mi-img"></div>
    <div class="modal-name" id="mi-name"></div>
    <div class="modal-desc" id="mi-desc"></div>
    <div class="modal-price" id="mi-price"></div>
    <div class="qty-row">
      <button class="qty-btn" onclick="chQty(-1)">−</button>
      <span class="qty-num" id="mi-qty">1</span>
      <button class="qty-btn" onclick="chQty(1)">+</button>
    </div>
    <button class="add-btn" onclick="addCart()">Savatchaga qo'shish</button>
  </div>
</div>
<div class="overlay" id="cart-modal" onclick="if(event.target===this)closeCart()">
  <div class="modal">
    <div class="cart-h2">🛒 Savatcha</div>
    <div id="cart-items"></div>
    <div class="cart-total"><span>Jami:</span><span id="cart-tot-m">0 so'm</span></div>
    <button class="checkout-btn" onclick="checkout()">✅ Buyurtma berish</button>
  </div>
</div>
<script>
const tg=window.Telegram.WebApp;tg.ready();tg.expand();
let menu=[],cart=[],sel=null,qty=1;
function fmt(p){return p.toLocaleString('uz-UZ')+" so'm";}
function load(){
  try{
    const d = __MENU_DATA__;
    document.getElementById('rname').textContent=d.restaurant.name;
    document.getElementById('rhours').textContent=d.restaurant.hours;
    menu=d.items;
    if(menu.length===0){
      document.getElementById('items-wrap').innerHTML='<p class="empty">Hozircha menyu mavjud emas</p>';
      return;
    }
    renderCats();renderItems('all');
  }catch(e){
    document.getElementById('items-wrap').innerHTML='<p class="empty">Xato yuz berdi</p>';
  }
}
function renderCats(){
  const cats=['all',...new Set(menu.map(i=>i.category))];
  document.getElementById('cats').innerHTML=cats.map(c=>
    `<button class="cat-btn${c==='all'?' active':''}" onclick="fcat('${c}',this)">${c==='all'?'Barchasi':c}</button>`
  ).join('');
}
function fcat(c,el){
  document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');renderItems(c);
}
function renderItems(cat){
  const f=cat==='all'?menu:menu.filter(i=>i.category===cat);
  if(!f.length){document.getElementById('items-wrap').innerHTML='<p class="empty">Taomlar yo\'q</p>';return;}
  document.getElementById('items-wrap').innerHTML=`<div class="items">${f.map(i=>`
    <div class="item" onclick="openItem('${i.id}')">
      ${i.photo?`<img class="item-img" src="data:image/jpeg;base64,${i.photo}">`:`<div class="item-img-ph">🍽</div>`}
      <div class="item-body"><div class="item-name">${i.name}</div><div class="item-price">${fmt(i.price)}</div></div>
    </div>`).join('')}</div>`;
}
function openItem(id){
  sel=menu.find(i=>i.id===id);qty=1;if(!sel)return;
  document.getElementById('mi-name').textContent=sel.name;
  document.getElementById('mi-desc').textContent=sel.desc||'';
  document.getElementById('mi-price').textContent=fmt(sel.price);
  document.getElementById('mi-qty').textContent='1';
  document.getElementById('mi-img').innerHTML=sel.photo?`<img class="modal-img" src="data:image/jpeg;base64,${sel.photo}">`:'' ;
  document.getElementById('item-modal').classList.add('show');
}
function closeItem(){document.getElementById('item-modal').classList.remove('show');}
function chQty(d){qty=Math.max(1,qty+d);document.getElementById('mi-qty').textContent=qty;}
function addCart(){
  if(!sel)return;
  const ex=cart.find(c=>c.id===sel.id);
  if(ex)ex.qty+=qty;else cart.push({...sel,qty});
  closeItem();updateBar();
}
function updateBar(){
  const tot=cart.reduce((s,c)=>s+c.price*c.qty,0);
  const cnt=cart.reduce((s,c)=>s+c.qty,0);
  const bar=document.getElementById('cart-bar');
  if(cnt>0){bar.style.display='flex';document.getElementById('cart-cnt').textContent=cnt+' ta';document.getElementById('cart-tot-bar').textContent=fmt(tot);}
  else bar.style.display='none';
}
function showCart(){
  const tot=cart.reduce((s,c)=>s+c.price*c.qty,0);
  document.getElementById('cart-tot-m').textContent=fmt(tot);
  document.getElementById('cart-items').innerHTML=!cart.length?'<p class="empty">Bo\'sh</p>':
    cart.map((c,i)=>`<div class="cart-item"><div><div style="font-weight:500">${c.name} × ${c.qty}</div><div style="opacity:.6;font-size:13px">${fmt(c.price*c.qty)}</div></div><button class="rm-btn" onclick="rmCart(${i})">✕</button></div>`).join('');
  document.getElementById('cart-modal').classList.add('show');
}
function closeCart(){document.getElementById('cart-modal').classList.remove('show');}
function rmCart(i){cart.splice(i,1);updateBar();showCart();}
function checkout(){
  if(!cart.length)return;
  tg.sendData(JSON.stringify({items:cart.map(c=>({id:c.id,name:c.name,price:c.price,qty:c.qty})),total:cart.reduce((s,c)=>s+c.price*c.qty,0)}));
  tg.close();
}
load();
</script>
</body>
</html>"""

@flask_app.route("/menu")
def menu_page():
    import json as _json
    data = _json.dumps({
        "restaurant": restaurant,
        "items": menu_items
    }, ensure_ascii=False)
    html = MENU_HTML.replace("__MENU_DATA__", data)
    return html

@flask_app.route("/api/menu")
def api_menu():
    return jsonify({"restaurant": restaurant, "items": menu_items})

@flask_app.route("/")
@flask_app.route("/health")
def health():
    return "OK", 200

def fmt(price):
    return f"{price:,}".replace(",", " ") + " so'm"

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍽 Menyu & Buyurtma", web_app=WebAppInfo(url=MENU_URL))],
        [InlineKeyboardButton("📦 Buyurtmalarim", callback_data="my_orders")],
    ])

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Buyurtmalar",      callback_data="admin_orders")],
        [InlineKeyboardButton("🍽 Menyu boshqaruv",  callback_data="admin_menu_mgmt")],
        [InlineKeyboardButton("🏪 Restoran sozlash", callback_data="admin_settings")],
        [InlineKeyboardButton("📊 Statistika",       callback_data="admin_stats")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        await update.message.reply_text(
            f"👨‍💼 *Admin paneli*\n🏪 {restaurant['name']}",
            parse_mode='Markdown', reply_markup=admin_kb())
        return ConversationHandler.END
    if uid in users:
        u = users[uid]
        await update.message.reply_text(
            f"👋 Salom, *{u['name']}*!\n\n"
            f"🏪 *{restaurant['name']}*\n"
            f"📝 {restaurant['bio']}\n"
            f"📍 {restaurant['address']}\n"
            f"📞 {restaurant['phone']}\n"
            f"⏰ {restaurant['hours']}\n\n"
            f"Buyurtma berish uchun 👇",
            parse_mode='Markdown', reply_markup=main_kb())
        return ConversationHandler.END
    await update.message.reply_text(
        f"👋 *Xush kelibsiz!*\n\n🏪 *{restaurant['name']}*\n\n"
        f"Ro'yxatdan o'tish uchun *ism va familyangizni* kiriting:",
        parse_mode='Markdown')
    return REG_NAME

async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ Ism juda qisqa. Qayta kiriting:")
        return REG_NAME
    context.user_data['reg_name'] = name
    phone_kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Telefon raqamimni ulashish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        f"✅ *{name}*\n\n📞 *Telefon raqamingizni yuboring:*",
        parse_mode='Markdown', reply_markup=phone_kb)
    return REG_PHONE

async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = context.user_data.get('reg_name', update.effective_user.full_name)
    if update.message.contact:
        phone = update.message.contact.phone_number
        if not phone.startswith("+"): phone = "+" + phone
    else:
        phone = update.message.text.strip()
        if not phone.startswith("+998") or len(phone) < 12:
            await update.message.reply_text("❌ O'zbekiston raqami kiriting.\nMisol: +998901234567")
            return REG_PHONE
    users[uid] = {"name": name, "phone": phone,
                  "username": update.effective_user.username or "—",
                  "joined": datetime.now().strftime("%d.%m.%Y %H:%M")}
    await context.bot.send_message(chat_id=ADMIN_ID,
        text=f"🆕 *Yangi mijoz!*\n👤 *{name}*\n📞 {phone}", parse_mode='Markdown')
    await update.message.reply_text(
        f"✅ *Ro'yxatdan o'tdingiz!*\n\n"
        f"🏪 *{restaurant['name']}*\n"
        f"📝 {restaurant['bio']}\n"
        f"📍 {restaurant['address']}\n"
        f"📞 {restaurant['phone']}\n"
        f"⏰ {restaurant['hours']}\n\nBuyurtma berish uchun 👇",
        parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("Menyuni ko'rish:", reply_markup=main_kb())
    return ConversationHandler.END

async def webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users:
        await update.message.reply_text("❌ Avval /start orqali ro'yxatdan o'ting!")
        return
    try:
        payload = json.loads(update.effective_message.web_app_data.data)
        items   = payload['items']
        total   = payload['total']
    except Exception:
        await update.message.reply_text("❌ Xato. Qayta urining.")
        return
    order_cnt[0] += 1
    order_id = f"#{order_cnt[0]:04d}"
    now = datetime.now()
    u   = users[uid]
    order = {"id": order_id, "uid": uid, "name": u['name'], "phone": u['phone'],
             "items": items, "total": total, "status": "new",
             "time": now.strftime("%H:%M"), "date": now.strftime("%d.%m.%Y")}
    orders[order_id] = order
    lines = [f"🎉 *Buyurtma qabul qilindi!*\n🔖 *{order_id}*\n{'─'*24}"]
    for it in items:
        lines.append(f"• {it['name']} × {it['qty']} — {fmt(it['price']*it['qty'])}")
    lines.append(f"\n💰 *Jami: {fmt(total)}*\n⏰ Taxminiy: *30-60 daqiqa*")
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 Kuzatish", callback_data=f"track_{order_id}")]]))
    admin_lines = [f"🆕 *Yangi buyurtma {order_id}!*\n👤 *{u['name']}*\n📞 {u['phone']}\n{'─'*24}"]
    for it in items:
        admin_lines.append(f"• {it['name']} × {it['qty']}")
    admin_lines.append(f"\n💰 *{fmt(total)}* | 🕐 {now.strftime('%H:%M')}")
    await context.bot.send_message(chat_id=ADMIN_ID, text="\n".join(admin_lines), parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Qabul",    callback_data=f"os_{order_id}_accepted"),
             InlineKeyboardButton("❌ Bekor",    callback_data=f"os_{order_id}_cancelled")],
            [InlineKeyboardButton("👨‍🍳 Tayyorlanmoqda", callback_data=f"os_{order_id}_cooking")],
            [InlineKeyboardButton("🛵 Yo'lda",  callback_data=f"os_{order_id}_delivery"),
             InlineKeyboardButton("🎉 Yetkazildi", callback_data=f"os_{order_id}_done")],
        ]))

async def track_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    order_id = "_".join(q.data.split("_")[1:])
    order = orders.get(order_id)
    if not order:
        await q.message.reply_text("❌ Buyurtma topilmadi!"); return
    steps = ["new","accepted","cooking","delivery","done"]
    idx   = steps.index(order['status']) if order['status'] in steps else 0
    bar   = "".join(["🟢" if i<=idx else "⚪" for i in range(len(steps))])
    await q.message.reply_text(
        f"📦 *{order_id}*\n{'─'*24}\n{STATUS.get(order['status'])}\n{bar}\n\n"
        f"🕐 {order['time']} | 💰 *{fmt(order['total'])}*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Yangilash", callback_data=f"track_{order_id}")]]))

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    my  = [o for o in orders.values() if o['uid']==uid]
    if not my:
        await q.message.reply_text("📦 Hali buyurtma yo'q!", reply_markup=main_kb()); return
    kb = [[InlineKeyboardButton(f"{o['id']} — {fmt(o['total'])} — {STATUS.get(o['status'],'')}",
           callback_data=f"track_{o['id']}")] for o in sorted(my, key=lambda x:x['id'], reverse=True)[:5]]
    kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_main")])
    await q.message.reply_text("📦 *Buyurtmalar:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def change_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    parts    = q.data.split("_")
    order_id = parts[1]
    status   = parts[2]
    order    = orders.get(order_id)
    if not order: return
    order['status'] = status
    await q.message.reply_text(f"✅ *{order_id}* → *{STATUS.get(status)}*",
        parse_mode='Markdown', reply_markup=admin_kb())
    msgs = {
        "accepted": f"✅ *{order_id}* qabul qilindi!",
        "cooking":  f"👨‍🍳 *{order_id}* tayyorlanmoqda!",
        "delivery": f"🛵 *{order_id}* yo'lda!",
        "done":     f"🎉 *{order_id}* yetkazildi! Ishtahangizdek bo'lsin!",
        "cancelled":f"❌ *{order_id}* bekor qilindi.",
    }
    if status in msgs:
        await context.bot.send_message(chat_id=order['uid'], text=msgs[status], parse_mode='Markdown')

async def admin_menu_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    kb = [[InlineKeyboardButton("➕ Taom qo'shish", callback_data="add_item")]]
    for item in menu_items:
        kb.append([InlineKeyboardButton(f"🗑 {item['name']} — {fmt(item['price'])}", callback_data=f"del_item_{item['id']}")])
    kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")])
    await q.message.reply_text(
        f"🍽 *Menyu boshqaruv*\n{len(menu_items)} ta taom",
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🍽 *Taom nomini kiriting:*", parse_mode='Markdown')
    return ADMIN_ITEM_NAME

async def add_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['item_name'] = update.message.text.strip()
    await update.message.reply_text("📝 *Tavsifini kiriting:*", parse_mode='Markdown')
    return ADMIN_ITEM_DESC

async def add_item_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['item_desc'] = update.message.text.strip()
    await update.message.reply_text("💰 *Narxini kiriting (so'mda):*\nMisol: `35000`", parse_mode='Markdown')
    return ADMIN_ITEM_PRICE

async def add_item_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['item_price'] = int(update.message.text.strip().replace(" ","").replace(",",""))
    except:
        await update.message.reply_text("❌ Narxni to'g'ri kiriting. Misol: `35000`", parse_mode='Markdown')
        return ADMIN_ITEM_PRICE
    await update.message.reply_text("📂 *Kategoriyasini kiriting:*\nMisol: `Pizzalar`, `Burgerlar`", parse_mode='Markdown')
    return ADMIN_ITEM_CAT

async def add_item_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['item_cat'] = update.message.text.strip()
    await update.message.reply_text("📸 *Rasmini yuboring* yoki /skip deb yozing:", parse_mode='Markdown')
    return ADMIN_ITEM_PHOTO

async def add_item_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_b64 = None
    if update.message.photo:
        f = await update.message.photo[-1].get_file()
        b = await f.download_as_bytearray()
        photo_b64 = base64.b64encode(b).decode()
    item_cnt[0] += 1
    item = {"id": f"i{item_cnt[0]}", "name": context.user_data['item_name'],
            "desc": context.user_data['item_desc'], "price": context.user_data['item_price'],
            "category": context.user_data['item_cat'], "photo": photo_b64}
    menu_items.append(item)
    save_data()
    await update.message.reply_text(
        f"✅ *{item['name']}* qo'shildi!\n💰 {fmt(item['price'])}\n📂 {item['category']}",
        parse_mode='Markdown', reply_markup=admin_kb())
    return ConversationHandler.END

async def del_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    item_id = "_".join(q.data.split("_")[2:])
    global menu_items
    item = next((i for i in menu_items if i['id']==item_id), None)
    if item:
        menu_items[:] = [i for i in menu_items if i['id']!=item_id]
        save_data()
        await q.message.reply_text(f"🗑 *{item['name']}* o'chirildi!", parse_mode='Markdown', reply_markup=admin_kb())
    return ConversationHandler.END

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    await q.message.reply_text(
        f"🏪 *Restoran sozlamalari*\n{'─'*24}\n"
        f"Nom: *{restaurant['name']}*\n"
        f"Bio: {restaurant['bio']}\n"
        f"Manzil: {restaurant['address']}\n"
        f"Tel: {restaurant['phone']}\n"
        f"Vaqt: {restaurant['hours']}\n\n"
        f"O'zgartirish:\n"
        f"`/setname Yangi nom`\n`/setbio Tavsif`\n`/setaddress Manzil`\n`/setphone Telefon`\n`/sethours 10:00-22:00`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]))

async def set_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    parts = update.message.text.split(None, 1)
    if len(parts) < 2:
        await update.message.reply_text("Misol: `/setname Yangi nom`", parse_mode='Markdown'); return
    cmd, val = parts[0][1:], parts[1].strip()
    fields = {"setname":"name","setbio":"bio","setaddress":"address","setphone":"phone","sethours":"hours"}
    if cmd in fields:
        restaurant[fields[cmd]] = val
        save_data()
        await update.message.reply_text(f"✅ Yangilandi: *{val}*", parse_mode='Markdown', reply_markup=admin_kb())

async def admin_orders_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    active = [o for o in orders.values() if o['status'] not in ('done','cancelled')]
    if not active:
        await q.message.reply_text("📋 Faol buyurtmalar yo'q.", reply_markup=admin_kb()); return
    kb = [[InlineKeyboardButton(f"{o['id']} — {o['name']} — {STATUS.get(o['status'],'')}",
           callback_data=f"aorder_{o['id']}")] for o in active]
    kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")])
    await q.message.reply_text(f"📋 *Faol buyurtmalar ({len(active)}):*",
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def admin_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    order_id = "_".join(q.data.split("_")[1:])
    order = orders.get(order_id)
    if not order: return
    lines = [f"📦 *{order_id}*\n👤 *{order['name']}*\n📞 {order['phone']}\n{'─'*24}"]
    for it in order['items']:
        lines.append(f"• {it['name']} × {it['qty']}")
    lines.append(f"\n💰 *{fmt(order['total'])}* | {STATUS.get(order['status'])}")
    await q.message.reply_text("\n".join(lines), parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Qabul",    callback_data=f"os_{order_id}_accepted"),
             InlineKeyboardButton("👨‍🍳 Tayyorlanmoqda", callback_data=f"os_{order_id}_cooking")],
            [InlineKeyboardButton("🛵 Yo'lda",  callback_data=f"os_{order_id}_delivery"),
             InlineKeyboardButton("🎉 Yetkazildi", callback_data=f"os_{order_id}_done")],
            [InlineKeyboardButton("❌ Bekor",   callback_data=f"os_{order_id}_cancelled")],
            [InlineKeyboardButton("🔙 Orqaga",  callback_data="admin_orders")],
        ]))

async def admin_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    total   = len(orders)
    done    = sum(1 for o in orders.values() if o['status']=='done')
    revenue = sum(o['total'] for o in orders.values() if o['status']=='done')
    active  = sum(1 for o in orders.values() if o['status'] not in ('done','cancelled'))
    await q.message.reply_text(
        f"📊 *Statistika*\n{'─'*24}\n"
        f"📦 Jami: *{total}*\n✅ Yetkazildi: *{done}*\n"
        f"🔄 Faol: *{active}*\n💰 Daromad: *{fmt(revenue)}*",
        parse_mode='Markdown', reply_markup=admin_kb())

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id == ADMIN_ID:
        await q.message.reply_text("👨‍💼 *Admin paneli*", parse_mode='Markdown', reply_markup=admin_kb())
    else:
        await q.message.reply_text("🏠 *Bosh menyu*", parse_mode='Markdown', reply_markup=main_kb())

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("👨‍💼 *Admin paneli*", parse_mode='Markdown', reply_markup=admin_kb())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    def run_bot():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        reg_conv = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                REG_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
                REG_PHONE: [MessageHandler(filters.CONTACT, reg_phone),
                            MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
            },
            fallbacks=[CommandHandler("start", start)],
        )
        add_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(add_item_start, pattern="^add_item$")],
            states={
                ADMIN_ITEM_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_name)],
                ADMIN_ITEM_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_desc)],
                ADMIN_ITEM_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_price)],
                ADMIN_ITEM_CAT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_cat)],
                ADMIN_ITEM_PHOTO: [MessageHandler(filters.PHOTO, add_item_photo),
                                   CommandHandler("skip", add_item_photo)],
            },
            fallbacks=[CommandHandler("start", start)],
        )

        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(reg_conv)
        app.add_handler(add_conv)
        app.add_handler(CommandHandler("setname",    set_field))
        app.add_handler(CommandHandler("setbio",     set_field))
        app.add_handler(CommandHandler("setaddress", set_field))
        app.add_handler(CommandHandler("setphone",   set_field))
        app.add_handler(CommandHandler("sethours",   set_field))
        app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data))
        app.add_handler(CallbackQueryHandler(track_order,        pattern="^track_"))
        app.add_handler(CallbackQueryHandler(my_orders,          pattern="^my_orders$"))
        app.add_handler(CallbackQueryHandler(change_status,      pattern="^os_"))
        app.add_handler(CallbackQueryHandler(admin_menu_mgmt,    pattern="^admin_menu_mgmt$"))
        app.add_handler(CallbackQueryHandler(admin_settings,     pattern="^admin_settings$"))
        app.add_handler(CallbackQueryHandler(admin_orders_cb,    pattern="^admin_orders$"))
        app.add_handler(CallbackQueryHandler(admin_order_detail, pattern="^aorder_"))
        app.add_handler(CallbackQueryHandler(admin_stats_cb,     pattern="^admin_stats$"))
        app.add_handler(CallbackQueryHandler(del_item,           pattern="^del_item_"))
        app.add_handler(CallbackQueryHandler(back_main,          pattern="^back_main$"))
        app.add_handler(CallbackQueryHandler(admin_back,         pattern="^admin_back$"))
        print("Restoran boti ishga tushdi!")
        app.run_polling(allowed_updates=["message","callback_query","web_app_data"], stop_signals=[])

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print(f"Flask {port} portda ishga tushdi!")
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)