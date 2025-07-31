import os
import asyncio
import traceback
import datetime
import re
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

async def wait_for_table_update(page, old_content, max_wait=30):
    """Ждет обновления таблицы после применения фильтров."""
    print("Ожидаю обновления таблицы...")
    
    for i in range(max_wait):
        await page.wait_for_timeout(1000)
        
        # Проверяем наличие индикатора загрузки
        loader = page.locator('.h_loader, .loader, .loading')
        if await loader.count() > 0:
            is_visible = await loader.is_visible()
            if is_visible:
                print(f"  Обнаружен индикатор загрузки (попытка {i+1})")
                # Ждем пока индикатор исчезнет
                try:
                    await loader.wait_for(state="hidden", timeout=5000)
                    print("  Индикатор загрузки исчез")
                except:
                    pass
        
        # Проверяем изменение содержимого таблицы
        try:
            current_content = await page.locator('#courses tbody').inner_html()
            if current_content != old_content and len(current_content) > 100:
                print(f"Таблица обновилась (попытка {i+1})")
                # Дополнительная пауза для стабильности
                await page.wait_for_timeout(2000)
                return True
        except:
            pass
    
    return False

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
                
                login_button = page.locator('input[type="submit"][value="Войти"], button:has-text("Войти")')
                await login_button.first.click()
                
                await page.wait_for_url(COURSES_REPORT_URL, timeout=30000)
                print("Авторизация успешна")
            else:
                print("Авторизация не требуется")

            # --- Шаг 2: Применение фильтров ---
            log_steps.append("2. Применяю фильтры 'Вчера' и 'Десерты'...")
            
            # Ждем полной загрузки страницы
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(3000)
            
            # Сохраняем текущее состояние таблицы
            old_table_content = ""
            try:
                old_table_content = await page.locator('#courses tbody').inner_html()
            except:
                pass
            
            # Выбираем "Вчера" из выпадающего списка
            print("Выбираю период 'Вчера'...")
            standart_date_select = page.locator('#standatr_date')
            await standart_date_select.select_option('2')  # 2 = Вчера
            
            # Ждем обновления дат в полях
            await page.wait_for_timeout(2000)
            
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            print(f"Установлена дата: {yesterday.strftime('%d.%m.%Y')}")
            
            # Выбираем категорию "Десерты"
            print("Выбираю категорию 'Десерты'...")
            category_field = page.locator('#crep_cat_search')
            await category_field.click()
            await page.wait_for_timeout(1000)
            
            # Ищем и кликаем на "Десерты" в выпадающем списке
            dessert_option = page.locator('.ui-menu-item:has-text("Десерты")')
            if await dessert_option.count() > 0:
                await dessert_option.first.click()
                print("  - Категория 'Десерты' выбрана.")
            else:
                # Альтернативный способ
                await category_field.fill("Десерты")
                await page.wait_for_timeout(1000)
                await page.keyboard.press('Enter')
            
            # Нажимаем кнопку поиска
            print("Нажимаю кнопку 'Начать поиск'...")
            search_button = page.locator('button[name="commit"]:has-text("Начать поиск")')
            await search_button.click()
            
            # Ждем обновления таблицы
            table_updated = await wait_for_table_update(page, old_table_content)
            
            if not table_updated:
                print("Предупреждение: таблица может не обновиться полностью")
            
            # --- Шаг 3: Сбор данных из таблицы ---
            log_steps.append("3. Собираю данные из таблицы...")
            print("\nНачинаю сбор данных из таблицы...")
            
            # Делаем скриншот для отладки
            await page.screenshot(path="debug_table.png", full_page=False)
            
            # Ищем таблицу с id="courses"
            table_selector = '#courses tbody tr'
            rows = page.locator(table_selector)
            row_count = await rows.count()
            
            print(f"Всего найдено строк в таблице: {row_count}")
            
            # Проходим по каждой строке
            for i in range(row_count):
                row = rows.nth(i)
                
                # Проверяем класс строки - пропускаем строки с классом "table_top"
                row_class = await row.get_attribute('class') or ""
                if 'table_top' in row_class:
                    continue
                
                # Получаем все ячейки в строке
                cells = row.locator('td')
                cell_count = await cells.count()
                
                if cell_count >= 3:
                    # Индексы ячеек в таблице:
                    # 0 - № (номер)
                    # 1 - Наименование
                    # 2 - Кол-во
                    # 3 - Средняя цена (отпускная)
                    # 4 - Сумма (отпускная)
                    # и т.д.
                    
                    try:
                        # Читаем название из второй ячейки (индекс 1)
                        name_text = await cells.nth(1).inner_text()
                        name_text = name_text.strip()
                        
                        # Читаем количество из третьей ячейки (индекс 2)
                        qty_text = await cells.nth(2).inner_text()
                        qty_text = qty_text.strip()
                        
                        print(f"\nСтрока {i+1}:")
                        print(f"  Название: '{name_text}'")
                        print(f"  Количество (текст): '{qty_text}'")
                        
                        # Проверяем, является ли это одним из искомых товаров
                        for item_name in ITEMS_TO_FIND:
                            if item_name in name_text:
                                print(f"  ✓ Найден товар: {item_name}")
                                
                                # Извлекаем число из текста количества
                                try:
                                    # Пробуем преобразовать напрямую
                                    qty = int(qty_text)
                                    results[item_name] = qty
                                    print(f"  ✓ Количество: {qty}")
                                except ValueError:
                                    # Если не получилось, ищем числа в тексте
                                    numbers = re.findall(r'\d+', qty_text)
                                    if numbers:
                                        qty = int(numbers[0])
                                        results[item_name] = qty
                                        print(f"  ✓ Количество (извлечено): {qty}")
                                    else:
                                        print(f"  ❌ Не удалось извлечь количество из '{qty_text}'")
                                break
                        
                    except Exception as e:
                        print(f"  Ошибка при обработке строки {i+1}: {e}")
                        continue
            
            print(f"\n=== Итоговые результаты ===")
            for item, qty in results.items():
                print(f"{item}: {qty} шт.")

            # --- Шаг 4: Формирование и отправка отчета ---
            log_steps.append("4. Формирую и отправляю отчет...")
            yesterday_str = yesterday.strftime('%d.%m.%Y')
            report_lines = [f"<b>Отчет по десертам (Tandoor) за {yesterday_str}</b>", ""]
            
            total_items = 0
            for name, qty in results.items():
                report_lines.append(f"<b>{name}:</b> {qty} шт.")
                total_items += qty
            
            report_lines.append("")
            report_lines.append(f"<b>Всего десертов:</b> {total_items} шт.")
            
            await send_report("\n".join(report_lines))
            print("\nОтчет успешно отправлен!")

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
