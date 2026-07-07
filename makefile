restart_ngrok:
	@echo "Restarting ngrok..."
	@pkill -x ngrok || true
	@sleep 1
	@nohup ngrok http 3000 > /dev/null 2>&1 &
	@echo "Waiting for ngrok tunnel..."
	@sleep 3
	@curl -s --retry 5 --retry-delay 1 --retry-connrefused \
	  http://127.0.0.1:4040/api/tunnels \
	  | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])"

restart_server:
	@echo "Restarting server..."
	@pkill -x uvicorn || true
	@sleep 1
	@nohup /home/ec2-user/irs/run.sh > uvicorn.log 2>&1 &

# Cloudflare Tunnel（免費、無 ngrok 警告頁）。安裝（免 sudo，放專案目錄即可）：
#   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
#     -o ./cloudflared && chmod +x ./cloudflared
CLOUDFLARED := $(shell command -v cloudflared 2>/dev/null || echo ./cloudflared)

restart_tunnel:
	@test -x "$(CLOUDFLARED)" || { echo "找不到 cloudflared，請先執行 makefile 註解中的安裝指令"; exit 1; }
	@echo "Restarting Cloudflare Tunnel..."
	@pkill -x cloudflared || true
	@sleep 1
	@nohup $(CLOUDFLARED) tunnel --url http://localhost:3000 > cloudflared.log 2>&1 &
	@echo "Waiting for tunnel URL..."
	@for i in $$(seq 1 15); do \
	  URL=$$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' cloudflared.log | head -1); \
	  if [ -n "$$URL" ]; then echo "$$URL"; exit 0; fi; \
	  sleep 1; \
	done; echo "取得網址逾時，請查看 cloudflared.log"; exit 1