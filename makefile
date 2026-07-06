restart_ngrok:
	@echo "Restarting ngrok..."
	@pkill -f ngrok || true
	@nohup ngrok http 3000 > ngrok.log 2>&1 &
	@echo "ngrok restarted. Public URL:"
	@curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])"