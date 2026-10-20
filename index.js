const { Telegraf } = require('telegraf');
const axios = require('axios');
const cheerio = require('cheerio');
const { URL } = require('url');
const express = require('express');

// Render uchun veb-server (port ochish uchun)
const app = express();
const PORT = process.env.PORT || 3000;

app.get('/', (req, res) => {
    send('Bot ishlamoqda!');
});

app.listen(PORT, () => {
    console.log(`Server ${PORT}-portda ishga tushdi.`);
});

// Bot tokeni Render Environment Variables'dan olinadi
const token = process.env.BOT_TOKEN;
if (!token) {
    throw new Error('BOT_TOKEN muhit o‘zgaruvchisi topilmadi!');
}

const bot = new Telegraf(token);

// /start buyrug'i
bot.start((ctx) => {
    ctx.reply("Salom! 👋\n\nMenga istalgan veb-sayt havolasini yuboring, men o'sha sahidadagi barcha rasmlarni topib sizga yuboraman.");
});

// Havolalarni qabul qilish va rasmlarni yig'ish
bot.on('text', async (ctx) => {
    const urlText = ctx.message.text.trim();

    if (!urlText.startsWith('http://') && !urlText.startsWith('https://')) {
        return ctx.reply("❌ Iltimos, to'g'ri havola (URL) yuboring (masalan: https://example.com)");
    }

    const processingMsg = await ctx.reply("⏳ Havola tekshirilmoqda va rasmlar qidirilmoqda...");

    try {
        const response = await axios.get(urlText, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
            timeout: 15000
        });

        const $ = cheerio.load(response.data);
        const imageUrls = new Set();

        $('img').each((_, element) => {
            const imgSrc = $(element).attr('src') || $(element).attr('data-src') \vert{}\vert{}$(element).attr('data-lazy-src');
            if (imgSrc) {
                try {
                    const fullUrl = new URL(imgSrc, urlText).href;
                    if (fullUrl.startswith('http://') || fullUrl.startswith('https://')) {
                        imageUrls.add(fullUrl);
                    }
                } catch (e) {
                    // Yaroqsiz havolalarni o'tkazib yuborish
                }
            }
        });

        const imagesArray = Array.from(imageUrls);

        if (imagesArray.length === 0) {
            return ctx.telegram.editMessageText(
                ctx.chat.id, 
                processingMsg.message_id, 
                undefined, 
                "❌ Bu havoladan hech qanday rasm topilmadi."
            );
        }

        await ctx.telegram.editMessageText(
            ctx.chat.id, 
            processing_msg.message_id, 
            undefined, 
            `✅ Topildi: ${imagesArray.length} ta rasm. Ularni yuborishni boshlayman...`
        );

        let sentCount = 0;
        // Telegram limiti va bloklanishining oldini olish uchun cheklaymiz va tanaffus qilamiz
        for (const imgUrl of imagesArray.slice(0, 20)) {
            try {
                await ctx.replyWithPhoto(imgUrl);
                sentCount++;
                // Har bir rasm orasida 1 soniya kutish (Telegram chekloviga tushmaslik uchun)
                await new Promise(resolve => setTimeout(resolve, 1000));
            } catch (err) {
                continue;
            }
        }

        await ctx.reply(`🎉 Jami ${sentCount} ta rasm muvaffaqiyatli yuborildi!`);

    } catch (error) {
        await ctx.telegram.editMessageText(
            ctx.chat.id, 
            processing_msg.message_id, 
            undefined, 
            `❌ Xatolik yuz berdi: ${error.message}`
        );
    }
});

// Botni ishga tushirish
bot.launch();
console.log("Bot ishga tushdi...");

// Dastur to'xtaganda xavfsiz yopish
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
