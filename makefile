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

# curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ./cloudflared
# chmod +x ./cloudflared

restart_tunnel:
	@echo "Restarting Cloudflare Tunnel..."
	@pkill -x cloudflared || true
	@sleep 1
	@nohup cloudflared tunnel --url http://localhost:3000 > cloudflared.log 2>&1 &
	@echo "Waiting for tunnel URL..."
	@for i in $$(seq 1 15); do \
	  URL=$$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' cloudflared.log | head -1); \
	  if [ -n "$$URL" ]; then echo "$$URL"; exit 0; fi; \
	  sleep 1; \
	done; echo "取得網址逾時，請查看 cloudflared.log"; exit 1