# -*- coding: utf-8 -*-
"""
Парсер отзывов из App Store - Streamlit Web App
Запуск: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime
import time
import csv
from collections import Counter
import io
import base64

# ==================== НАСТРОЙКИ СТРАНИЦЫ ====================
st.set_page_config(
    page_title="Парсер отзывов App Store",
    page_icon="📱",
    layout="wide"
)

# ==================== ЗАГОЛОВОК ====================
st.title("📱 Парсер отзывов App Store")
st.markdown("---")

# ==================== БОКОВАЯ ПАНЕЛЬ ====================
with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Ссылка на приложение
    app_url = st.text_input(
        "🔗 Ссылка на приложение",
        value="https://apps.apple.com/ru/app/duolingo-%D1%8F%D0%B7%D1%8B%D0%BA%D0%B8-%D0%B8-%D1%88%D0%B0%D1%85%D0%BC%D0%B0%D1%82%D1%8B/id570060128",
        help="Вставьте ссылку на приложение из App Store"
    )
    
    st.markdown("---")
    
    # Период фильтрации
    st.subheader("📅 Период фильтрации")
    date_from = st.date_input(
        "Дата от",
        value=datetime(2026, 1, 31)
    )
    date_to = st.date_input(
        "Дата до",
        value=datetime(2026, 6, 15)
    )
    
    # Время
    col1, col2 = st.columns(2)
    with col1:
        time_from = st.time_input("Время от", value=datetime.strptime("00:00", "%H:%M").time())
    with col2:
        time_to = st.time_input("Время до", value=datetime.strptime("15:43", "%H:%M").time())
    
    st.markdown("---")
    
    # Сортировка
    sort_order = st.selectbox(
        "📊 Сортировка по оценке",
        options=["По убыванию (5→1)", "По возрастанию (1→5)"],
        index=0
    )
    
    # Количество отзывов
    max_reviews = st.slider(
        "📥 Максимум отзывов",
        min_value=100,
        max_value=5000,
        value=5000,
        step=100
    )
    
    # Кнопка запуска
    st.markdown("---")
    start_button = st.button(
        "🚀 Начать парсинг",
        type="primary",
        use_container_width=True
    )

# ==================== ФУНКЦИИ ПАРСИНГА ====================
def extract_app_info(url):
    """Извлекает ID и страну из URL"""
    id_match = re.search(r'/id(\d+)', url)
    if not id_match:
        raise ValueError("Не найден ID приложения")
    app_id = id_match.group(1)
    
    country_match = re.search(r'apps\.apple\.com/([a-z]{2})/', url)
    country = country_match.group(1) if country_match else 'ru'
    
    name_match = re.search(r'/app/([^/]+)/', url)
    app_name = name_match.group(1) if name_match else 'app'
    app_name = re.sub(r'[^a-zA-Z0-9_]', '_', app_name)
    
    return country, app_id, app_name

def fetch_reviews(app_id, country='ru', max_reviews=5000, progress_callback=None):
    """Собирает отзывы через iTunes API"""
    all_reviews = []
    url = f"https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/json"
    
    try:
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        
        if 'feed' not in data or 'entry' not in data['feed']:
            return []
        
        entries = data['feed']['entry']
        total = len(entries) - 1
        
        for i, entry in enumerate(entries[1:], 1):
            review = parse_review_entry(entry)
            if review:
                all_reviews.append(review)
            
            if progress_callback and total > 0:
                progress_callback(i / total)
            
            if len(all_reviews) >= max_reviews:
                break
        
        return all_reviews
        
    except Exception as e:
        st.error(f"Ошибка при сборе отзывов: {e}")
        return []

def parse_review_entry(entry):
    """Парсит один отзыв из JSON"""
    try:
        date_str = entry.get('updated', {}).get('label', '')
        if date_str:
            try:
                review_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
                review_date = review_date.replace(tzinfo=None)
            except:
                review_date = datetime.now()
        else:
            review_date = datetime.now()
        
        rating = 0
        if 'im:rating' in entry:
            try:
                rating = int(entry['im:rating']['label'])
            except:
                rating = 0
        
        title = entry.get('title', {}).get('label', '')
        
        content = ''
        if 'content' in entry:
            content = entry['content'].get('label', '')
        if not content and 'summary' in entry:
            content = entry.get('summary', {}).get('label', '')
        
        author = ''
        if 'author' in entry and 'name' in entry['author']:
            author = entry['author']['name'].get('label', '')
        
        return {
            'date': review_date,
            'rating': rating,
            'title': title,
            'review': content,
            'userName': author
        }
    except:
        return None

def is_russian(text):
    """Проверяет наличие русских символов"""
    if not text or len(text.strip()) == 0:
        return False
    text = text.strip()
    russian_chars = sum(1 for c in text if 'а' <= c.lower() <= 'я' or c == 'ё')
    if len(text) < 10:
        return russian_chars > 0
    else:
        return russian_chars / len(text) > 0.15

def filter_by_language(reviews):
    """Оставляет только русские отзывы"""
    filtered = []
    for review in reviews:
        text = review.get('review', '')
        title = review.get('title', '')
        author = review.get('userName', '')
        if is_russian(text) or is_russian(title) or is_russian(author):
            filtered.append(review)
    return filtered

def clean_text(text):
    """Очищает текст от эмодзи"""
    if not text:
        return ''
    cleaned = re.sub(r'[^\w\s\.,!?\-:;()"\'"«»…—]', ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

# ==================== ОСНОВНАЯ ЛОГИКА ====================
if start_button:
    try:
        # Создаем прогресс-бар
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 1. Извлекаем информацию
        status_text.text("📌 Извлечение информации из ссылки...")
        country, app_id, app_name = extract_app_info(app_url)
        
        # 2. Собираем отзывы
        status_text.text(f"🔄 Сбор отзывов для ID: {app_id}...")
        
        def update_progress(progress):
            progress_bar.progress(progress)
        
        all_reviews = fetch_reviews(
            app_id, 
            country, 
            max_reviews,
            update_progress
        )
        
        total = len(all_reviews)
        
        if total == 0:
            st.warning("❌ Отзывы не найдены")
            st.stop()
        
        # 3. Формируем даты
        date_from_dt = datetime.combine(date_from, time_from)
        date_to_dt = datetime.combine(date_to, time_to)
        
        # 4. Фильтруем по дате
        status_text.text("📅 Фильтрация по дате...")
        date_filtered = []
        for review in all_reviews:
            review_date = review.get('date')
            if review_date and date_from_dt <= review_date <= date_to_dt:
                date_filtered.append(review)
        
        # 5. Фильтруем по языку
        status_text.text("🇷🇺 Фильтрация по русскому языку...")
        russian_reviews = filter_by_language(date_filtered)
        
        if not russian_reviews:
            st.warning("⚠️ Нет отзывов на русском языке в указанном диапазоне")
            st.stop()
        
        # 6. Сортируем
        status_text.text("📊 Сортировка отзывов...")
        if sort_order == "По убыванию (5→1)":
            sorted_reviews = sorted(russian_reviews, key=lambda x: x.get('rating', 0), reverse=True)
        else:
            sorted_reviews = sorted(russian_reviews, key=lambda x: x.get('rating', 0))
        
        # 7. Подготавливаем данные для отображения
        status_text.text("📊 Подготовка данных...")
        
        data = []
        for r in sorted_reviews:
            data.append({
                'Дата': r['date'].strftime("%Y-%m-%d %H:%M:%S") if r.get('date') else '',
                'Оценка': r.get('rating', 0),
                'Заголовок': clean_text(r.get('title', '')),
                'Текст_отзыва': clean_text(r.get('review', '')),
                'Автор': clean_text(r.get('userName', ''))
            })
        
        df = pd.DataFrame(data)
        
        # Скрываем прогресс
        progress_bar.empty()
        status_text.empty()
        
        # ==================== ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ ====================
        st.markdown("---")
        st.success(f"✅ Собрано {len(df)} отзывов!")
        
        # Статистика
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📥 Всего собрано", total)
        with col2:
            st.metric("📅 По дате", len(date_filtered))
        with col3:
            st.metric("🇷🇺 На русском", len(russian_reviews))
        with col4:
            st.metric("⭐ Средняя оценка", f"{df['Оценка'].mean():.2f}")
        
        # Распределение по оценкам
        st.subheader("⭐ Распределение по оценкам")
        rating_counts = df['Оценка'].value_counts().sort_index(ascending=False)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(rating_counts)
        with col2:
            st.dataframe(
                rating_counts.reset_index().rename(
                    columns={'index': 'Оценка', 'Оценка': 'Количество'}
                ),
                hide_index=True,
                use_container_width=True
            )
        
        # Таблица с отзывами
        st.subheader("📋 Список отзывов")
        
        # Фильтры для таблицы
        col1, col2 = st.columns(2)
        with col1:
            rating_filter = st.multiselect(
                "Фильтр по оценке",
                options=sorted(df['Оценка'].unique(), reverse=True),
                default=sorted(df['Оценка'].unique(), reverse=True)
            )
        with col2:
            search_text = st.text_input("🔍 Поиск по тексту", placeholder="Введите слово для поиска...")
        
        # Применяем фильтры
        filtered_df = df[df['Оценка'].isin(rating_filter)]
        if search_text:
            filtered_df = filtered_df[
                filtered_df['Текст_отзыва'].str.contains(search_text, case=False, na=False) |
                filtered_df['Заголовок'].str.contains(search_text, case=False, na=False)
            ]
        
        # Отображаем таблицу
        st.dataframe(
            filtered_df,
            use_container_width=True,
            height=400,
            column_config={
                "Дата": st.column_config.DatetimeColumn("Дата", format="YYYY-MM-DD HH:mm"),
                "Оценка": st.column_config.NumberColumn("Оценка", format="%d ★"),
                "Заголовок": st.column_config.TextColumn("Заголовок", width="medium"),
                "Текст_отзыва": st.column_config.TextColumn("Текст отзыва", width="large"),
                "Автор": st.column_config.TextColumn("Автор", width="small"),
            }
        )
        
        # ==================== СКАЧИВАНИЕ ====================
        st.markdown("---")
        st.subheader("💾 Скачать данные")
        
        col1, col2, col3 = st.columns(3)
        
        # CSV
        with col1:
            csv = df.to_csv(sep=';', index=False, encoding='utf-8-sig')
            b64_csv = base64.b64encode(csv.encode('utf-8-sig')).decode()
            href_csv = f'<a href="data:text/csv;base64,{b64_csv}" download="reviews_{app_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv" style="text-decoration:none;"><div style="background:#4CAF50;color:white;padding:10px;border-radius:5px;text-align:center;">📥 Скачать CSV</div></a>'
            st.markdown(href_csv, unsafe_allow_html=True)
        
        # Excel
        with col2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Отзывы')
            excel_data = output.getvalue()
            b64_excel = base64.b64encode(excel_data).decode()
            href_excel = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="reviews_{app_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx" style="text-decoration:none;"><div style="background:#2196F3;color:white;padding:10px;border-radius:5px;text-align:center;">📊 Скачать Excel</div></a>'
            st.markdown(href_excel, unsafe_allow_html=True)
        
        # JSON
        with col3:
            json_data = df.to_json(orient='records', force_ascii=False, indent=2)
            b64_json = base64.b64encode(json_data.encode('utf-8')).decode()
            href_json = f'<a href="data:application/json;base64,{b64_json}" download="reviews_{app_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json" style="text-decoration:none;"><div style="background:#FF9800;color:white;padding:10px;border-radius:5px;text-align:center;">📄 Скачать JSON</div></a>'
            st.markdown(href_json, unsafe_allow_html=True)
        
        st.info("💡 Нажмите на кнопку для скачивания файла в нужном формате")
        
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")
        st.exception(e)

else:
    # Отображение инструкции при первом запуске
    st.info("👈 Настройте параметры в боковой панели и нажмите 'Начать парсинг'")
    
    st.markdown("""
    ### 📌 Как использовать:
    1. **Вставьте ссылку** на приложение из App Store
    2. **Выберите период** для фильтрации отзывов
    3. **Настройте сортировку** и количество отзывов
    4. **Нажмите кнопку** "Начать парсинг"
    5. **Скачайте** результат в CSV, Excel или JSON
    
    ### 📱 Примеры приложений:
    - Duolingo: `https://apps.apple.com/ru/app/duolingo-языки-и-шахматы/id570060128`
    - Spotify: `https://apps.apple.com/ru/app/spotify/id324684580`
    - Telegram: `https://apps.apple.com/ru/app/telegram/id686449807`
    """)

# ==================== ПОДВАЛ ====================
st.markdown("---")
st.caption("🔧 Парсер отзывов App Store | Сделано с ❤️ на Streamlit")