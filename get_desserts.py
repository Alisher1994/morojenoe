import os
import asyncio
import traceback
import datetime
from playwright.async_api import async_playwright
from telegram import Bot
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# --- Конфигурация ---
JOWI_LOGIN = os.getenv("JOWI_LOGIN")
JOWI_PASSWORD = os.getenv("JOWI_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = "-4820879112"
MAX_TIMEOUT = 120000  # 2 минуты

# URL отчета и товары, которые мы ищем
COURSES_REPORT_URL = "https://app.jowi.club/ru/restaurants/ef62ef82-e7a3-4909-bb8b-906257ebd17c/courses_report"
ITEMS_TO_FIND = ["Морожний шарик (1шт)", "Пироженное"]

# --- Функции ---

async def send_report(message: str, photo_path: str = None):
    """Отправляет отчет в Telegram."""
    if not all([BOT_TOKEN, GROUP_ID]):
        print("Ошибка: Переменные Telegram не настроены.")
        return
    try:
        bot = Bot(token=BOT_TOKEN)
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo_file:
                await bot.send_photo(chat_id=GROUP_ID, photo=photo_file, caption=message, parse_mode='HTML')
            os.remove(photo_path)
        else:
            await bot.send_message(chat_id=GROUP_ID, text=message, parse_mode='HTML')
        print("Отчет успешно отправлен в Telegram.")
    except Exception as e:
        print(f"Ошибка при отправке в Telegram: {e}")

async def main():
    """Основной цикл скрипта."""
    results = {item: 0 for item in ITEMS_TO_FIND}
    log_steps = []
    screenshot_path = "dessert_report_error.png"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(MAX_TIMEOUT)

        try:
            # --- Шаг 1: Вход в систему ---
            log_steps.append("1. Перехожу на страницу отчета и авторизуюсь...")
            await page.goto(COURSES_REPORT_URL)
            await page.wait_for_url("**/users/sign_in")
            await page.locator('#user_email').fill(JOWI_LOGIN)
            await page.locator('input[name="user[password]"]').fill(JOWI_PASSWORD)
            await page.locator('button:has-text("Войти")').first.click()
            await page.wait_for_url(COURSES_REPORT_URL)
            print("Вход выполнен, нахожусь на странице отчета по блюдам.")

            # --- Шаг 2: Применение фильтров ---
            log_steps.append("2. Применяю фильтры 'Вчера' и 'Десерты'...")
            
            # Начинаем ждать ответ от сервера ДО применения всех фильтров
            async with page.expect_response(lambda r: "courses_report" in r.url and r.status == 200) as response_info:
                # Выбираем "Вчера"
                await page.locator('#standatr_date').select_option("2")
                # Выбираем категорию "Десерты"
                await page.get_by_role('textbox', name='Категории').click()
                await page.locator('.ui-menu-item-wrapper:has-text("Десерты")').click()
                # Нажимаем поиск
                await page.get_by_role('button', name='Начать поиск').click()
            
            # Ждем завершения сетевого запроса, который был вызван поиском
            await response_info.value
            print("Фильтры применены, данные загружены.")

            # --- Шаг 3: Сбор данных из таблицы ---
            log_steps.append("3. Собираю данные из таблицы...")
            
            for item_name in ITEMS_TO_FIND:
                # Ищем строку таблицы, содержащую название нашего товара
                row = page.locator(f'tr:has-text("{item_name}")')
                
                if await row.count() > 0:
                    # Если строка найдена, берем текст из 3-й ячейки (Кол-во)
                    quantity_text = await row.locator("td").nth(2).inner_text()
                    results[item_name] = int(quantity_text)
                    print(f"  - Найдено '{item_name}': {quantity_text} шт.")
                else:
                    print(f"  - Товар '{item_name}' не найден в отчете (количество 0).")

            # --- Шаг 4: Формирование и отправка отчета ---
            yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%d.%m.%Y')
            report_lines = [
                f"<b>Отчет по десертам (Tandoor) за {yesterday_str}</b>",
                ""
            ]
            for name, qty in results.items():
                report_lines.append(f"<b>{name}:</b> {qty} шт.")
            
            await send_report("\n".join(report_lines))

        except Exception:
            # --- Обработка любой ошибки ---
            print("Произошла критическая ошибка!")
            await page.screenshot(path=screenshot_path)
            error_trace = traceback.format_exc()
            error_details = (
                f"<b>Критическая ошибка при получении отчета по десертам</b>\n\n"
                f"❌ <b>Сбой на шаге:</b>\n<code>{log_steps[-1]}</code>\n\n"
                f"📄 <b>Технические детали:</b>\n<pre>{error_trace.splitlines()[-1]}</pre>"
            )
            await send_report(error_details, photo_path=screenshot_path)
        
        finally:
            await browser.close()
            print("\nРабота завершена.")

if __name__ == "__main__":
    asyncio.run(main())
