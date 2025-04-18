
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Авторизация
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# Загрузка CSV
df = pd.read_csv("quiz_questions_template.csv")  # Файл должен лежать рядом со скриптом

# Открытие таблицы и листа
sheet_id = "16NFOXf7EJj0mvrUIWkcJXKFEZLuY9dwsOV5XpibvOFo"
spreadsheet = client.open_by_key(sheet_id)
sheet = spreadsheet.sheet1

# Очистка и загрузка данных
sheet.clear()
sheet.insert_row(df.columns.tolist(), index=1)
sheet.insert_rows(df.values.tolist(), row=2)

print("✅ Вопросы успешно загружены в Google Таблицу!")
