nohup /home/ec2-user/irs/run.sh > uvicorn.log 2>&1 &
nohup ngrok http 3000 > ngrok.log 2>&1 &
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])"