
import os
import warnings
warnings.filterwarnings("ignore")

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import yfinance as yf
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
import asyncio

TOKEN = os.getenv("TELEGRAM_TOKEN", "7595299972:AAHe8kB0YSHl5e6AkJ_jYdcC5lf4Eu5rFv8")
TIMEZONE = pytz.timezone('America/Sao_Paulo')

app = Flask(__name__)

ACOES_B3 = ["PETR4", "VALE3", "ITUB4", "BBDC4", "JBSS3"]
FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Money Times": "https://www.moneytimes.com.br/ultimas-noticias/"
}

class AnalisadorMercado:
    def __init__(self):
        self.sentiment_pipeline = pipeline(
            "text-classification",
            model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
            device=-1
        )

    async def buscar_noticias(self):
        oportunidades = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(response.text, 'html.parser')
                noticias = soup.find_all('a', href=True)[:15]
                for noticia in noticias:
                    titulo = noticia.get_text(strip=True)
                    link = noticia['href']
                    for acao in ACOES_B3:
                        if acao.lower() in titulo.lower():
                            oportunidades.append({
                                'acao': acao,
                                'titulo': titulo,
                                'link': link if link.startswith('http') else f"{url}{link}",
                                'fonte': site,
                                'timestamp': datetime.now(TIMEZONE)
                            })
                            break
            except:
                continue
        return oportunidades

    async def analisar_noticia(self, noticia):
        try:
            analise = self.sentiment_pipeline(noticia['titulo'])[0]
            impacto = "alta" if analise['label'] == "POSITIVE" else "baixa"
            return {
                'impacto': impacto,
                'confianca': analise['score']
            }
        except:
            return {'impacto': 'neutro', 'confianca': 0.5}

analisador = AnalisadorMercado()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ RadarB3 Ativo!\nEnvie o código de uma ação como: PETR4")

async def handle_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.upper().strip()
    if texto not in ACOES_B3:
        await update.message.reply_text("❌ Ação não encontrada.")
        return
    try:
        ticker = yf.Ticker(f"{texto}.SA")
        hist = ticker.history(period="1d")
        preco = hist['Close'].iloc[-1]
        noticias = await analisador.buscar_noticias()
        noticias_acao = [n for n in noticias if n['acao'] == texto][:3]
        msg = f"📊 {texto} - R$ {preco:.2f}\n\n"
        for noticia in noticias_acao:
            analise = await analisador.analisar_noticia(noticia)
            msg += (
                f"▪️ {noticia['fonte']}: {noticia['titulo']}\n"
                f"→ Impacto: {analise['impacto'].upper()} "
                f"(Confiança: {analise['confianca']*100:.0f}%)\n\n"
            )
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro: {str(e)}")

@app.route('/')
def index():
    return "RadarB3 está rodando!"

def main():
    import asyncio
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    app_telegram = ApplicationBuilder().token(TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_acao))
    loop = asyncio.get_event_loop()
    loop.create_task(app_telegram.initialize())
    loop.create_task(app_telegram.start())
    loop.create_task(app_telegram.updater.start_polling())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()
