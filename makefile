restart_ngrok:
	@echo "Restarting ngrok..."
	@pkill -x ngrok || true
	@sleep 1
	@nohup ngrok http 3000 > ngrok.log 2>&1 &
	@echo "Waiting for ngrok tunnel..."
	@sleep 3
	@curl -s --retry 5 --retry-delay 1 --retry-connrefused \
	  http://127.0.0.1:4040/api/tunnels \
	  | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])"