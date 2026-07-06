# bullseye（glibc 2.31）基底：主機 Docker 20.10.7 的 seccomp 不支援 clone3，
# bookworm 基底的映像會在 pip/執行期出現 "can't start new thread"
FROM python:3.11-slim-bullseye

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY public ./public

EXPOSE 3000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
