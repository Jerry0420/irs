restart_ngrok:
	@echo "Restarting ngrok..."
	@pkill -x ngrok || true
	@sleep 1
	@nohup ngrok http --url=mimifrogmoonyoung.ngrok.app 3000 > /dev/null 2>&1 &
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

kill_ngrok:
	@echo "Killing ngrok..."
	@pkill -x ngrok || true

kill_server:
	@echo "Killing server..."
	@pkill -x uvicorn || true