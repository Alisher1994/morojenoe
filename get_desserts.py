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
            # --- Проверка переменных окружения ---
            if not all([JOWI_LOGIN, JOWI_PASSWORD, BOT_TOKEN]):
                raise ValueError("Не все переменные окружения настроены: JOWI_LOGIN, JOWI_PASSWORD, BOT_TOKEN")

            # --- Шаг 1: Вход в систему ---
            log_steps.append("1. Перехожу на страницу отчета и авторизуюсь...")
            print("Переходим на страницу авторизации...")
            
            await page.goto(COURSES_REPORT_URL, wait_until='networkidle')
            
            # Ждем перенаправления на страницу логина
            try:
                await page.wait_for_url("**/users/sign_in", timeout=30000)
            except:
                print("Не было перенаправления на страницу входа, возможно уже авторизован")
            
            # Проверяем, нужна ли авторизация
            email_field = page.locator('#user_email')
            if await email_field.count() > 0:
                print("Выполняю авторизацию...")
                await email_field.fill(JOWI_LOGIN)
                await page.locator('input[name="user[password]"]').fill(JOWI_PASSWORD)
                
                # Исправленный селектор кнопки входа
                login_button = page.locator('input[type="submit"][value="Войти"], button:has-text("Войти")')
                await login_button.first.click()
                
                # Ждем успешной авторизации
                await page.wait_for_url(COURSES_REPORT_URL, timeout=30000)
                print("Авторизация успешна")
            else:
                print("Авторизация не требуется")

            # --- Шаг 2: Применение фильтров ---
            log_steps.append("2. Применяю фильтры 'Вчера' и 'Десерты'...")
            
            # Ждем полной загрузки страницы
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(2000)
            
            # Выбираем дату в календаре вручную
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            yesterday_day_str = str(yesterday.day)
            
            print(f"Устанавливаю дату: {yesterday.strftime('%d.%m.%Y')}")
            
            # Поле "От"
            from_field = page.get_by_role('textbox', name='От:')
            if await from_field.count() == 0:
                from_field = page.locator('input[placeholder*="От"], input[name*="from"], input[id*="from"]')
            
            await from_field.first.click()
            await page.wait_for_timeout(1000)
            
            # Выбираем день в календаре
            day_cell = page.get_by_role('cell', name=yesterday_day_str, exact=True)
            if await day_cell.count() > 0:
                await day_cell.first.click()
            else:
                print(f"Не найдена ячейка с днем {yesterday_day_str}")
            
            print(f"  - Выбрана дата 'От': {yesterday.strftime('%d.%m.%Y')}")

            # Поле "До"
            to_field = page.get_by_role('textbox', name='До:')
            if await to_field.count() == 0:
                to_field = page.locator('input[placeholder*="До"], input[name*="to"], input[id*="to"]')
                
            await to_field.first.click()
            await page.wait_for_timeout(1000)
            
            day_cell = page.get_by_role('cell', name=yesterday_day_str, exact=True)
            if await day_cell.count() > 0:
                await day_cell.first.click()
            else:
                print(f"Не найдена ячейка с днем {yesterday_day_str}")
                
            print(f"  - Выбрана дата 'До': {yesterday.strftime('%d.%m.%Y')}")

            # Выбираем категорию
            category_field = page.get_by_role('textbox', name='Категории')
            if await category_field.count() == 0:
                category_field = page.locator('input[placeholder*="Категори"], input[name*="categor"]')
            
            await category_field.first.click()
            await page.wait_for_timeout(2000)
            
            # Ищем опцию "Десерты"
            dessert_option = page.locator('.ui-menu-item-wrapper:has-text("Десерты"), .option:has-text("Десерты"), li:has-text("Десерты")')
            if await dessert_option.count() > 0:
                await dessert_option.first.click()
                print("  - Категория 'Десерты' выбрана.")
            else:
                print("  - Опция 'Десерты' не найдена")

            # Нажимаем поиск
            search_button = page.get_by_role('button', name='Начать поиск')
            if await search_button.count() == 0:
                search_button = page.locator('button:has-text("Поиск"), input[type="submit"]')
            
            # Ждем ответ от сервера
            try:
                async with page.expect_response(lambda r: "courses_report" in r.url and r.status == 200, timeout=60000) as response_info:
                    await search_button.first.click()
                await response_info.value
                print("Фильтры применены, данные загружены.")
            except:
                print("Не дождались ответа от сервера, продолжаем...")
                await page.wait_for_timeout(5000)

            # --- Шаг 3: Сбор данных из таблицы ---
            log_steps.append("3. Собираю данные из таблицы...")
            
            # Ждем появления таблицы
            await page.wait_for_timeout(3000)
            
            for item_name in ITEMS_TO_FIND:
                print(f"Ищу товар: {item_name}")
                
                # Различные варианты поиска строки в таблице
                row_selectors = [
                    f'tr:has-text("{item_name}")',
                    f'tr td:has-text("{item_name}")',
                    f'tbody tr:has-text("{item_name}")'
                ]
                
                row = None
                for selector in row_selectors:
                    row = page.locator(selector)
                    if await row.count() > 0:
                        break
                
                if row and await row.count() > 0:
                    try:
                        # Пробуем разные варианты получения количества
                        quantity_cell = row.locator("td").nth(2)
                        if await quantity_cell.count() == 0:
                            quantity_cell = row.locator("td").nth(1)
                        
                        quantity_text = await quantity_cell.inner_text()
                        # Извлекаем только числа
                        import re
                        numbers = re.findall(r'\d+', quantity_text)
                        if numbers:
                            results[item_name] = int(numbers[0])
                            print(f"  - Найдено '{item_name}': {results[item_name]} шт.")
                        else:
                            print(f"  - Не удалось извлечь количество для '{item_name}': {quantity_text}")
                    except Exception as e:
                        print(f"  - Ошибка при получении количества для '{item_name}': {e}")
                else:
                    print(f"  - Товар '{item_name}' не найден в отчете (количество 0).")

            # --- Шаг 4: Формирование и отправка отчета ---
            log_steps.append("4. Формирую и отправляю отчет...")
            yesterday_str = yesterday.strftime('%d.%m.%Y')
            report_lines = [f"<b>Отчет по десертам (Tandoor) за {yesterday_str}</b>", ""]
            for name, qty in results.items():
                report_lines.append(f"<b>{name}:</b> {qty} шт.")
            
            await send_report("\n".join(report_lines))
            print("Отчет успешно отправлен!")

        except Exception as e:
            # --- Обработка любой ошибки ---
            print(f"Произошла критическая ошибка: {e}")
            await page.screenshot(path=screenshot_path, full_page=True)
            error_trace = traceback.format_exc()
            
            current_step = log_steps[-1] if log_steps else "Неизвестный шаг"
            
            error_details = (
                f"<b>Критическая ошибка при получении отчета по десертам</b>\n\n"
                f"❌ <b>Сбой на шаге:</b>\n<code>{current_step}</code>\n\n"
                f"🔍 <b>Ошибка:</b>\n<code>{str(e)}</code>\n\n"
                f"📄 <b>Технические детали:</b>\n<pre>{error_trace.splitlines()[-1] if error_trace.splitlines() else 'Нет деталей'}</pre>"
            )
            await send_report(error_details, photo_path=screenshot_path)
        
        finally:
            await browser.close()
            print("\nРабота завершена.")

if __name__ == "__main__":
    asyncio.run(main())
