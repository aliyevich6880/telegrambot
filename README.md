# So'z o'yini Telegram boti

Oddiy guruh o'yini uchun Telegram bot. Qo'llanma (o'zbekcha):

- /host — guruhda buyrug'ini yuborib boshlovchi bo'ling.
- /category <nom> — boshlovchi toifani o'rnatadi (masalan: film, hayvon).
- Boshlovchi shaxsiy chatda botga /setword <so'z> yuboradi (so'z maxfiy qoladi).
- Guruhda boshlovchi maqsadli foydalanuvchining xabariga javoban /reveal buyrug'ini yuboradi — bot shu foydalanuvchiga shaxsiy xabarda so'zni yuboradi.
- Foydalanuvchilar guruhda so'zni topishga harakat qiladi; kim to'g'ri topsa, bot e'lon qiladi va raund tugaydi.
- /cancel — boshlovchi raundni bekor qiladi.

Qanday ishlatish:

1. Botni guruhga qo'shing.
2. Har bir ishtirokchi bot bilan shaxsiy chatni boshlashi kerak (aksi holda bot ularga shaxsiy xabar yubora olmaydi).
3. Guruhda /host bosing, keyin /category ni belgilang.
4. Boshlovchi shaxsiy chatda /setword yuboradi.
5. Boshlovchi guruhda maqsadli foydalanuvchining xabariga javoban /reveal yuboradi.

O'rnatish (mahalliy):

1. Python 3.8+.
2. Virtual muhit yaratish va quyidagilarni o'rnatish:

```bash
pip install -r requirements.txt
```

3. `.env` faylida `BOT_TOKEN` ni qo'ying.

4. Botni ishga tushiring:

```bash
python bot.py
```

Yangi komandalar (so'zlarni boshqarish):

- `/addword <so'z>` — (guruhda, faqat boshlovchi) so'zni saqlaydi.
- `/listwords` — (guruhda, faqat boshlovchi) guruh uchun saqlangan so'zlarni ko'rsatadi (id bilan).
- `/removeword <id>` — (guruhda, faqat boshlovchi) ko'rsatilgan id dagi so'zni o'chiradi.
- `/useword <id>` — (shaxsiyda, boshlovchi) saqlangan so'zni tanlab joriy raundga o'rnatadi.

Eslatma: saqlangan so'zlar `words.db` (SQLite) faylida saqlanadi.
