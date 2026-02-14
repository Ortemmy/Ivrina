from flask import Flask, render_template, request
import requests
import json
import warnings
import time
from datetime import datetime
import ssl
from tokens import secret, client_id, rquid
warnings.filterwarnings('ignore')

app = Flask(__name__)

class GigaChatClient:
    def __init__(self, client_id, client_secret, rquid):
        self.auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self.client_id = client_id
        self.client_secret = client_secret
        self.rquid = rquid
        self.access_token = None
        self.token_expiry = 0
        
    def _get_auth_header(self):
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f'Basic {encoded_credentials}'
    
    def get_access_token(self):
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'RqUID': self.rquid,
                'Authorization': self._get_auth_header()
            }
            
            payload = {'scope': 'GIGACHAT_API_PERS'}
            
            # Увеличиваем таймауты и пробуем отключить SSL проверку полностью
            response = requests.post(
                self.auth_url, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token')
                self.token_expiry = data.get('expires_at', 0)
                print(f"✅ Токен получен (действителен до: {datetime.fromtimestamp(self.token_expiry/1000)})")
                return True
            else:
                print(f"❌ Ошибка получения токена: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("❌ Таймаут при получении токена")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Ошибка соединения при получении токена: {e}")
            return False
        except Exception as e:
            print(f"❌ Исключение при получении токена: {str(e)}")
            return False
    
    def is_token_valid(self):
        if not self.access_token:
            return False
        current_time = int(time.time() * 1000)
        return current_time < (self.token_expiry - 300000)
    
    def ensure_valid_token(self):
        if not self.is_token_valid():
            print("🔄 Токен истек, запрашиваю новый...")
            return self.get_access_token()
        return True
    
    def get_response(self, message):
        # Проверяем и получаем токен
        if not self.ensure_valid_token():
            return "Извините, не удалось подключиться к AI сервису. Пожалуйста, попробуйте позже."
        
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.access_token}'
            }
            
            payload = {
                "model": "GigaChat",
                "messages": [{"role": "user", "content": message}],
                "temperature": 0.7,
                "max_tokens": 256,  # Уменьшаем для более быстрого ответа
                "stream": False
            }
            
            print(f"📤 Отправляю запрос в GigaChat: '{message[:50]}...'")
            
            # Отправляем запрос с увеличенным таймаутом
            response = requests.post(
                self.chat_url, 
                headers=headers, 
                json=payload,
                verify=False,
                timeout=45  # Увеличиваем таймаут
            )
            
            print(f"📥 Получен ответ: {response.status_code}")
            
            # Если токен истек
            if response.status_code == 401:
                print("🔄 Токен истек, обновляю...")
                if self.get_access_token():
                    headers['Authorization'] = f'Bearer {self.access_token}'
                    response = requests.post(
                        self.chat_url, 
                        headers=headers, 
                        json=payload,
                        verify=False,
                        timeout=45
                    )
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    reply = data['choices'][0]['message']['content']
                    print(f"✅ Получен ответ от GigaChat ({len(reply)} символов)")
                    return reply
                else:
                    print("❌ Неожиданный формат ответа")
                    return "Извините, не удалось обработать ответ AI."
            else:
                print(f"❌ Ошибка API: {response.status_code} - {response.text[:200]}")
                return f"Ошибка сервиса ({response.status_code}). Попробуйте еще раз."
                
        except requests.exceptions.Timeout:
            print("❌ Таймаут при запросе к GigaChat")
            return "Извините, время ожидания ответа истекло. Попробуйте еще раз."
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Ошибка соединения: {e}")
            return "Извините, проблема с соединением. Проверьте интернет и попробуйте снова."
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {str(e)}")
            return f"Произошла ошибка: {str(e)[:100]}"

# Инициализируем клиент
print("🚀 Инициализация GigaChat клиента...")
gigachat_client = GigaChatClient(
    client_id=client_id,
    client_secret=secret,
    rquid=rquid
)

# Тестовый запрос при запуске
print("🧪 Тестовый запрос при запуске...")
test_response = gigachat_client.get_response("Привет! Ответь 'Готов к работе' если ты работаешь.")
print(f"Тестовый ответ: {test_response}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    user_message = request.form.get("message", "").strip()
    
    print(f"\n📩 Получено сообщение от пользователя: '{user_message}'")
    
    if not user_message:
        reply = "Вы ничего не ввели. Пожалуйста, напишите что-нибудь!"
    else:
        # Получаем ответ от GigaChat
        reply = gigachat_client.get_response(user_message)
    
    print(f"📤 Отправляю ответ пользователю")
    
    return render_template("result.html", 
                         user_message=user_message, 
                         reply=reply,
                         now=datetime.now())

if __name__ == "__main__":
    print("🌐 Запуск Flask сервера...")
    app.run(debug=True, host='0.0.0.0', port=5000)