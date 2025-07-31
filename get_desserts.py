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
            
            # Сохраняем старые данные таблицы для сравнения
            old_table_content = ""
            try:
                table = page.locator('table, .table, tbody')
                if await table.count() > 0:
                    old_table_content = await table.first.inner_text()
            except:
                pass
            
            print("Нажимаю кнопку 'Начать поиск'...")
            await search_button.first.click()
            
            # Ждем обновления таблицы - несколько способов
            table_updated = False
            max_attempts = 20  # 20 секунд максимум
            
            for attempt in range(max_attempts):
                await page.wait_for_timeout(1000)
                
                try:
                    # Способ 1: Ждем сетевой запрос
                    if not table_updated:
                        try:
                            await page.wait_for_response(
                                lambda r: "courses_report" in r.url and r.status == 200, 
                                timeout=2000
                            )
                            table_updated = True
                            print(f"Получен ответ от сервера на попытке {attempt + 1}")
                            break
                        except:
                            pass
                    
                    # Способ 2: Проверяем изменение содержимого таблицы
                    table = page.locator('table, .table, tbody')
                    if await table.count() > 0:
                        current_table_content = await table.first.inner_text()
                        if current_table_content != old_table_content and current_table_content.strip():
                            table_updated = True
                            print(f"Таблица обновилась на попытке {attempt + 1}")
                            break
                    
                    # Способ 3: Проверяем индикатор загрузки
                    loading_indicator = page.locator('.loading, .spinner, [data-loading="true"]')
                    if await loading_indicator.count() == 0:
                        # Если нет индикатора загрузки, даем дополнительное время
                        if attempt > 5:  # После 5 секунд
                            table_updated = True
                            print(f"Нет индикатора загрузки, считаем что данные загружены на попытке {attempt + 1}")
                            break
                            
                except Exception as e:
                    print(f"Ошибка при проверке обновления таблицы: {e}")
                    continue
            
            if not table_updated:
                print("Таблица может быть не обновилась, но продолжаем...")
            
            # Дополнительная пауза для стабильности
            await page.wait_for_timeout(3000)
            print("Данные должны быть загружены, начинаю сбор информации.")

            # --- Шаг 3: ИСПРАВЛЕННЫЙ сбор данных из таблицы ---
            log_steps.append("3. Собираю данные из таблицы...")
            
            # Импортируем regex для работы с числами
            import re
            
            # Ищем основную таблицу с данными
            main_table = page.locator('table.main_table, table.data_table, #courses')
            if await main_table.count() == 0:
                main_table = page.locator('table')
            
            if await main_table.count() > 0:
                print("Найдена основная таблица с данными")
                
                # ИСПРАВЛЕНИЕ: Получаем все строки из tbody без использования filter с lambda
                tbody = main_table.locator('tbody')
                all_rows = tbody.locator('tr')
                
                row_count = await all_rows.count()
                print(f"Всего найдено строк: {row_count}")
                
                # Отфильтровываем строки заголовков вручную
                data_rows = []
                for i in range(row_count):
                    row = all_rows.nth(i)
                    row_class = await row.get_attribute('class')
                    
                    # Пропускаем строки с классом table_top (заголовки)
                    if row_class and 'table_top' in row_class:
                        continue
                    
                    data_rows.append(row)
                
                print(f"Найдено строк с данными: {len(data_rows)}")
                
                for item_name in ITEMS_TO_FIND:
                    print(f"\nИщу товар: {item_name}")
                    found = False
                    
                    for i, row in enumerate(data_rows):
                        # Получаем все ячейки в строке
                        cells = row.locator('td')
                        cell_count = await cells.count()
                        
                        if cell_count >= 3:  # Минимум должно быть 3 ячейки (№, Название, Количество)
                            # Вторая ячейка - название товара
                            name_cell = cells.nth(1)
                            name_text = await name_cell.inner_text()
                            
                            if item_name in name_text.strip():
                                print(f"  ✓ Найден товар в строке {i+1}: {name_text.strip()}")
                                
                                # Третья ячейка - количество
                                qty_cell = cells.nth(2)
                                qty_text = await qty_cell.inner_text()
                                
                                print(f"  - Текст ячейки с количеством: '{qty_text.strip()}'")
                                
                                # Извлекаем число из ячейки количества
                                qty_numbers = re.findall(r'\d+', qty_text.strip())
                                if qty_numbers:
                                    results[item_name] = int(qty_numbers[0])
                                    print(f"  ✓ '{item_name}': {results[item_name]} шт.")
                                else:
                                    print(f"  ⚠️ Не удалось извлечь число из '{qty_text}'")
                                
                                found = True
                                break
                    
                    if not found:
                        print(f"  ❌ Товар '{item_name}' не найден в таблице")
                        
            else:
                print("❌ Основная таблица не найдена!")
                # Выводим всю страницу для отладки
                page_content = await page.content()
                print("Содержимое страницы (первые 1000 символов):")
                print(page_content[:1000])

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
