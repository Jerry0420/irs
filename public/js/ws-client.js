/* WebSocket 薄封裝：JSON 訊息分派 + 指數退避自動重連（重連後伺服器會重送 state:init） */
class WSClient {
  constructor(path = "/ws") {
    this.path = path;
    this.handlers = {};
    this.retryMs = 500;
    this.ws = null;
  }

  on(type, fn) {
    (this.handlers[type] = this.handlers[type] || []).push(fn);
    return this;
  }

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}${this.path}`);

    this.ws.onopen = () => {
      this.retryMs = 500;
      this._emit("_open");
    };

    this.ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      this._emit(msg.type, msg.payload);
    };

    this.ws.onclose = () => {
      this._emit("_close");
      setTimeout(() => this.connect(), this.retryMs);
      this.retryMs = Math.min(this.retryMs * 2, 10000);
    };

    this.ws.onerror = () => this.ws.close();
    return this;
  }

  send(type, payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, payload }));
      return true;
    }
    return false;
  }

  _emit(type, payload) {
    (this.handlers[type] || []).forEach((fn) => fn(payload));
  }
}
